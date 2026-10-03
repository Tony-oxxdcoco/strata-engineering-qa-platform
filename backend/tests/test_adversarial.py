"""Integration regressions: incomplete tools and stale/corrupt handoff evidence."""
import base64
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strata import workflow
from strata.storage import Resource
from test_api import system, run


def upload(client, base, filename, content):
    response = client.post(base + "/files", json={"filename": filename, "content_base64": base64.b64encode(content).decode()})
    assert response.status_code == 200, response.text
    return response.json()["file"]


def handoff_run(system):
    app, client, base, project, _ = system
    snapshots = []
    files = []
    for revision in ("SOURCE-A", "TARGET-B"):
        payload = {"synthetic": True, "project": {"revision": revision}, "units": {"force": "kN"}, "assignment": {"force": 100}}
        source = upload(client, base, revision + ".json", json.dumps(payload).encode())
        response = client.post(base + "/snapshots", json={"file_id": source["id"], "input": payload, "mapping_note": "Explicit exact synthetic scalar mapping"})
        assert response.status_code == 200, response.text
        files.append(source)
        snapshots.append(response.json()["snapshot"])
    text = "HANDOFF: compare only the explicit source and target force field with the listed tolerance."
    source = upload(client, base, "handoff-rule.txt", text.encode())
    parameters = {"source_revision": "SOURCE-A", "target_revision": "TARGET-B",
        "required_source_paths": ["/assignment/force"], "required_target_paths": ["/assignment/force"],
        "mappings": [{"id": "force", "source_path": "/assignment/force", "target_path": "/assignment/force",
            "source_unit_path": "/units/force", "target_unit_path": "/units/force", "comparison_unit": "kN",
            "absolute_tolerance": 0, "relative_tolerance": 0}]}
    rule = {"id": "HANDOFF", "version": "2", "title": "Synthetic explicit transfer", "text": text,
        "locator": "line 1", "task_ids": ["handoff"], "check_ids": ["HANDOFF"], "authority": "synthetic",
        "status": "draft", "source_sha256": source["sha256"], "project_id": project["id"], "parameters": parameters}
    response = client.post(base + "/rules", json={"rule": rule})
    assert response.status_code == 200, response.text
    rule_id = response.json()["rule"]["id"]
    assert client.post(base + "/rules/" + rule_id + "/approve").status_code == 200
    queued = client.post(base + "/runs", json={"snapshot_id": snapshots[0]["id"], "compare_to": snapshots[1]["id"], "task_id": "handoff"})
    assert queued.status_code == 200, queued.text
    run_id = queued.json()["run"]["id"]
    app.state.runner.process(run_id)
    result = client.get(base + "/runs/" + run_id).json()["run"]
    assert result["status"] == "PASS", result
    assert result["stale"] is False
    return result, files, snapshots


def test_missing_required_tool_results_cannot_be_a_full_pass(system, monkeypatch):
    actual = workflow.node_tool
    def missing_results(tool, **arguments):
        if tool == "gravity":
            return {"results": [{"id": "QA-001", "status": "PASS", "summary": "Only one check returned", "details": []}]}
        return actual(tool, **arguments)
    monkeypatch.setattr(workflow, "node_tool", missing_results)
    result = run(system)
    assert result["status"] == "NOT VERIFIED", result
    assert result["state"] in {"ERROR", "WAITING"}


def test_handoff_target_source_corruption_blocks_old_report(system):
    app, client, base, _, _ = system
    result, files, _ = handoff_run(system)
    (app.state.store.blobs / files[1]["sha256"]).write_bytes(b"corrupt target source")
    response = client.get(base + "/runs/" + result["id"] + "/report?format=json")
    assert response.status_code == 422, response.text


def test_handoff_snapshot_mutation_blocks_old_review_and_export(system):
    app, client, base, _, _ = system
    result, _, snapshots = handoff_run(system)
    with app.state.store.session.begin() as session:
        target = session.get(Resource, snapshots[1]["id"])
        data = copy.deepcopy(target.data)
        data["input"]["assignment"]["force"] = 0
        app.state.store.change(session, target, data)
    assert client.get(base + "/runs/" + result["id"] + "/report?format=json").status_code == 422
    assert client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": "Must reject corrupt input"}).status_code in {409, 422}


def test_declared_output_status_cannot_disagree_with_hashed_findings(system):
    app, client, base, _, seed = system
    client.post(base + "/snapshots/" + seed["snapshots"][1]["id"] + "/activate")
    result = run(system, 1)
    assert result["status"] == "FAIL"
    with app.state.store.session.begin() as session:
        row = session.get(Resource, result["id"])
        # Simulate corrupt redundant status, leaving findings and their hash intact.
        app.state.store.change(session, row, {**row.data, "status": "PASS"})
    assert client.get(base + "/runs/" + result["id"] + "/report?format=json").status_code == 422
    assert client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": "Must not approve inconsistent summary"}).status_code in {409, 422}
