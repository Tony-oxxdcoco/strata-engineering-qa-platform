"""A valid blob at a different source identity must not preserve a verified PASS."""
from strata.storage import Resource
from test_api import system, run
from test_adversarial import handoff_run


def replace_source_with_other_valid_blob(app, source_id, other_id):
    with app.state.store.session.begin() as session:
        source = session.get(Resource, source_id)
        other = session.get(Resource, other_id)
        assert source.data["sha256"] != other.data["sha256"]
        app.state.store.get_blob(other.data["sha256"])
        app.state.store.change(session, source, {**source.data, "sha256": other.data["sha256"]})


def test_valid_source_replacement_invalidates_historical_pass_and_confirmation(system):
    app, client, base, _, seed = system
    result = run(system)
    replace_source_with_other_valid_blob(app, seed["snapshots"][0]["file_id"], seed["snapshots"][1]["file_id"])
    visible = client.get(base + "/runs/" + result["id"]).json()["run"]
    assert visible["status"] == "NOT VERIFIED" and visible["integrity_status"] == "INVALID"
    assert client.get(base + "/runs/" + result["id"] + "/report").status_code == 422
    assert client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": "Must reject changed original source"}).status_code in {409, 422}


def test_source_metadata_replacement_before_publication_cannot_commit_pass(system, monkeypatch):
    app, _, _, _, seed = system
    original = app.state.runner.publish
    def replace(run_id, *args, **kwargs):
        replace_source_with_other_valid_blob(app, seed["snapshots"][0]["file_id"], seed["snapshots"][1]["file_id"])
        return original(run_id, *args, **kwargs)
    monkeypatch.setattr(app.state.runner, "publish", replace)
    result = run(system)
    with app.state.store.session() as session:
        row = session.get(Resource, result["id"])
        assert row.data["state"] == "ERROR" and row.data["status"] == "NOT VERIFIED"


def test_handoff_target_source_metadata_replacement_invalidates_report(system):
    app, client, base, _, _ = system
    result, sources, _ = handoff_run(system)
    replace_source_with_other_valid_blob(app, sources[1]["id"], sources[0]["id"])
    visible = client.get(base + "/runs/" + result["id"]).json()["run"]
    assert visible["status"] == "NOT VERIFIED" and visible["integrity_status"] == "INVALID"
    assert client.get(base + "/runs/" + result["id"] + "/report?format=json").status_code == 422


def test_explicit_empty_or_null_mapping_never_falls_back_to_parsed_source(system):
    app,client,base,project,seed=system
    before=client.get(base+'/dashboard').json()
    for value in ({},None):
        response=client.post(base+'/snapshots',json={'file_id':seed['snapshots'][0]['file_id'],'input':value,'mapping_note':'Explicit synthetic empty mapping must be rejected'})
        assert response.status_code==422
    after=client.get(base+'/dashboard').json()
    assert len(after['snapshots'])==len(before['snapshots'])
    assert after['project']['active_snapshot_id']==before['project']['active_snapshot_id']
