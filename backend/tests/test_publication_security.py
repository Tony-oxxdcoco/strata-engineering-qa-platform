"""Faults at the actual publication boundary, beyond ideal-input QA tests."""
import pytest

from strata.storage import Membership, Resource
from test_api import system, run


@pytest.mark.parametrize("interruption", ["revoke", "cancel", "retire-rule"])
def test_final_boundary_rechecks_rights_cancel_and_rule_approval(system, monkeypatch, interruption):
    app, client, base, project, _ = system
    original = app.state.runner.publish

    def interrupt(run_id, *args, **kwargs):
        if interruption == "cancel":
            assert client.post(base + "/runs/" + run_id + "/cancel").status_code == 200
        else:
            with app.state.store.session.begin() as session:
                row = session.get(Resource, run_id)
                if interruption == "revoke":
                    member = session.get(Membership, (project["id"], row.data["created_by"]))
                    member.role = "viewer"
                else:
                    rule = session.get(Resource, row.data["rule_ids"][0])
                    app.state.store.change(session, rule, {**rule.data, "rule": {**rule.data["rule"], "status": "retired"}})
        return original(run_id, *args, **kwargs)

    monkeypatch.setattr(app.state.runner, "publish", interrupt)
    result = run(system)
    assert result["status"] == "NOT VERIFIED"
    assert result["state"] == ("CANCELLED" if interruption == "cancel" else "ERROR")
    with app.state.store.session() as session:
        assert not app.state.store.list(session, project["id"], "cache")
        assert not any(a["action"] == "run.completed" for a in app.state.store.audit_chain(session, project["id"])["items"])


@pytest.mark.parametrize("failure", ["issue", "audit"])
def test_failed_publication_rolls_back_result_cache_findings_and_audit(system, monkeypatch, failure):
    app, _, _, project, _ = system
    if failure == "issue":
        original = app.state.store.add
        def add(session, kind, *args, **kwargs):
            if kind == "issue":
                raise ValueError("Synthetic issue-storage failure")
            return original(session, kind, *args, **kwargs)
        monkeypatch.setattr(app.state.store, "add", add)
    else:
        original = app.state.store.audit
        def audit(session, project_id, actor, action, *args, **kwargs):
            if action == "run.completed":
                raise ValueError("Synthetic audit-storage failure")
            return original(session, project_id, actor, action, *args, **kwargs)
        monkeypatch.setattr(app.state.store, "audit", audit)
    result = run(system, 1)
    assert result["state"] == "ERROR" and result["status"] == "NOT VERIFIED"
    with app.state.store.session() as session:
        assert not app.state.store.list(session, project["id"], "cache")
        assert not app.state.store.list(session, project["id"], "issue")
        assert not any(a["action"] == "run.completed" for a in app.state.store.audit_chain(session, project["id"])["items"])


def test_completed_run_cannot_be_published_twice_by_worker_retry(system):
    app, _, _, project, _ = system
    result = run(system, 1)
    with app.state.store.session() as session:
        before = {kind: len(app.state.store.list(session, project["id"], kind)) for kind in ("run", "cache", "issue")}
    app.state.runner.process(result["id"])
    with app.state.store.session() as session:
        assert before == {kind: len(app.state.store.list(session, project["id"], kind)) for kind in before}
        events = app.state.store.audit_chain(session, project["id"])["items"]
        assert len([a for a in events if a["action"] == "run.completed" and a["target"] == result["id"]]) == 1
