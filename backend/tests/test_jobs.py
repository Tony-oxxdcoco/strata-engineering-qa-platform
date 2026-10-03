import pytest

from strata.storage import Membership, Resource
from strata.workflow import Runner
from test_api import system


def queued(system, **headers):
    _, client, base, _, seed = system
    return client.post(base + "/runs", json={"task_id": "gravity-full", "snapshot_id": seed["snapshots"][0]["id"]}, headers=headers)


def test_idempotency_same_body_reuses_run_and_changed_body_conflicts(system):
    _, client, base, _, _ = system
    first = queued(system, **{"Idempotency-Key": "repeat-request-123"})
    second = queued(system, **{"Idempotency-Key": "repeat-request-123"})
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    assert client.post(base + "/runs", json={"task_id": "gravity-balance"}, headers={"Idempotency-Key": "repeat-request-123"}).status_code == 409
    assert len(client.get(base + "/dashboard").json()["runs"]) == 1


def test_cancelled_queued_run_never_calculates(system):
    app, client, base, _, _ = system
    rid = queued(system).json()["run"]["id"]
    assert client.post(base + "/runs/" + rid + "/cancel").status_code == 200
    app.state.runner.process(rid)
    result = client.get(base + "/runs/" + rid).json()["run"]
    assert result["state"] == "CANCELLED"
    assert result["status"] == "NOT VERIFIED"
    assert not result["trace"]
    assert client.post(base + "/runs/" + rid + "/review", json={"action": "approve", "note": "No calculation"}).status_code == 409


def test_membership_revocation_blocks_queued_worker(system):
    app, client, base, project, _ = system
    rid = queued(system).json()["run"]["id"]
    with app.state.store.session.begin() as session:
        row = session.get(Resource, rid)
        member = session.get(Membership, (project["id"], row.data["created_by"]))
        member.role = "viewer"
    app.state.runner.process(rid)
    result = client.get(base + "/runs/" + rid).json()["run"]
    assert result["state"] == "ERROR"
    assert result["status"] == "NOT VERIFIED"
    assert not result["trace"]


def test_only_one_worker_can_own_same_storage(system):
    app, _, _, _, _ = system
    first, second = Runner(app.state.store), Runner(app.state.store)
    first.start()
    try:
        with pytest.raises(RuntimeError, match="owns this data directory"):
            second.start()
    finally:
        first.close()
        second.close()
