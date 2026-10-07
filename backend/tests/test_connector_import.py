"""Synthetic HTTP-adapter output imported through the authenticated API."""
import importlib.util
import json
from pathlib import Path

from strata import connector
from strata.storage import Membership
from test_api import system, run

spec = importlib.util.spec_from_file_location("csi_import_mock", Path(__file__).resolve().parents[2] / "scripts/csi-mock-server.py")
mock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock)


def exported():
    payload = mock.payload()
    content = json.dumps(payload["snapshot"], ensure_ascii=False, separators=(",", ":")).encode()
    return {"bytes": content, "provenance": {key: payload[key] for key in
        ("contract", "model_id", "revision", "profile", "software_version", "exported_at", "snapshot_sha256")}}


BODY = {"model_id": "M-SYNTHETIC", "revision": "R-SYNTHETIC", "profile": "synthetic-gravity"}


def test_repeated_identical_data_preserves_active_revision_and_review(system, monkeypatch):
    _, client, base, _, seed = system
    value = exported()
    monkeypatch.setattr(connector, "export_snapshot", lambda **_: value)
    first = client.post(base + "/connector/import", json=BODY)
    assert first.status_code == 200 and first.json()["reused"] is False
    client.post(base + "/snapshots/" + seed["snapshots"][0]["id"] + "/activate")
    result = run(system)
    assert client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": "Synthetic review for repeat-import software regression"}).status_code == 200
    value["provenance"]["exported_at"] = "2026-10-07T00:01:00Z"
    second = client.post(base + "/connector/import", json=BODY)
    assert second.status_code == 200 and second.json()["reused"] is True
    assert second.json()["snapshot"]["id"] == first.json()["snapshot"]["id"]
    assert second.json()["file"]["connector"]["exported_at"] == "2026-10-07T00:00:00Z"
    assert second.json()["observed_connector"]["exported_at"] == "2026-10-07T00:01:00Z"
    dashboard = client.get(base + "/dashboard").json()
    assert dashboard["project"]["active_snapshot_id"] == seed["snapshots"][0]["id"]
    current = client.get(base + "/runs/" + result["id"]).json()["run"]
    assert current["stale"] is False and current["review_state"] == "APPROVED"


def test_same_response_is_deduplicated_only_inside_its_project(system, monkeypatch):
    _, client, base, _, _ = system
    monkeypatch.setattr(connector, "export_snapshot", lambda **_: exported())
    first = client.post(base + "/connector/import", json=BODY).json()
    other = client.post("/api/v1/projects", json={"name": "SYNTHETIC second connector scope"}).json()["project"]
    second = client.post("/api/v1/projects/" + other["id"] + "/connector/import", json=BODY).json()
    assert first["reused"] is False and second["reused"] is False
    assert first["file"]["id"] != second["file"]["id"]
    assert first["snapshot"]["id"] != second["snapshot"]["id"]


def test_software_version_change_is_a_new_provenance_revision(system, monkeypatch):
    _, client, base, _, _ = system
    value = exported()
    monkeypatch.setattr(connector, "export_snapshot", lambda **_: value)
    first = client.post(base + "/connector/import", json=BODY).json()
    value["provenance"]["software_version"] = "SYNTHETIC second exporter version"
    second = client.post(base + "/connector/import", json=BODY).json()
    assert not second["reused"] and first["snapshot"]["id"] != second["snapshot"]["id"]


def test_permissions_are_rechecked_after_connector_response(system, monkeypatch):
    app, client, base, project, _ = system
    account = client.get("/api/v1/auth/me").json()
    before = client.get(base + "/dashboard").json()
    def revoke(**_):
        with app.state.store.session.begin() as session:
            session.get(Membership, (project["id"], account["id"])).role = "viewer"
        return exported()
    monkeypatch.setattr(connector, "export_snapshot", revoke)
    assert client.post(base + "/connector/import", json=BODY).status_code == 403
    after = client.get(base + "/dashboard").json()
    assert len(before["files"]) == len(after["files"])
    assert len(before["snapshots"]) == len(after["snapshots"])
