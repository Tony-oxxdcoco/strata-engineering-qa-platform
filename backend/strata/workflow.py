"""Durable, bounded tool workflow. Only registered deterministic tools decide QA."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import threading
import time
from pathlib import Path

from sqlalchemy import select, update

from .storage import Membership, Resource, canonical, digest, now, public
from . import model
from .usage import reserve_call
from .locking import lock_worker, unlock_worker

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_VERSION = "server-workflow-1.0"
TOOL_FINGERPRINT = digest({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in [ROOT / "dist/engine.js", ROOT / "dist/combinations.js", ROOT / "backend/strata/data_tools.py", ROOT / "backend/strata/knowledge.py", Path(__file__), ROOT / "scripts/tool-bridge.mjs"]})
REQUIRED = {
    "gravity-full": [f"QA-00{i}" for i in range(1, 7)],
    "gravity-distribution": ["QA-003"], "gravity-balance": ["QA-005"],
    "load-combination": ["COMB-001"], "combination-configuration": ["COMB-CONFIG"],
    "handoff": ["HANDOFF"], "seismic-configuration": ["SEISMIC"],
    "mass-source": ["MASS-SOURCE"], "additional-settings": ["SETTINGS"],
}


def node_tool(tool, **arguments):
    payload = canonical({"tool": tool, **arguments})
    if len(payload.encode()) > 2_000_000:
        raise ValueError("Tool input exceeds 2 MB")
    try:
        completed = subprocess.run([os.environ.get("STRATA_NODE", "node"), str(ROOT / "scripts/tool-bridge.mjs")], input=payload, text=True, encoding="utf-8", capture_output=True, timeout=15, cwd=ROOT)
        if len(completed.stdout) > 4_000_000:
            raise ValueError("Tool output exceeds limit")
        result = json.loads(completed.stdout)
        if completed.returncode or result.get("ok") is not True:
            raise ValueError(result.get("error", "Numerical tool failed"))
        return result["result"]
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as error:
        raise ValueError("Numerical tool unavailable or timed out") from error


def outcome(results):
    if not results or any(r.get("status") not in {"PASS", "FAIL", "NOT VERIFIED"} for r in results):
        raise ValueError("Malformed or empty tool findings")
    if any(not isinstance(r.get("id"), str) or not r["id"] for r in results) or len({r["id"] for r in results}) != len(results):
        raise ValueError("Duplicate or missing tool finding IDs")
    counts = {status: sum(r["status"] == status for r in results) for status in ["PASS", "FAIL", "NOT VERIFIED"]}
    return {"status": "FAIL" if counts["FAIL"] else "NOT VERIFIED" if counts["NOT VERIFIED"] else "PASS", "summary": counts, "results": results}


def english_gravity(results):
    names = {"QA-001": "Record uniqueness", "QA-002": "Floor and load-case coverage", "QA-003": "Floor load distribution", "QA-004": "Load-case totals", "QA-005": "Independent vertical reaction balance", "QA-006": "Evidence completeness"}
    passed = {"QA-001": "Model keys and record IDs are unique.", "QA-002": "Every required floor and load-case pair is present.", "QA-003": "Each floor assignment agrees with its independent area and load intensity.", "QA-004": "Each load-case total agrees with the independent brief.", "QA-005": "Independent reactions agree with the load baseline within the supported scope.", "QA-006": "All required evidence roles contain inspectable source content."}
    return [{**r, "name": names[r["id"]], "original_summary": r.get("summary"), "summary": passed[r["id"]] if r["status"] == "PASS" else f"{names[r['id']]} {'failed' if r['status'] == 'FAIL' else 'could not be verified'}. Inspect the item values and original source details below."} for r in results]


class Cancelled(Exception):
    pass


class Runner:
    def __init__(self, store):
        self.store = store
        self.stop = threading.Event()
        self.thread = None
        self.lock_file = None

    def start(self):
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Worker already started")
        self.lock_file = open(self.store.root / "worker.lock", "a+b")
        try:
            lock_worker(self.lock_file)
        except OSError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError("Another STRATA worker owns this data directory")
        # One worker per installation. A crashed process cannot continue writing;
        # attempt counters cap recovery. Multi-process workers are not supported.
        with self.store.session.begin() as session:
            for row in session.scalars(select(Resource).where(Resource.kind == "run", Resource.data["state"].as_string() == "RUNNING")):
                if row.data.get("state") == "RUNNING":
                    data = {**row.data, "state": "QUEUED", "recovered_at": now()}
                    self.store.change(session, row, data)
        self.thread = threading.Thread(target=self.loop, daemon=True, name="strata-worker")
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=50)
        if self.lock_file and not (self.thread and self.thread.is_alive()):
            unlock_worker(self.lock_file)
            self.lock_file.close()
            self.lock_file = None

    def loop(self):
        while not self.stop.wait(.15):
            with self.store.session() as session:
                ids = list(session.scalars(select(Resource.id).where(Resource.kind == "run", Resource.data["state"].as_string() == "QUEUED").order_by(Resource.created_at).limit(20)))
            for run_id in ids:
                if self.stop.is_set():
                    return
                self.process(run_id)

    def save(self, run_id, fields, event=None):
        with self.store.session.begin() as session:
            row = session.get(Resource, run_id)
            if row.data.get("state") == "CANCELLED":
                raise Cancelled()
            data = {**row.data, **fields}
            if event:
                data["trace"] = [*data.get("trace", []), {"at": now(), **event}]
            self.store.change(session, row, data)

    def block(self, run_id, reason, missing=None, infrastructure=False):
        result = {"id": "WORKFLOW-GATE", "status": "NOT VERIFIED", "summary": reason, "details": []}
        self.save(run_id, {**outcome([result]), "state": "ERROR" if infrastructure else "WAITING", "missing": missing or [reason], "explanation": reason, "finished_at": now()}, {"tool": "verify_evidence", "status": "blocked", "reason": reason})

    def source_valid(self, session, project_id, source_hash):
        sources = self.store.list(session, project_id, "file")
        if not any(f.data["sha256"] == source_hash for f in sources):
            raise ValueError("Approved rule source is not present in this project")
        self.store.get_blob(source_hash)

    def process(self, run_id):
        from .knowledge import retrieve, check_coverage
        from .data_tools import verify_combination_configuration, verify_handoff, verify_settings
        try:
            with self.store.session.begin() as session:
                row = session.get(Resource, run_id)
                if not row or row.data.get("state") != "QUEUED":
                    return
                data = dict(row.data)
                member = session.get(Membership, (row.project_id, data.get("created_by")))
                if not member or member.role not in {"engineer", "reviewer"}:
                    self.store.change(session, row, {**data, "state": "ERROR", "status": "NOT VERIFIED", "explanation": "Run owner no longer has engineering access"})
                    return
                if data.get("attempts", 0) >= 3:
                    self.store.change(session, row, {**data, "state": "ERROR", "status": "NOT VERIFIED", "explanation": "Recovery attempt budget exceeded"})
                    return
                self.store.change(session, row, {**data, "state": "RUNNING", "attempts": data.get("attempts", 0) + 1})
                project_id = row.project_id
            selected = data["task_id"]
            routing = {"method": "explicit-selection", "task_id": selected}
            if data.get("use_model"):
                try:
                    reserve_call(self.store, project_id, run_id)
                    routing = model.route(data.get("question", ""))
                    selected = routing["task_id"]
                except ValueError as error:
                    self.save(run_id, {"route": {"method": "local-model", "error": str(error)}}, {"tool": "select_task", "status": "error", "reason": str(error)})
                    self.block(run_id, str(error), ["Select an explicit task or restore the local model"])
                    return
                if selected is None:
                    self.save(run_id, {"route": routing}, {"tool": "select_task", "status": "blocked", "output": routing})
                    self.block(run_id, "Question is unsupported or ambiguous. Select a registered task.")
                    return
            if selected not in REQUIRED:
                self.block(run_id, "Unregistered task")
                return
            self.save(run_id, {"task_id": selected, "route": routing}, {"tool": "select_task", "status": "ok", "output": routing})
            with self.store.session() as session:
                snapshot = session.get(Resource, data.get("snapshot_id"))
                if not snapshot or snapshot.project_id != project_id or snapshot.kind != "snapshot":
                    self.block(run_id, "A project input snapshot is required", ["snapshot"])
                    return
                input_data = snapshot.data["input"]
                if digest(input_data) != snapshot.data["input_hash"]:
                    raise ValueError("Snapshot integrity verification failed")
                source = session.get(Resource, snapshot.data["file_id"])
                if not source or source.project_id != project_id:
                    raise ValueError("Snapshot source is unavailable")
                self.store.get_blob(source.data["sha256"])
                rules = [dict(r.data["rule"], resource_id=r.id) for r in self.store.list(session, project_id, "rule")]
                if input_data.get("synthetic") is not True:
                    rules = [r for r in rules if r["authority"] == "client"]
                # Search is user-facing; execution retrieves its exact required IDs.
                retrieval = retrieve(" ".join(REQUIRED[selected]), selected, rules, project_id, limit=50)
                coverage = check_coverage(retrieval, REQUIRED[selected])
                if retrieval["status"] != "FOUND" or coverage["status"] != "FOUND":
                    self.block(run_id, retrieval.get("reason") if retrieval["status"] != "FOUND" else coverage.get("reason"), ["approved rules: " + ", ".join(REQUIRED[selected])])
                    return
                for rule in retrieval["rules"]:
                    self.source_valid(session, project_id, rule["source_sha256"])
                rule_hash = digest(retrieval["rules"])
                # Existing fixed-tolerance numerical tools are approved only for
                # the seeded synthetic profile. Client profiles use explicit
                # parameter tools until their numerical method is reviewed.
                if selected in {"gravity-full", "gravity-distribution", "gravity-balance", "load-combination"} and (input_data.get("synthetic") is not True or any(r["authority"] != "synthetic" for r in retrieval["rules"])):
                    self.block(run_id, "The legacy arithmetic profile is synthetic-only. Register and validate a client calculation profile first.")
                    return
                rule_ids = [r["resource_id"] for r in retrieval["rules"]]
                compare = session.get(Resource, data.get("compare_to")) if data.get("compare_to") else None
                if compare and (compare.kind != "snapshot" or compare.project_id != project_id):
                    raise ValueError("Invalid comparison snapshot")
                target = compare.data["input"] if compare else None
                if compare:
                    if digest(target) != compare.data["input_hash"]:
                        raise ValueError("Comparison snapshot integrity failed")
                    compare_source = session.get(Resource, compare.data["file_id"])
                    self.store.get_blob(compare_source.data["sha256"])
                key = digest({"project": project_id, "input": input_data, "target": target, "rules": retrieval["rules"], "task": selected, "workflow": WORKFLOW_VERSION, "tool_fingerprint": TOOL_FINGERPRINT})
                cached = next((r.data for r in self.store.list(session, project_id, "cache") if r.data.get("key") == key), None)
                if cached and digest(cached["output"]) != cached["output_hash"]:
                    raise ValueError("Cached output integrity verification failed")
            self.save(run_id, {"input_hash": digest(input_data), "rule_hash": rule_hash, "rule_ids": rule_ids, "citations": retrieval["citations"], "cache_key": key, "source_hash": source.data["sha256"], "tool_fingerprint": TOOL_FINGERPRINT, "target_hash": digest(target) if target else None}, {"tool": "retrieve_engineering_rules", "status": "ok", "output": {"rule_ids": rule_ids, "coverage": coverage}})
            self.save(run_id, {}, {"tool": "request_engineering_data", "status": "ok", "output": {"snapshot_id": snapshot.id, "input_hash": digest(input_data), "provider": "stored-file"}})
            started = time.monotonic()
            if cached:
                checked = cached["output"]
            elif selected.startswith("gravity"):
                checked = outcome(english_gravity([r for r in node_tool("gravity", input=input_data)["results"] if r["id"] in REQUIRED[selected]]))
            elif selected == "load-combination":
                checked = outcome(node_tool("combination", input=input_data)["results"])
            else:
                candidates = [r for r in retrieval["rules"] if REQUIRED[selected][0] in r["check_ids"]]
                if len(candidates) != 1:
                    self.block(run_id, "Exactly one applicable parameter rule is required")
                    return
                parameters = {**candidates[0].get("parameters", {}), "approved": True, "id": candidates[0]["id"], "version": candidates[0]["version"]}
                if selected == "combination-configuration":
                    check = verify_combination_configuration(input_data, parameters)
                elif selected == "handoff":
                    if target is None:
                        self.block(run_id, "A target snapshot is required for handoff verification", ["compare_to"])
                        return
                    check = verify_handoff(input_data, target, parameters)
                else:
                    check = verify_settings(input_data, parameters)
                checked = outcome([{**check, "id": REQUIRED[selected][0], "summary": check.get("reason", "")}])
            expected_ids = {c["id"] for c in input_data.get("combinations", [])} if selected == "load-combination" else set(REQUIRED[selected])
            actual_ids = [r.get("id") for r in checked.get("results", [])]
            if not expected_ids or set(actual_ids) != expected_ids or len(actual_ids) != len(expected_ids) or checked != outcome(checked["results"]):
                raise ValueError("Deterministic tool returned incomplete or inconsistent required findings")
            elapsed = round((time.monotonic() - started) * 1000, 3)
            self.save(run_id, {"cache_hit": bool(cached), "calculation_ms": elapsed}, {"tool": "run_deterministic_check", "status": "ok", "duration_ms": elapsed, "cache_hit": bool(cached), "output": checked})
            # Re-read all rules/sources before final publication. Approval may
            # have changed while a tool was working.
            with self.store.session.begin() as session:
                member = session.get(Membership, (project_id, data["created_by"]))
                if not member or member.role not in {"engineer", "reviewer"}:
                    raise ValueError("Run owner engineering access was revoked during execution")
                current = [dict(session.get(Resource, rid).data["rule"], resource_id=rid) for rid in rule_ids]
                if digest(current) != rule_hash or any(r["status"] != "approved" for r in current):
                    raise ValueError("Rule approval changed during execution")
                for rule in current:
                    self.source_valid(session, project_id, rule["source_sha256"])
                self.store.get_blob(source.data["sha256"])
                if compare:
                    self.store.get_blob(compare_source.data["sha256"])
                    persisted_target = session.get(Resource, compare.id)
                    if digest(persisted_target.data["input"]) != compare.data["input_hash"]:
                        raise ValueError("Target snapshot changed during execution")
                persisted_source = session.get(Resource, snapshot.id)
                if digest(persisted_source.data["input"]) != snapshot.data["input_hash"]:
                    raise ValueError("Input snapshot changed during execution")
                if not cached:
                    self.store.add(session, "cache", project_id, {"key": key, "output": checked, "output_hash": digest(checked)})
            explanation = "\n".join([f"{selected}: {checked['status']}.", *[f"{r['id']}: {r['status']}. {r.get('summary', '')}" for r in checked["results"]], "Findings are limited to the selected checks and supplied evidence. Rule approval records a software review, not structural certification."])
            self.save(run_id, {**checked, "state": "WAITING" if checked["status"] == "NOT VERIFIED" else "COMPLETED", "missing": [r.get("summary", r["id"]) for r in checked["results"] if r["status"] == "NOT VERIFIED"], "explanation": explanation, "finished_at": now(), "output_hash": digest(checked)}, {"tool": "verify_evidence", "status": "ok", "source_count": len(retrieval["citations"])})
            self.save(run_id, {}, {"tool": "compose_response", "status": "ok", "method": "verified-tool-template"})
            with self.store.session.begin() as session:
                for finding in checked["results"]:
                    if finding["status"] != "PASS":
                        issue_id = "issue_" + digest([run_id, finding["id"]])
                        if not session.get(Resource, issue_id):
                            self.store.add(session, "issue", project_id, {"source_run_id": run_id, "finding_id": finding["id"], "title": finding.get("name", finding["id"]), "technical_status": finding["status"], "state": "OPEN", "assignee": None, "notes": [], "resolution_run_id": None}, issue_id)
                self.store.audit(session, project_id, "workflow", "run.completed", run_id, {"status": checked["status"], "output_hash": digest(checked)})
        except Cancelled:
            return
        except Exception as error:
            # Tool and infrastructure errors never get converted into FAIL/PASS.
            try:
                self.block(run_id, str(error)[:500] if isinstance(error, ValueError) else "Workflow infrastructure error; consult server logs", infrastructure=True)
            except Cancelled:
                return
