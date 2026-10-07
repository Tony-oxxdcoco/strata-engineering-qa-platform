"""Authenticated API, immutable artifacts, durable jobs and review workspace."""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
import re
import secrets
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from . import __version__, model
from .security import hash_password, token_hash, verify_password
from .storage import Audit, LoginSession, Membership, Resource, Store, User, canonical, digest, now, public, uid
from .workflow import REQUIRED, ROOT, WORKFLOW_VERSION, TOOL_FINGERPRINT, Runner, node_tool, outcome

from .provenance import validate_file

MAX_BODY = 14_000_000


def create_app(data_dir=None, testing=False, worker=True):
    store = Store(data_dir or os.environ.get("STRATA_DATA_DIR", ROOT / ".runtime"), os.environ.get("STRATA_DATABASE_URL"))
    runner = Runner(store)
    week5_instance = os.environ.get("STRATA_WEEK5_INSTANCE", "")
    if week5_instance and not re.fullmatch(r"[0-9a-f]{32}", week5_instance):
        raise ValueError("STRATA_WEEK5_INSTANCE must be a managed 32-character hexadecimal instance identifier")
    bootstrap_lock = threading.Lock()
    login_attempts = {}
    public_origin = os.environ.get("STRATA_PUBLIC_ORIGIN", "").rstrip("/")
    if public_origin:
        parsed_origin = urlsplit(public_origin)
        if parsed_origin.scheme != "https" or not parsed_origin.hostname or parsed_origin.path or parsed_origin.query or parsed_origin.fragment or parsed_origin.username or parsed_origin.password:
            raise ValueError("STRATA_PUBLIC_ORIGIN must be a plain HTTPS origin")

    @asynccontextmanager
    async def lifespan(app):
        if worker:
            runner.start()
        yield
        runner.close()

    app = FastAPI(title="STRATA QA", version=__version__, lifespan=lifespan)
    app.state.store, app.state.runner = store, runner

    @app.middleware("http")
    async def boundaries(request, call_next):
        allowed = {"127.0.0.1", "localhost", "::1", *os.environ.get("STRATA_ALLOWED_HOSTS", "").split(",")}
        if testing:
            allowed.add("testserver")
        if request.url.hostname not in allowed:
            return JSONResponse({"detail": "Host is not configured"}, 400)
        origin = request.headers.get("origin")
        expected_origin = public_origin or str(request.base_url).rstrip("/")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != expected_origin:
            return JSONResponse({"detail": "Cross-origin mutation rejected"}, 403)
        try:
            declared = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, 400)
        if declared > MAX_BODY:
            return JSONResponse({"detail": "Request exceeds 14 MB"}, 413)
        if request.method in {"POST", "PUT", "PATCH"}:
            parts, size = [], 0
            async for part in request.stream():
                size += len(part)
                if size > MAX_BODY:
                    return JSONResponse({"detail": "Request exceeds 14 MB"}, 413)
                parts.append(part)
            request._body = b"".join(parts)
            media=request.headers.get('content-type','').split(';')[0].strip().lower()
            if request._body and (not media or media=='application/json' or media.startswith('application/') and media.endswith('+json')):
                from .data_tools import _json_float, _json
                def unique(items):
                    result={}
                    for key,value in items:
                        if key in result: raise ValueError('Duplicate JSON request field: '+key)
                        result[key]=value
                    return result
                try:
                    value=json.loads(request._body,object_pairs_hook=unique,parse_float=_json_float,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('JSON numbers must be finite')))
                    _json(value)
                except (ValueError,RecursionError,UnicodeError) as error:
                    return JSONResponse({'detail':{'kind':'INVALID_INPUT','message':str(error)[:600]}},422)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        path=request.url.path
        kind='IMPORT_MAPPING_ERROR' if hasattr(error,'errors') else 'CONFIGURATION_ERROR' if any(x in path for x in ('/rules','/rule-packages','/adapters','/cases')) else 'IMPORT_ERROR' if '/files' in path or '/connector/import' in path else 'INVALID_INPUT'
        detail={'kind':kind,'message':str(error)[:600]}
        if hasattr(error,'errors'): detail['errors']=error.errors
        return JSONResponse({'detail':detail},422)

    @app.exception_handler(IntegrityError)
    async def conflict(request, error):
        return JSONResponse({"detail": "Concurrent or duplicate request; reload and retry with the same idempotency key"}, 409)

    def user(request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 256:
            raise HTTPException(401, "Sign in to continue")
        with store.session() as session:
            login = session.get(LoginSession, token_hash(auth[7:]))
            if not login or login.expires_at <= time.time():
                raise HTTPException(401, "Session expired")
            account = session.get(User, login.user_id)
            if not account:
                raise HTTPException(401, "Account unavailable")
            return {"id": account.id, "username": account.username, "admin": bool(account.admin)}

    def access(session, project_id, account, roles=None):
        project = session.get(Resource, project_id)
        membership = session.get(Membership, (project_id, account["id"]))
        if not project or project.kind != "project" or not membership:
            raise HTTPException(404, "Project not found")
        if roles and membership.role not in roles:
            raise HTTPException(403, "Your project role cannot perform this action")
        return project, membership.role

    def resource(session, project_id, kind, resource_id):
        if not isinstance(resource_id, str) or len(resource_id) > 80:
            raise ValueError("Invalid resource identifier")
        row = session.get(Resource, resource_id)
        if not row or row.project_id != project_id or row.kind != kind:
            raise HTTPException(404, f"{kind.title()} not found")
        return row

    def require_fields(body, allowed, required=()):
        if not isinstance(body, dict) or set(body) - set(allowed) or set(required) - set(body):
            raise ValueError("Missing or unsupported request fields")
        canonical(body)

    def issue_session(session, account):
        token = secrets.token_urlsafe(40)
        session.add(LoginSession(token_hash=token_hash(token), user_id=account.id, expires_at=time.time() + 8 * 3600))
        return {"token": token, "user": {"id": account.id, "username": account.username, "admin": bool(account.admin)}}

    @app.get("/api/v1/health")
    def health():
        with store.session() as session:
            session.execute(select(Resource.id).limit(1))
        result = {"status": "ok", "version": __version__, "workflow": WORKFLOW_VERSION, "storage": "server", "worker": bool(runner.thread and runner.thread.is_alive()), "tasks": model.TASKS}
        if week5_instance:
            result["week5_instance"] = week5_instance
        return result

    @app.get("/api/v1/auth/setup")
    def setup():
        with store.session() as session:
            return {"needs_setup": session.scalar(select(User.id).limit(1)) is None, "token_required": bool(os.environ.get("STRATA_SETUP_TOKEN"))}

    @app.post("/api/v1/auth/bootstrap")
    def bootstrap(request: Request, body: dict = Body(...)):
        require_fields(body, ["username", "password"], ["username", "password"])
        local = request.client and request.client.host in {"127.0.0.1", "::1"} and request.url.hostname in {"127.0.0.1", "localhost", "::1"}
        setup_token = os.environ.get("STRATA_SETUP_TOKEN")
        if not testing and not local and not (setup_token and secrets.compare_digest(request.headers.get("x-setup-token", ""), setup_token)):
            raise HTTPException(403, "First account must be created locally or with the operator setup token")
        if not isinstance(body["username"], str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", body["username"]):
            raise ValueError("Username must be 3–80 letters, numbers or ._@-")
        with bootstrap_lock, store.session.begin() as session:
            if session.scalar(select(User.id).limit(1)):
                raise HTTPException(409, "Setup is already complete")
            account = User(id=uid("user"), username=body["username"], password=hash_password(body["password"]), admin=1)
            session.add(account)
            return issue_session(session, account)

    @app.post("/api/v1/auth/login")
    def login(request: Request, body: dict = Body(...)):
        require_fields(body, ["username", "password"], ["username", "password"])
        if not isinstance(body["username"], str) or not isinstance(body["password"], str) or len(body["username"]) > 80 or len(body["password"]) > 200:
            raise ValueError("Invalid login fields")
        key = request.client.host if request.client else "unknown"
        current = time.time()
        recent = [t for t in login_attempts.get(key, []) if current - t < 60]
        if len(recent) >= 10:
            raise HTTPException(429, "Too many sign-in attempts; retry in a minute")
        login_attempts[key] = recent + [current]
        with store.session.begin() as session:
            account = session.scalar(select(User).where(User.username == body["username"]))
            if not account or not verify_password(body["password"], account.password):
                raise HTTPException(401, "Invalid username or password")
            return issue_session(session, account)

    @app.get("/api/v1/auth/me")
    def me(account=Depends(user)):
        return account

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, account=Depends(user)):
        with store.session.begin() as session:
            session.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.headers["authorization"][7:])))
        return {"ok": True}

    @app.post("/api/v1/auth/password")
    def change_password(body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["current_password", "new_password"], ["current_password", "new_password"])
        with store.session.begin() as session:
            row = session.get(User, account["id"])
            if not verify_password(body["current_password"], row.password):
                raise HTTPException(401, "Current password is incorrect")
            row.password = hash_password(body["new_password"])
            session.execute(delete(LoginSession).where(LoginSession.user_id == account["id"]))
        return {"ok": True, "message": "Password changed. Sign in again; prior sessions are revoked."}

    @app.get("/api/v1/users")
    def list_users(account=Depends(user)):
        if not account["admin"]:
            raise HTTPException(403, "Administrator required")
        with store.session() as session:
            return {"items": [{"id": u.id, "username": u.username, "admin": bool(u.admin)} for u in session.scalars(select(User).order_by(User.username))]}

    @app.post("/api/v1/users")
    def create_user(body: dict = Body(...), account=Depends(user)):
        if not account["admin"]:
            raise HTTPException(403, "Administrator required")
        require_fields(body, ["username", "password"], ["username", "password"])
        if not isinstance(body["username"], str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", body["username"]):
            raise ValueError("Invalid username")
        with store.session.begin() as session:
            if session.scalar(select(User.id).where(User.username == body["username"])):
                raise HTTPException(409, "Username already exists")
            row = User(id=uid("user"), username=body["username"], password=hash_password(body["password"]), admin=0)
            session.add(row)
            return {"user": {"id": row.id, "username": row.username, "admin": False}}

    @app.get("/api/v1/projects")
    def projects(account=Depends(user)):
        with store.session() as session:
            memberships = list(session.scalars(select(Membership).where(Membership.user_id == account["id"])))
            return {"items": [{**public(session.get(Resource, m.project_id)), "role": m.role} for m in memberships]}

    @app.post("/api/v1/projects")
    def create_project(body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["name"], ["name"])
        if not isinstance(body["name"], str) or not 1 <= len(body["name"].strip()) <= 120:
            raise ValueError("Project name must contain 1–120 characters")
        with store.session.begin() as session:
            project_id = uid("project")
            row = store.add(session, "project", project_id, {"name": body["name"].strip(), "active_snapshot_id": None, "owner": account["id"]}, project_id)
            session.add(Membership(project_id=project_id, user_id=account["id"], role="reviewer"))
            store.audit(session, project_id, account["id"], "project.created", project_id)
            return {"project": {**public(row), "role": "reviewer"}}

    @app.post("/api/v1/projects/{project_id}/members")
    def add_member(project_id: str, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["user_id", "role"], ["user_id", "role"])
        if not isinstance(body["role"], str) or body["role"] not in {"viewer", "engineer", "reviewer"} or not isinstance(body["user_id"], str):
            raise ValueError("Invalid project role")
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"reviewer"})
            if project.data["owner"] != account["id"]:
                raise HTTPException(403, "Project owner manages membership")
            if body["user_id"] == project.data["owner"]:
                raise ValueError("Owner role cannot be downgraded")
            if not session.get(User, body["user_id"]):
                raise HTTPException(404, "User not found")
            session.merge(Membership(project_id=project_id, **body))
            store.audit(session, project_id, account["id"], "member.updated", body["user_id"], {"role": body["role"]})
        return {"ok": True}

    @app.post("/api/v1/projects/{project_id}/model-policy")
    def model_policy(project_id: str, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["daily_limit"], ["daily_limit"])
        if type(body["daily_limit"]) is not int or not 0 <= body["daily_limit"] <= 10000:
            raise ValueError("Daily call limit must be an integer from 0 to 10000")
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"reviewer"})
            if project.data["owner"] != account["id"]:
                raise HTTPException(403, "Only the project owner can set model limits")
            store.change(session, project, {**project.data, "model_daily_limit": body["daily_limit"]})
            store.audit(session, project_id, account["id"], "model.policy_updated", project_id, body)
            return {"ok": True}

    @app.delete("/api/v1/projects/{project_id}/members/{user_id}")
    def remove_member(project_id: str, user_id: str, account=Depends(user)):
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"reviewer"})
            if project.data["owner"] != account["id"] or user_id == project.data["owner"]:
                raise HTTPException(403, "Only the owner can remove another project member")
            row = session.get(Membership, (project_id, user_id))
            if not row:
                raise HTTPException(404, "Project member not found")
            session.delete(row)
            store.audit(session, project_id, account["id"], "member.removed", user_id)
            return {"ok": True}

    @app.get("/api/v1/projects/{project_id}/export")
    def export_project(project_id: str, account=Depends(user)):
        with store.session() as session:
            project, _ = access(session, project_id, account, {"reviewer"})
            records = list(session.scalars(select(Resource).where(Resource.project_id == project_id)))
            sources = {r.data["sha256"] for r in records if r.kind == "file"}
            if sum((store.blobs / sha).stat().st_size for sha in sources) > 200_000_000:
                raise ValueError("Project source export exceeds 200 MB; ask the operator for a backup")
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                payload = {"schema": "strata-project-export/1", "project": public(project), "resources": [{"kind": r.kind, **public(r)} for r in records if r.kind not in {"idempotency", "cache"}], "audit": store.audit_chain(session, project_id), "exported_at": now()}
                bundle.writestr("project.json", canonical(payload))
                for sha in sorted(sources):
                    bundle.writestr("sources/" + sha, store.get_blob(sha))
                bundle.writestr("README.txt", "Project records and original source bytes. Source filenames are mapped in project.json. No account passwords or session tokens are included. This is an inspection/export bundle, not a full server restore backup.")
            return Response(archive.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{project_id}.zip"'})

    @app.get("/api/v1/projects/{project_id}/runtime")
    def runtime(project_id: str, account=Depends(user)):
        from .usage import usage_view
        with store.session() as session:
            project, _ = access(session, project_id, account)
            rows = store.list(session, project_id, "run")
            return {"model_usage": usage_view(store, session, project), "jobs": {state: sum(r.data["state"] == state for r in rows) for state in ["QUEUED", "RUNNING", "WAITING", "COMPLETED", "ERROR", "CANCELLED"]}, "worker_alive": bool(runner.thread and runner.thread.is_alive())}

    def run_view(session, project, row):
        result = public(row)
        reasons = []
        integrity_problem = None
        if row.data.get("status") in {"PASS", "FAIL"} or row.data.get("output_hash"):
            checked = outcome(row.data.get("results", []))
            if not row.data.get("output_hash") or digest(checked) != row.data["output_hash"] or checked["status"] != row.data.get("status") or checked["summary"] != row.data.get("summary"):
                integrity_problem = "Stored calculation result integrity failed"
            try:
                for key in ["snapshot_id", "compare_to"]:
                    if row.data.get(key):
                        saved = resource(session, project.id, "snapshot", row.data[key])
                        expected_hash = row.data.get("input_hash" if key == "snapshot_id" else "target_hash")
                        if digest(saved.data["input"]) != saved.data["input_hash"] or expected_hash and digest(saved.data["input"]) != expected_hash:
                            raise ValueError("Snapshot integrity failed")
                        source = resource(session, project.id, "file", saved.data["file_id"])
                        sha = source.data["sha256"]
                        side='target' if key=='compare_to' else 'source'
                        expected_source_hash=row.data.get('target_source_hash' if side=='target' else 'source_hash')
                        expected_file=row.data.get('target_file_id' if side=='target' else 'source_file_id')
                        if expected_source_hash and sha!=expected_source_hash or expected_file and source.id!=expected_file: raise ValueError('Original source binding changed after checking')
                        chain_key=(source.id,source.revision,sha)
                        cache = session.info.setdefault("source_integrity", {})
                        if chain_key not in cache:
                            try:
                                validate_file(store,session,source)
                                cache[chain_key] = None
                            except (ValueError, OSError) as error:
                                cache[chain_key] = str(error)
                        if cache[chain_key]:
                            raise ValueError(cache[chain_key])
                for rule_id in row.data.get("rule_ids", []):
                    applied = resource(session, project.id, "rule", rule_id)
                    sha = applied.data["rule"]["source_sha256"]
                    rule_source_key=("rule",sha)
                    cache = session.info.setdefault("source_integrity", {})
                    if rule_source_key not in cache:
                        try:
                            runner.source_valid(session, project.id, sha)
                            cache[rule_source_key] = None
                        except (ValueError, OSError) as error:
                            cache[rule_source_key] = str(error)
                    if cache[rule_source_key]:
                        raise ValueError(cache[rule_source_key])
            except (ValueError, OSError, HTTPException):
                integrity_problem = "Stored input or original source integrity failed"
        if integrity_problem:
            reason = integrity_problem + "; no verified outcome is displayed"
            result.update(outcome([{"id": "INTEGRITY-GATE", "status": "NOT VERIFIED", "summary": reason, "details": []}]))
            result.update(state="ERROR", explanation=reason, integrity_status="INVALID", citations=[])
            reasons.append(reason)
        if row.data.get("tool_fingerprint") and row.data["tool_fingerprint"] != TOOL_FINGERPRINT:
            reasons.append("The checking implementation has changed; rerun before sign-off")
        current_input = row.data.get("compare_to") if row.data.get("task_id") == "handoff" else row.data.get("snapshot_id")
        if project.data.get("active_snapshot_id") != current_input:
            reasons.append("A newer input revision is active")
        for rid in row.data.get("rule_ids", []):
            rule = session.get(Resource, rid)
            if not rule or rule.data["rule"]["status"] != "approved":
                reasons.append("An applied rule is no longer approved")
        if row.data.get("rule_hash"):
            from .knowledge import retrieve
            task = row.data["task_id"]
            current_rules = [dict(r.data["rule"], resource_id=r.id) for r in store.list(session, project.id, "rule")]
            snapshot = session.get(Resource, row.data.get("snapshot_id"))
            if snapshot and snapshot.data["input"].get("synthetic") is not True:
                current_rules = [r for r in current_rules if r["authority"] == "client"]
            from .contracts import applicable
            current_rules = [r for r in current_rules if applicable(r, snapshot.data["input"] if snapshot else {})]
            retrieved = retrieve(" ".join(REQUIRED[task]), task, current_rules, project.id, limit=50)
            if retrieved["status"] != "FOUND" or digest(retrieved["rules"]) != row.data["rule_hash"]:
                reasons.append("Applicable approved rule context has changed")
        result["stale"] = bool(reasons)
        result["stale_reasons"] = reasons
        result["review_state"] = "STALE" if reasons else row.data.get("review_state", "UNREVIEWED")
        return result

    @app.get("/api/v1/projects/{project_id}/dashboard")
    def dashboard(project_id: str, account=Depends(user)):
        with store.session() as session:
            project, role = access(session, project_id, account)
            return {"project": {**public(project), "role": role}, "files": [public(r) for r in store.list(session, project_id, "file")], "snapshots": [public(r) for r in store.list(session, project_id, "snapshot")], "rules": [public(r) for r in store.list(session, project_id, "rule")], "runs": [run_view(session, project, r) for r in store.list(session, project_id, "run")], "issues": [public(r) for r in store.list(session, project_id, "issue")], "members": [{"user_id": m.user_id, "role": m.role, "username": session.get(User, m.user_id).username} for m in session.scalars(select(Membership).where(Membership.project_id == project_id))], "adapters": [public(r) for r in store.list(session, project_id, "adapter")], "cases": [public(r) for r in store.list(session, project_id, "case")], "evaluations": [{"id": r.id, "created_at": r.created_at} for r in store.list(session, project_id, "evaluation")], "audit": store.audit_chain(session, project_id)}

    def add_file(session, project_id, filename, content, account_id, source_only=False):
        from .data_tools import ingest
        if not isinstance(filename, str) or not filename or len(filename) > 180 or Path(filename).name != filename or "\\" in filename:
            raise ValueError("Use a simple filename without directories")
        if not 0 < len(content) <= 10_000_000:
            raise ValueError("Files must contain 1 byte–10 MB")
        if source_only:
            if Path(filename).suffix.lower() not in {".csv", ".json"}:
                raise ValueError("Source-only upload is available for CSV/JSON mapping inputs")
            text = content.decode("utf-8-sig")
            ingestion = {"status": "NEEDS_MAPPING", "format": "raw-mapping-source", "pages": [], "warnings": ["Original bytes retained; select an explicit adapter. No fields or units inferred."]}
        else:
            ingestion = ingest(filename, content)
        sha = store.put_blob(content)
        row = store.add(session, "file", project_id, {"filename": filename, "sha256": sha, "size_bytes": len(content), "ingestion": ingestion, "uploaded_by": account_id})
        store.audit(session, project_id, account_id, "file.uploaded", row.id, {"sha256": sha, "filename": filename})
        return row

    @app.post("/api/v1/projects/{project_id}/files")
    def upload(project_id: str, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["filename", "content_base64", "source_only"], ["filename", "content_base64"])
        if "source_only" in body and type(body["source_only"]) is not bool:
            raise ValueError("source_only must be boolean")
        try:
            content = base64.b64decode(body["content_base64"], validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid base64 file content") from error
        with store.session.begin() as session:
            access(session, project_id, account, {"engineer", "reviewer"})
            row = add_file(session, project_id, body["filename"], content, account["id"], source_only=body.get("source_only", False))
            return {"file": public(row)}

    @app.get("/api/v1/projects/{project_id}/files/{file_id}/content")
    def download(project_id: str, file_id: str, account=Depends(user)):
        with store.session() as session:
            access(session, project_id, account)
            row = resource(session, project_id, "file", file_id)
            content = store.get_blob(row.data["sha256"])
            return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": 'attachment; filename="source-file"', "X-Source-SHA256": row.data["sha256"]})

    def add_snapshot(session, project, source, body, account_id):
        payload = body["input"] if "input" in body else source.data["ingestion"].get("snapshot")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("File needs an explicit engineering mapping before a snapshot can be created")
        from .data_tools import _json
        _json(payload)
        if source.data["ingestion"].get("status") in {"NEEDS_OCR", "OCR_PAGE_IMAGE"}:
            raise ValueError("Scanned PDF values are unverified. Confirm the page transcription before creating a mapped snapshot.")
        validate_file(store,session,source)
        canonical(payload)
        parent = body.get("parent_id")
        if parent:
            resource(session, project.id, "snapshot", parent)
        row = store.add(session, "snapshot", project.id, {"title": str(body.get("title") or source.data["filename"])[:160], "file_id": source.id, "input": payload, "input_hash": digest(payload), "parent_id": parent, "created_by": account_id, "mapping": "manual" if "input" in body else "parsed", "mapping_note": str(body.get("mapping_note", ""))[:1000]})
        store.change(session, project, {**project.data, "active_snapshot_id": row.id})
        store.audit(session, project.id, account_id, "snapshot.created", row.id, {"input_hash": digest(payload), "file_id": source.id, "parent_id": parent})
        return row

    @app.post("/api/v1/projects/{project_id}/snapshots")
    def snapshot(project_id: str, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["file_id", "title", "input", "parent_id", "mapping_note"], ["file_id"])
        if "input" in body and not body.get("mapping_note"):
            raise ValueError("Manual mapping/corrections require a mapping_note")
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"engineer", "reviewer"})
            source = resource(session, project_id, "file", body["file_id"])
            return {"snapshot": public(add_snapshot(session, project, source, body, account["id"]))}

    @app.post("/api/v1/projects/{project_id}/snapshots/{snapshot_id}/corrections")
    def correct_snapshot(project_id: str, snapshot_id: str, body: dict = Body(...), account=Depends(user)):
        from .corrections import apply_corrections
        require_fields(body, ["title", "corrections"], ["corrections"])
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"engineer", "reviewer"})
            original = resource(session, project_id, "snapshot", snapshot_id)
            source = resource(session, project_id, "file", original.data["file_id"])
            validate_file(store,session,source)
            if digest(original.data["input"]) != original.data["input_hash"]:
                raise ValueError("Input integrity verification failed")
            corrected = apply_corrections(original.data["input"], body["corrections"])
            row = add_snapshot(session, project, source, {"title": body.get("title") or original.data["title"] + " · corrected", "input": corrected, "parent_id": original.id, "mapping_note": "Explicit field corrections; inspect the correction record and original source."}, account["id"])
            store.change(session, row, {**row.data, "adapter_id": original.data.get("adapter_id"), "adapter_hash": original.data.get("adapter_hash"), "provenance": original.data.get("provenance", []), "corrections": [{**change, "confirmed_by": account["id"], "confirmed_at": now()} for change in body["corrections"]]})
            store.audit(session, project_id, account["id"], "snapshot.corrected", row.id, {"parent_id": original.id, "paths": [c["path"] for c in body["corrections"]]})
            return {"snapshot": public(row)}

    @app.post("/api/v1/projects/{project_id}/snapshots/{snapshot_id}/activate")
    def activate_snapshot(project_id: str, snapshot_id: str, account=Depends(user)):
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"engineer", "reviewer"})
            row = resource(session, project_id, "snapshot", snapshot_id)
            store.change(session, project, {**project.data, "active_snapshot_id": row.id})
            store.audit(session, project_id, account["id"], "snapshot.activated", row.id)
            return {"snapshot": public(row)}

    def source_contains(source, text, raw=None, locator=None):
        ingestion = source.data["ingestion"]
        page_match=re.search(r'(?i)\bpage\s+(\d+)\b',locator or '')
        if page_match:
            return any(p.get('page')==int(page_match.group(1)) and text in p.get('text','') for p in ingestion.get('pages',[]))
        haystacks = [page.get("text", "") for page in ingestion.get("pages", [])]
        raw = store.get_blob(source.data["sha256"]) if raw is None else raw
        if source.data["filename"].lower().endswith((".txt", ".md", ".json", ".csv")):
            decoded = raw.decode("utf-8-sig")
            haystacks.append(decoded)
            if source.data["filename"].lower().endswith(".json"):
                def collect(value):
                    if isinstance(value, str): haystacks.append(value)
                    elif isinstance(value, dict):
                        for child in value.values(): collect(child)
                    elif isinstance(value, list):
                        for child in value: collect(child)
                collect(json.loads(decoded))
        for table in ingestion.get("tables", []):
            haystacks.append(canonical(table))
        return any(text in haystack for haystack in haystacks)

    @app.post("/api/v1/projects/{project_id}/rules")
    def add_rule(project_id: str, body: dict = Body(...), account=Depends(user)):
        from .knowledge import validate_rule
        require_fields(body, ["rule"], ["rule"])
        incoming = body["rule"]
        if not isinstance(incoming, dict):
            raise ValueError("rule must be an object")
        from .contracts import executable_rule
        rule = executable_rule({**incoming, "project_id": project_id, "status": "draft", "approved_by": None, "approved_at": None})
        with store.session.begin() as session:
            access(session, project_id, account, {"engineer", "reviewer"})
            sources = [r for r in store.list(session, project_id, "file") if r.data["sha256"] == rule["source_sha256"]]
            if not sources or not source_contains(sources[0], rule["text"],locator=rule["locator"]):
                raise ValueError("The exact rule excerpt must occur in an uploaded project source")
            if any(r.data["rule"]["id"] == rule["id"] and r.data["rule"]["version"] == rule["version"] for r in store.list(session, project_id, "rule")):
                raise HTTPException(409, "Rule ID/version already exists; create a new version")
            row = store.add(session, "rule", project_id, {"rule": rule, "created_by": account["id"]})
            store.audit(session, project_id, account["id"], "rule.drafted", row.id)
            return {"rule": public(row)}

    @app.post("/api/v1/projects/{project_id}/rules/{rule_id}/{action}")
    def rule_action(project_id: str, rule_id: str, action: str, account=Depends(user)):
        from .knowledge import validate_rule
        if action not in {"approve", "retire"}:
            raise HTTPException(404, "Action not found")
        with store.session.begin() as session:
            access(session, project_id, account, {"reviewer"})
            row = resource(session, project_id, "rule", rule_id)
            rule = dict(row.data["rule"])
            if action == "approve":
                if rule["status"] != "draft":
                    raise ValueError("Only a draft can be approved")
                sources = [s for s in store.list(session, project_id, "file") if s.data["sha256"] == rule["source_sha256"]]
                if not sources or not source_contains(sources[0], rule["text"],locator=rule["locator"]):
                    raise ValueError("Source excerpt verification failed")
                for other in store.list(session, project_id, "rule"):
                    if other.id != row.id and other.data["rule"]["id"] == rule["id"] and other.data["rule"]["status"] == "approved":
                        store.change(session, other, {**other.data, "rule": {**other.data["rule"], "status": "retired"}})
                from .contracts import executable_rule
                executable_rule(rule)
                rule.update(status="approved", approved_by=account["id"], approved_at=now())
            else:
                rule["status"] = "retired"
            store.change(session, row, {**row.data, "rule": validate_rule(rule)})
            store.audit(session, project_id, account["id"], f"rule.{action}", row.id, {"rule_id": rule["id"], "version": rule["version"]})
            return {"rule": public(row)}

    @app.post("/api/v1/projects/{project_id}/retrieve")
    def retrieve_rules(project_id: str, body: dict = Body(...), account=Depends(user)):
        from .knowledge import retrieve
        require_fields(body, ["query", "task_id"], ["query", "task_id"])
        with store.session() as session:
            access(session, project_id, account)
            rules = [r.data["rule"] for r in store.list(session, project_id, "rule")]
            result = retrieve(body["query"], body["task_id"], rules, project_id)
            for rule in result.get("rules", []):
                runner.source_valid(session, project_id, rule["source_sha256"])
            return {"retrieval": result}

    def new_run(session, project_id, body, account_id):
        task = body.get("task_id", "gravity-full")
        if not isinstance(task, str) or task not in REQUIRED:
            raise ValueError("Select a registered task")
        if body.get("snapshot_id"):
            resource(session, project_id, "snapshot", body["snapshot_id"])
        if body.get("compare_to"):
            resource(session, project_id, "snapshot", body["compare_to"])
        if not isinstance(body.get("use_model", False), bool) or not isinstance(body.get("question", ""), str) or len(body.get("question", "")) > 2000:
            raise ValueError("Invalid model route request")
        row = store.add(session, "run", project_id, {**body, "task_id": task, "state": "QUEUED", "status": "NOT VERIFIED", "trace": [], "results": [], "citations": [], "attempts": 0, "created_by": account_id, "workflow_version": WORKFLOW_VERSION, "review_state": "UNREVIEWED"})
        store.audit(session, project_id, account_id, "run.queued", row.id, {"task_id": task, "snapshot_id": body.get("snapshot_id")})
        return row

    @app.post("/api/v1/projects/{project_id}/runs")
    def run(project_id: str, request: Request, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["snapshot_id", "task_id", "question", "use_model", "compare_to"], ["task_id"])
        with store.session.begin() as session:
            access(session, project_id, account, {"engineer", "reviewer"})
            key = request.headers.get("idempotency-key")
            if key and not re.fullmatch(r"[A-Za-z0-9_.-]{8,128}", key):
                raise ValueError("Invalid idempotency key")
            request_hash = digest(body)
            key_id = "idem_" + digest([project_id, account["id"], key]) if key else None
            existing = session.get(Resource, key_id) if key_id else None
            if existing:
                if existing.data["request_hash"] != request_hash:
                    raise HTTPException(409, "Idempotency key was already used for a different request")
                return {"run": public(resource(session, project_id, "run", existing.data["run_id"]))}
            if sum(r.data.get("state") in {"QUEUED", "RUNNING"} for r in store.list(session, project_id, "run")) >= 20:
                raise HTTPException(429, "Project queue is full")
            row = new_run(session, project_id, body, account["id"])
            if key:
                store.add(session, "idempotency", project_id, {"request_hash": request_hash, "run_id": row.id}, key_id)
            return {"run": public(row)}

    @app.post("/api/v1/projects/{project_id}/runs/{run_id}/cancel")
    def cancel_run(project_id: str, run_id: str, account=Depends(user)):
        with store.session.begin() as session:
            access(session, project_id, account, {"engineer", "reviewer"})
            row = resource(session, project_id, "run", run_id)
            if row.data["state"] == "CANCELLED":
                return {"run": public(row)}
            if row.data["state"] not in {"QUEUED", "RUNNING", "WAITING"}:
                raise HTTPException(409, "A terminal completed/error run cannot be cancelled")
            store.change(session, row, {**row.data, "state": "CANCELLED", "status": "NOT VERIFIED", "cancelled_at": now(), "cancelled_by": account["id"], "explanation": "Cancelled by an authorized project member. No engineering approval was issued."})
            store.audit(session, project_id, account["id"], "run.cancelled", run_id)
            return {"run": public(row)}

    @app.get("/api/v1/projects/{project_id}/runs/{run_id}")
    def get_run(project_id: str, run_id: str, account=Depends(user)):
        with store.session() as session:
            project, _ = access(session, project_id, account)
            return {"run": run_view(session, project, resource(session, project_id, "run", run_id))}

    @app.post("/api/v1/projects/{project_id}/runs/{run_id}/resume")
    def resume(project_id: str, run_id: str, body: dict = Body({}), account=Depends(user)):
        require_fields(body, ["snapshot_id", "compare_to"])
        with store.session.begin() as session:
            access(session, project_id, account, {"engineer", "reviewer"})
            previous = resource(session, project_id, "run", run_id)
            if previous.data["state"] in {"QUEUED", "RUNNING"}:
                raise HTTPException(409, "Run is still executing")
            request = {k: previous.data[k] for k in ["snapshot_id", "task_id", "question", "use_model", "compare_to"] if k in previous.data}
            request.update(body)
            request["parent_run_id"] = run_id
            return {"run": public(new_run(session, project_id, request, account["id"]))}

    def verify_run(session, project, row):
        view = run_view(session, project, row)
        if view.get("integrity_status") == "INVALID":
            raise ValueError("Run output integrity failed")
        if row.data.get("output_hash"):
            recalculated = outcome(row.data["results"])
            if digest(recalculated) != row.data["output_hash"] or row.data.get("status") != recalculated["status"] or row.data.get("summary") != recalculated["summary"]:
                raise ValueError("Run output integrity failed")
        if row.data.get("snapshot_id"):
            snapshot = resource(session, project.id, "snapshot", row.data["snapshot_id"])
            if digest(snapshot.data["input"]) != snapshot.data["input_hash"] or row.data.get("input_hash") and row.data["input_hash"] != snapshot.data["input_hash"]:
                raise ValueError("Input snapshot integrity failed")
            source = resource(session, project.id, "file", snapshot.data["file_id"])
            validate_file(store,session,source)
        if row.data.get("compare_to"):
            target = resource(session, project.id, "snapshot", row.data["compare_to"])
            if digest(target.data["input"]) != target.data["input_hash"] or row.data.get("target_hash") and row.data["target_hash"] != target.data["input_hash"]:
                raise ValueError("Target snapshot integrity failed")
            source = resource(session, project.id, "file", target.data["file_id"])
            validate_file(store,session,source)
        if row.data.get("source_hash"):
            store.get_blob(row.data["source_hash"])
        for rid in row.data.get("rule_ids", []):
            rule = resource(session, project.id, "rule", rid)
            runner.source_valid(session, project.id, rule.data["rule"]["source_sha256"])
        return view

    def lineage(session, project_id, row):
        ids = [row.id]
        while row.data.get("parent_run_id"):
            row = resource(session, project_id, "run", row.data["parent_run_id"])
            if row.id in ids or len(ids) >= 100:
                raise ValueError("Invalid or excessive run lineage")
            ids.append(row.id)
        return ids

    @app.post("/api/v1/projects/{project_id}/issues/{issue_id}")
    def update_issue(project_id: str, issue_id: str, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["action", "note", "assignee", "resolution_run_id"], ["action", "note"])
        action = body["action"]
        if not isinstance(action, str) or action not in {"assign", "request_evidence", "resolve"} or not isinstance(body["note"], str) or not 1 <= len(body["note"].strip()) <= 2000:
            raise ValueError("An issue action and explanatory note are required")
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"reviewer"} if action == "resolve" else {"engineer", "reviewer"})
            row = resource(session, project_id, "issue", issue_id)
            if row.data["state"] == "RESOLVED":
                raise HTTPException(409, "Resolved issues are historical; a new failing run creates a new issue")
            data = dict(row.data)
            if action == "assign":
                assignee = body.get("assignee")
                if not isinstance(assignee, str):
                    raise ValueError("Select an engineer or reviewer")
                member = session.get(Membership, (project_id, assignee))
                if not member or member.role not in {"engineer", "reviewer"}:
                    raise ValueError("Assignee must be an engineer/reviewer in this project")
                data["assignee"] = assignee
            elif action == "request_evidence":
                data["state"] = "EVIDENCE_REQUESTED"
            else:
                successor = resource(session, project_id, "run", body.get("resolution_run_id"))
                original = resource(session, project_id, "run", data["source_run_id"])
                current = verify_run(session, project, successor)
                check = next((r for r in successor.data["results"] if r["id"] == data["finding_id"]), None)
                if original.id not in lineage(session, project_id, successor)[1:] or original.data["task_id"] != successor.data["task_id"] or current["stale"] or successor.data["state"] not in {"COMPLETED", "WAITING"} or not check or check["status"] != "PASS":
                    raise HTTPException(409, "Resolution requires the same finding to pass in a current, linked successor run")
                data.update(state="RESOLVED", resolution_run_id=successor.id, resolved_by=account["id"], resolved_at=now())
            if len(data["notes"]) >= 100:
                raise ValueError("Issue note limit reached")
            data["notes"] = [*data["notes"], {"actor": account["id"], "username": account["username"], "at": now(), "action": action, "note": body["note"].strip()}]
            store.change(session, row, data)
            store.audit(session, project_id, account["id"], "issue." + action, row.id, {"resolution_run_id": data.get("resolution_run_id"), "assignee": data.get("assignee")})
            return {"issue": public(row)}

    @app.post("/api/v1/projects/{project_id}/runs/{run_id}/review")
    def review(project_id: str, run_id: str, body: dict = Body(...), account=Depends(user)):
        require_fields(body, ["action", "note"], ["action", "note"])
        if body["action"] not in {"approve", "request_evidence"} or not isinstance(body["note"], str) or not 1 <= len(body["note"].strip()) <= 2000:
            raise ValueError("A review action and note are required")
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"reviewer"})
            row = resource(session, project_id, "run", run_id)
            view = verify_run(session, project, row)
            if body["action"] == "approve" and (view["stale"] or view["status"] != "PASS" or view["state"] != "COMPLETED" or not view.get("output_hash")):
                raise HTTPException(409, "Only a current, complete PASS run can be signed off")
            if body["action"] == "approve":
                chain = lineage(session, project_id, row)
                if any(i.data["source_run_id"] in chain and i.data["state"] != "RESOLVED" for i in store.list(session, project_id, "issue")):
                    raise HTTPException(409, "Resolve the blocking findings in this run lineage before confirmation")
            record = store.add(session, "review", project_id, {"run_id": run_id, "input_hash": row.data.get("input_hash"), "rule_hash": row.data.get("rule_hash"), "actor": account["id"], "username": account["username"], **body})
            store.change(session, row, {**row.data, "review_state": "APPROVED" if body["action"] == "approve" else "EVIDENCE_REQUESTED", "reviews": [*row.data.get("reviews", []), public(record)]})
            store.audit(session, project_id, account["id"], "run.reviewed", run_id, {"action": body["action"], "review_id": record.id})
            return {"review": public(record)}

    @app.post("/api/v1/projects/{project_id}/compare")
    def compare(project_id: str, body: dict = Body(...), account=Depends(user)):
        from .data_tools import compare_snapshots
        require_fields(body, ["before_id", "after_id"], ["before_id", "after_id"])
        with store.session() as session:
            access(session, project_id, account)
            before = resource(session, project_id, "snapshot", body["before_id"])
            after = resource(session, project_id, "snapshot", body["after_id"])
            return {"comparison": compare_snapshots(before.data["input"], after.data["input"])}

    @app.get("/api/v1/projects/{project_id}/runs/{run_id}/report")
    def report(project_id: str, run_id: str, format: str = "html", language:str="en", account=Depends(user)):
        if language not in {"en","zh-CN"}: raise ValueError("Unsupported report language")
        with store.session() as session:
            project, _ = access(session, project_id, account)
            row = resource(session, project_id, "run", run_id)
            view = verify_run(session, project, row)
            if view["state"] in {"QUEUED", "RUNNING"}:
                raise HTTPException(409, "Wait for the run to finish")
            provenance = []
            for side, key in [("input", "snapshot_id"), ("target", "compare_to")]:
                if row.data.get(key):
                    snapshot = resource(session, project_id, "snapshot", row.data[key])
                    source = resource(session, project_id, "file", snapshot.data["file_id"])
                    provenance.append({"side": side, "snapshot_id": snapshot.id, "title": snapshot.data["title"], "input_hash": snapshot.data["input_hash"], "synthetic": snapshot.data["input"].get("synthetic", False), "parent_id": snapshot.data.get("parent_id"), "mapping_note": snapshot.data.get("mapping_note"), "adapter_id": snapshot.data.get("adapter_id"), "adapter_hash": snapshot.data.get("adapter_hash"), "mapping_provenance": snapshot.data.get("provenance", []), "corrections": snapshot.data.get("corrections", []), "filename": source.data["filename"], "source_sha256": source.data["sha256"], "derived_from":source.data.get("derived_from"),"ocr_id":source.data.get("ocr_id"),"ocr_confirmation_hash":source.data.get("confirmation_hash"),"original_pdf_sha256":source.data.get("original_pdf_sha256"),"page_image_sha256":source.data.get("page_image_sha256")})
            chain = lineage(session, project_id, row)
            findings = [public(i) for i in store.list(session, project_id, "issue") if i.data["source_run_id"] in chain]
            if format == "json":
                return JSONResponse({"project": public(project), "run": view, "input_provenance": provenance, "finding_register": findings, "exported_at": now()}, headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'})
            if format != "html":
                raise ValueError("Supported report formats: html, json. Print HTML to PDF.")
            from .reporting import render_report
            markup = render_report(project.data, view, provenance, findings, now(),language=language)
            return HTMLResponse(markup)

    @app.get("/api/v1/model")
    def model_status(account=Depends(user)):
        conf = model.config()
        return {k: v for k, v in conf.items() if k != "base"}

    @app.get("/api/v1/validation")
    def validation(account=Depends(user)):
        records = {}
        names = {"system": "system-evaluation-v12.json" if (ROOT / "docs/system-evaluation-v12.json").is_file() else "system-evaluation-2026-10-07-v11.json", "retrieval": "retrieval-evaluation-v12.json", "model_baseline": "model-evaluation-v1-development.json", "model_development": "model-evaluation-v3-development.json", "model_holdout": "model-evaluation-v12-holdout.json"}
        for key, name in names.items():
            path = ROOT / "docs" / name
            if path.is_file():
                records[key] = json.loads(path.read_text())
        if "system" in records:
            records["system"]["matches_current_tools"] = records["system"].get("tool_fingerprint") == TOOL_FINGERPRINT
        return {"baseline": node_tool("validation"), "records": records, "scope": "Controlled software fixtures and local-model task routing. Not client engineering accuracy or competitive reviewer-time evidence."}

    @app.get("/api/v1/tools")
    def tools(account=Depends(user)):
        from .connector import config
        connection = {k: v for k, v in config().items() if k != "base"}
        return {"tasks": model.TASKS, "workflow_version": WORKFLOW_VERSION, "etabs": {**connection, "live_interoperability": "NOT VERIFIED"}, "model": model_status(account)}

    @app.post("/api/v1/projects/{project_id}/connector/import")
    def connector_import(project_id: str, body: dict = Body(...), account=Depends(user)):
        from .connector import export_snapshot
        require_fields(body, ["model_id", "revision", "profile"], ["model_id", "revision", "profile"])
        with store.session() as session:
            access(session, project_id, account, {"engineer", "reviewer"})
        exported = export_snapshot(**body)
        with store.session.begin() as session:
            # Deduplicate before creating an input revision. The SQLite write
            # reservation prevents two identical concurrent imports from each
            # creating a new snapshot and invalidating a current review.
            if store.engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            project, _ = access(session, project_id, account, {"engineer", "reviewer"})
            if store.engine.dialect.name != "sqlite":
                session.scalar(select(Resource).where(Resource.id == project_id).with_for_update())
            identity = ["contract", "model_id", "revision", "profile", "software_version", "snapshot_sha256"]
            expected_input = json.loads(exported["bytes"])
            expected_hash = digest(expected_input)
            for existing_file in store.list(session, project_id, "file"):
                prior = existing_file.data.get("connector", {})
                if (existing_file.data.get("sha256") == exported["provenance"]["snapshot_sha256"]
                        and all(prior.get(key) == exported["provenance"][key] for key in identity)):
                    store.get_blob(existing_file.data["sha256"])
                    candidate = next((snap for snap in store.list(session, project_id, "snapshot")
                                      if snap.data["file_id"] == existing_file.id
                                      and snap.data.get("input_hash") == expected_hash
                                      and digest(snap.data["input"]) == expected_hash), None)
                    if candidate:
                        store.audit(session, project_id, account["id"], "connector.reused", candidate.id,
                                    {"identity": {key: exported["provenance"][key] for key in identity},
                                     "observed_exported_at": exported["provenance"]["exported_at"]})
                        return {"file": public(existing_file), "snapshot": public(candidate), "reused": True,
                                "observed_connector": exported["provenance"],
                                "interoperability": "This validates the received contract, not the underlying CSI implementation"}
            source = add_file(session, project_id, "connector-export.json", exported["bytes"], account["id"])
            store.change(session, source, {**source.data, "connector": exported["provenance"]})
            snapshot = add_snapshot(session, project, source, {"title": f"CSI export · {body['revision']}"}, account["id"])
            return {"file": public(source), "snapshot": public(snapshot), "reused": False,
                    "observed_connector": exported["provenance"],
                    "interoperability": "This validates the received contract, not the underlying CSI implementation"}

    @app.post("/api/v1/projects/{project_id}/seed")
    def seed(project_id: str, account=Depends(user)):
        from .knowledge import validate_rule
        with store.session.begin() as session:
            project, _ = access(session, project_id, account, {"reviewer"})
            if project.data.get("seeded"):
                raise HTTPException(409, "Controlled examples already exist in this project")
            bundle = node_tool("seed")
            source_text = "\n\n".join(r["source"]["text"] for r in bundle["knowledge"]["rules"])
            knowledge_file = add_file(session, project_id, "synthetic-rules.txt", source_text.encode(), account["id"])
            for rule in bundle["knowledge"]["rules"]:
                normalized = validate_rule({"id": rule["id"], "version": rule["version"], "title": rule["source"]["title"], "text": rule["source"]["text"], "locator": rule["source"]["locator"], "task_ids": rule["taskIds"], "check_ids": ["COMB-001"] if rule["id"] == "COMB-001" else rule["checkIds"], "status": "approved", "authority": "synthetic", "source_sha256": knowledge_file.data["sha256"], "approved_by": "synthetic-fixture-loader", "approved_at": now(), "project_id": project_id})
                store.add(session, "rule", project_id, {"rule": normalized, "created_by": account["id"]})
            snapshots = []
            for scenario in ["clean", "issues", "missing", "redistribution"]:
                payload = node_tool("seed", scenario=scenario, profile="gravity")["gravity"]
                source = add_file(session, project_id, f"gravity-{scenario}.json", canonical(payload).encode(), account["id"])
                snapshots.append(add_snapshot(session, project, source, {"title": f"Controlled gravity · {scenario}"}, account["id"]))
            for scenario in ["clean", "mismatch", "missing", "unsupported"]:
                payload = node_tool("seed", scenario=scenario, profile="combination")["combination"]
                source = add_file(session, project_id, f"combination-{scenario}.json", canonical(payload).encode(), account["id"])
                snapshots.append(add_snapshot(session, project, source, {"title": f"Controlled combination · {scenario}"}, account["id"]))
            from .fixtures import advanced_fixtures
            examples, extra_rules = advanced_fixtures(bundle["combination"])
            for index, (title, payload, task_id) in enumerate(examples):
                source = add_file(session, project_id, f"controlled-profile-{index + 1}.json", canonical(payload).encode(), account["id"])
                snap = add_snapshot(session, project, source, {"title": title, "input": payload, "mapping_note": "Exact controlled fixture JSON; no inferred values"}, account["id"])
                store.change(session, snap, {**snap.data, "suggested_task": task_id})
                snapshots.append(snap)
            for template in extra_rules:
                source = add_file(session, project_id, template["id"].lower() + "-fixture-rule.txt", template["text"].encode(), account["id"])
                rule = validate_rule({"id": template["id"], "version": "CONTROLLED-1", "title": template["title"], "text": template["text"], "locator": "Controlled fixture source / paragraph 1", "task_ids": [template["task"]], "check_ids": [template["id"]], "status": "approved", "authority": "synthetic", "source_sha256": source.data["sha256"], "approved_by": "synthetic-fixture-loader", "approved_at": now(), "project_id": project_id, "parameters": template["parameters"]})
                store.add(session, "rule", project_id, {"rule": rule, "created_by": account["id"]})
            store.change(session, project, {**project.data, "seeded": True, "active_snapshot_id": snapshots[0].id})
            store.audit(session, project_id, account["id"], "synthetic.seeded", project_id, {"snapshots": len(snapshots), "rules": 12})
            return {"snapshots": [public(s) for s in snapshots], "rules": 12}

    from .adaptation_api import register_adaptation
    register_adaptation(app, store, runner, user, access, resource, require_fields, add_file, add_snapshot, source_contains, new_run, run_view)
    from .ocr_api import register_ocr
    register_ocr(app,store,user,access,resource,require_fields)

    web = ROOT / "web"
    if web.exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="workspace")
    return app
