"""Published preparation uses normal API gates and does not manufacture results."""
import importlib.util
from pathlib import Path
import secrets
import pytest
from fastapi.testclient import TestClient
from strata.app import create_app
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('week5_prepare',ROOT/'scripts/prepare-week5.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_prepared_cases_are_independent_and_start_without_runs(tmp_path):
    app=create_app(tmp_path,testing=True,worker=False)
    with TestClient(app) as client:
        auth=client.post('/api/v1/auth/bootstrap',json={'username':'week5-test','password':secrets.token_urlsafe(20)})
        assert auth.status_code==200
        client.headers['Authorization']='Bearer '+auth.json()['token']
        record=module.prepare(client)
        base='/api/v1/projects/'+record['project_id']
        dashboard=client.get(base+'/dashboard').json()
        assert len(dashboard['snapshots'])==3 and not dashboard['runs']
        assert record['runs_precomputed']==0 and record['model_live'] is False
        assert len(record['cases'])==3
        rule=dashboard['rules'][0]['rule']
        assert rule['status']=='draft' and rule['authority']=='synthetic' and not rule.get('approved_by')
        cases=client.get(base+'/cases').json()['items']
        assert {c['case']['expected']['status'] for c in cases}=={'PASS','FAIL','NOT VERIFIED'}
        assert all(c['case']['truth']['independent'] is True for c in cases)
        # Re-running cannot delete or overwrite a previous rehearsal project.
        with pytest.raises(ValueError,match='existing projects are never deleted'):module.prepare(client)
        assert client.get(base+'/dashboard').json()==dashboard

def test_http_instance_mismatch_blocks_preparation_before_auth(tmp_path,monkeypatch):
    nonce='a'*32
    monkeypatch.setenv('STRATA_WEEK5_INSTANCE',nonce)
    app=create_app(tmp_path,testing=True,worker=False)
    with TestClient(app) as client:
        assert client.get('/api/v1/health').json()['week5_instance']==nonce
        module.verify_demo_instance(client,nonce)
        with pytest.raises(ValueError,match='no login or preparation was sent'):
            module.verify_demo_instance(client,'b'*32)
        assert client.get('/api/v1/auth/setup').json()['needs_setup'] is True

def test_ordinary_app_health_has_no_demo_directory_or_marker(tmp_path,monkeypatch):
    monkeypatch.delenv('STRATA_WEEK5_INSTANCE',raising=False)
    app=create_app(tmp_path,testing=True,worker=False)
    with TestClient(app) as client:
        assert 'week5_instance' not in client.get('/api/v1/health').json()

@pytest.mark.parametrize('nonce',[None,'',17,'g'*32,'a'*31])
def test_invalid_expected_instance_is_rejected_without_http(nonce):
    class NoRequests:
        def get(self,*args,**kwargs):pytest.fail('No request may be sent for invalid metadata')
    with pytest.raises(ValueError,match='no HTTP request was sent'):
        module.verify_demo_instance(NoRequests(),nonce)
