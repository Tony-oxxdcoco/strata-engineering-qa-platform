import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from strata.app import create_app
from strata.storage import Resource, digest


@pytest.fixture
def system(tmp_path):
    app = create_app(tmp_path, testing=True, worker=False)
    with TestClient(app) as client:
        auth = client.post("/api/v1/auth/bootstrap", json={"username": "reviewer", "password": "long-test-password"})
        assert auth.status_code == 200
        client.headers["Authorization"] = "Bearer " + auth.json()["token"]
        project = client.post("/api/v1/projects", json={"name": "Controlled acceptance"}).json()["project"]
        base = "/api/v1/projects/" + project["id"]
        seed = client.post(base + "/seed")
        assert seed.status_code == 200, seed.text
        yield app, client, base, project, seed.json()


def run(system, index=0, task="gravity-full", **extra):
    app, client, base, _, seed = system
    response = client.post(base + "/runs", json={"snapshot_id": seed["snapshots"][index]["id"], "task_id": task, **extra})
    assert response.status_code == 200, response.text
    rid = response.json()["run"]["id"]
    app.state.runner.process(rid)
    return client.get(base + "/runs/" + rid).json()["run"]


def test_correct_error_missing_known_outcomes(system):
    assert run(system)["status"] == "PASS"
    assert run(system, 1)["status"] == "FAIL"
    missing = run(system, 2)
    assert missing["status"] == "NOT VERIFIED"
    assert missing["state"] == "WAITING"
    assert missing["missing"]


def test_combination_arithmetic_remains_separate(system):
    assert run(system, 4, "load-combination")["status"] == "PASS"
    assert run(system, 5, "load-combination")["status"] == "FAIL"
    assert run(system, 6, "load-combination")["status"] == "NOT VERIFIED"
    assert run(system, 4, "combination-configuration")["status"] == "NOT VERIFIED"


def test_cache_reuses_only_identical_inputs(system):
    first = run(system)
    second = run(system)
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["results"] == first["results"]
    assert run(system, 1)["cache_hit"] is False


def test_cache_corruption_never_publishes_pass(system):
    app, _, _, project, _ = system
    run(system)
    with app.state.store.session.begin() as session:
        cache = app.state.store.list(session, project["id"], "cache")[0]
        app.state.store.change(session, cache, {**cache.data, "output_hash": "0" * 64})
    result = run(system)
    assert result["status"] == "NOT VERIFIED"
    assert "integrity" in result["explanation"]


def test_missing_rules_stop_before_calculation(system):
    _, client, base, _, _ = system
    rules = client.get(base + "/dashboard").json()["rules"]
    target = next(r for r in rules if r["rule"]["id"] == "QA-003")
    assert client.post(base + "/rules/" + target["id"] + "/retire").status_code == 200
    result = run(system)
    assert result["state"] == "WAITING"
    assert not any(t["tool"] == "run_deterministic_check" for t in result["trace"])


def test_resume_creates_successor_without_rewriting_original(system):
    app, client, base, _, seed = system
    original = run(system, 2)
    response = client.post(base + "/runs/" + original["id"] + "/resume", json={"snapshot_id": seed["snapshots"][0]["id"]})
    new_id = response.json()["run"]["id"]
    app.state.runner.process(new_id)
    successor = client.get(base + "/runs/" + new_id).json()["run"]
    assert successor["status"] == "PASS"
    assert successor["parent_run_id"] == original["id"]
    assert client.get(base + "/runs/" + original["id"]).json()["run"]["status"] == "NOT VERIFIED"


def test_review_requires_current_complete_pass(system):
    _, client, base, _, seed = system
    result = run(system)
    response = client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": "Compared the controlled reference values"})
    assert response.status_code == 200
    client.post(base + "/snapshots/" + seed["snapshots"][1]["id"] + "/activate")
    assert client.get(base + "/runs/" + result["id"]).json()["run"]["review_state"] == "STALE"
    assert client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": "Approve again"}).status_code == 409
    failed = run(system, 1)
    assert client.post(base + "/runs/" + failed["id"] + "/review", json={"action": "approve", "note": "Override"}).status_code == 409
    assert client.post(base + "/runs/" + failed["id"] + "/review", json={"action": "request_evidence", "note": "Supply a corrected export"}).status_code == 200
    assert client.get(base + "/runs/" + failed["id"]).json()["run"]["status"] == "FAIL"


def test_source_tamper_blocks_execution_and_export(system):
    app, client, base, _, seed = system
    result = run(system)
    with app.state.store.session() as session:
        snapshot = session.get(Resource, seed["snapshots"][0]["id"])
        source = session.get(Resource, snapshot.data["file_id"])
        rule = session.get(Resource, result["rule_ids"][0])
        hashes = [source.data["sha256"], rule.data["rule"]["source_sha256"]]
    for sha in hashes:
        path = app.state.store.blobs / sha
        original_bytes = path.read_bytes()
        try:
            path.write_bytes(b"modified")
            assert run(system)["status"] == "NOT VERIFIED"
            assert client.get(base + "/runs/" + result["id"] + "/report").status_code == 422
            visible = client.get(base + "/runs/" + result["id"]).json()["run"]
            assert visible["status"] == "NOT VERIFIED"
            assert visible["integrity_status"] == "INVALID"
            assert all(r["status"] == "NOT VERIFIED" for r in visible["results"])
        finally:
            path.write_bytes(original_bytes)
        assert client.get(base + "/runs/" + result["id"]).json()["run"]["status"] == "PASS"


def test_report_has_versions_and_integrity_bound_content(system):
    app, client, base, _, _ = system
    result = run(system)
    html = client.get(base + "/runs/" + result["id"] + "/report")
    assert html.status_code == 200
    assert result["input_hash"] in html.text
    assert "Synthetic fixtures are not client engineering validation" in html.text
    exported = client.get(base + "/runs/" + result["id"] + "/report?format=json").json()
    assert exported["run"]["results"] == result["results"]
    with app.state.store.session.begin() as session:
        row = session.get(Resource, result["id"])
        data = json.loads(json.dumps(row.data))
        data["results"][0]["status"] = "FAIL"
        app.state.store.change(session, row, data)
    assert client.get(base + "/runs/" + result["id"] + "/report").status_code == 422


def test_permissions_and_cross_project_ids(system):
    _, client, base, _, seed = system
    original_token = client.headers["Authorization"]
    new = client.post("/api/v1/users", json={"username": "outsider", "password": "other-long-password"}).json()["user"]
    login = client.post("/api/v1/auth/login", json={"username": "outsider", "password": "other-long-password"})
    client.headers["Authorization"] = "Bearer " + login.json()["token"]
    assert client.get(base + "/dashboard").status_code == 404
    assert client.get(base + "/files/" + seed["snapshots"][0]["file_id"] + "/content").status_code == 404
    own = client.post("/api/v1/projects", json={"name": "Other project"}).json()["project"]
    assert client.post("/api/v1/projects/" + own["id"] + "/runs", json={"task_id": "gravity-full", "snapshot_id": seed["snapshots"][0]["id"]}).status_code == 404
    client.headers["Authorization"] = original_token
    assert client.post(base + "/members", json={"user_id": new["id"], "role": "viewer"}).status_code == 200
    client.headers["Authorization"] = "Bearer " + login.json()["token"]
    assert client.get(base + "/dashboard").status_code == 200
    assert client.post(base + "/runs", json={"task_id": "gravity-full"}).status_code == 403
    assert client.post(base + "/files", json={"filename": "a.txt", "content_base64": base64.b64encode(b"a").decode()}).status_code == 403


def test_rule_import_forces_draft_and_matches_original(system):
    _, client, base, project, _ = system
    text = "The mass setting must use the approved source."
    uploaded = client.post(base + "/files", json={"filename": "client-rule.txt", "content_base64": base64.b64encode(text.encode()).decode()})
    assert uploaded.status_code == 200
    source = uploaded.json()["file"]
    rule = {"id": "CLIENT-MASS", "version": "1", "title": "Mass settings", "text": text, "locator": "line 1", "task_ids": ["mass-source"], "check_ids": ["MASS-SOURCE"], "status": "approved", "authority": "client", "source_sha256": source["sha256"], "project_id": project["id"], "approved_by": "fake", "approved_at": "2026-10-03T00:00:00Z", "parameters": {"settings": [{"path": "/mass/source", "operator": "eq", "value": "SDL"}]}}
    response = client.post(base + "/rules", json={"rule": rule})
    assert response.status_code == 200, response.text
    stored = response.json()["rule"]
    assert stored["rule"]["status"] == "draft"
    assert stored["rule"]["approved_by"] is None
    found = client.post(base + "/retrieve", json={"query": "mass setting", "task_id": "mass-source"}).json()["retrieval"]
    assert all(r["id"] != "CLIENT-MASS" for r in found["rules"])
    assert client.post(base + "/rules/" + stored["id"] + "/approve").status_code == 200
    found = client.post(base + "/retrieve", json={"query": "mass setting", "task_id": "mass-source"}).json()["retrieval"]
    assert found["status"] == "FOUND"
    assert any(r["id"] == "CLIENT-MASS" for r in found["rules"])
    rule["id"] = "FORGED-EXCERPT"
    rule["text"] = "A fabricated engineering statement"
    assert client.post(base + "/rules", json={"rule": rule}).status_code == 422


def test_new_client_settings_execute_without_synthetic_flag(system):
    app, client, base, project, _ = system
    text = "Check mass source equals SDL."
    file = client.post(base + "/files", json={"filename": "rule.txt", "content_base64": base64.b64encode(text.encode()).decode()}).json()["file"]
    rule = {"id": "MASS-CLIENT", "version": "1", "title": "Mass checklist", "text": text, "locator": "line 1", "task_ids": ["mass-source"], "check_ids": ["MASS-SOURCE"], "authority": "client", "status": "draft", "source_sha256": file["sha256"], "project_id": project["id"], "parameters": {"settings": [{"path": "/mass/source", "operator": "eq", "value": "SDL"}]}}
    created = client.post(base + "/rules", json={"rule": rule}).json()["rule"]
    client.post(base + "/rules/" + created["id"] + "/approve")
    payload = {"configuration_complete": True, "mass": {"source": "SDL"}}
    upload = client.post(base + "/files", json={"filename": "settings.json", "content_base64": base64.b64encode(json.dumps(payload).encode()).decode()}).json()["file"]
    snap = client.post(base + "/snapshots", json={"file_id": upload["id"], "input": payload, "mapping_note": "Exact mapping of settings JSON"})
    assert snap.status_code == 200, snap.text
    row = client.post(base + "/runs", json={"task_id": "mass-source", "snapshot_id": snap.json()["snapshot"]["id"]}).json()["run"]
    app.state.runner.process(row["id"])
    result = client.get(base + "/runs/" + row["id"]).json()["run"]
    assert result["status"] == "PASS", result


def test_audit_chain_and_restart_persistence(system, tmp_path):
    app, client, base, project, _ = system
    result = run(system)
    dashboard = client.get(base + "/dashboard").json()
    assert dashboard["audit"]["valid"]
    assert any(e["action"] == "run.completed" for e in dashboard["audit"]["items"])
    restored = create_app(app.state.store.root, testing=True, worker=False)
    with TestClient(restored) as reopened:
        reopened.headers["Authorization"] = client.headers["Authorization"]
        assert reopened.get(base + "/runs/" + result["id"]).json()["run"]["status"] == "PASS"


def test_interrupted_job_recovery_is_bounded(system):
    app, client, base, _, seed = system
    row = client.post(base + "/runs", json={"task_id": "gravity-full", "snapshot_id": seed["snapshots"][0]["id"]}).json()["run"]
    with app.state.store.session.begin() as session:
        stored = session.get(Resource, row["id"])
        app.state.store.change(session, stored, {**stored.data, "state": "RUNNING", "attempts": 1})
    app.state.runner.start()
    for _ in range(50):
        result = client.get(base + "/runs/" + row["id"]).json()["run"]
        if result["state"] not in {"QUEUED", "RUNNING"}:
            break
        time.sleep(.05)
    app.state.runner.close()
    assert result["status"] == "PASS"
    assert result["attempts"] == 2
    assert result["recovered_at"]


def test_csrf_host_upload_limits_and_logout(system):
    _, client, base, _, _ = system
    assert client.post(base + "/runs", json={"task_id": "gravity-full"}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/v1/health", headers={"Host": "attacker.example"}).status_code == 400
    assert client.post(base + "/files", json={"filename": "../outside.txt", "content_base64": "YQ=="}).status_code == 422
    assert client.post(base + "/files", json={"filename": "a.txt", "content_base64": "!invalid"}).status_code == 422
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get(base + "/dashboard").status_code == 401
