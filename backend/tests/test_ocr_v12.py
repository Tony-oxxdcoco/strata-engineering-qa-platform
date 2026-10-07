"""Synthetic OCR API/provenance regressions with MOCK recognition, not OCR accuracy.

Only recognize() is mocked. Auth, roles, storage, confirmation, snapshots,
workflow, dashboard integrity, exports and backup/restore use real local code.
"""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from strata.app import create_app
from strata.provenance import validate_file
from strata.storage import Resource

ROOT=Path(__file__).resolve().parents[2]
TEXT='SYNTHETIC MOCK recognition\nObject Force Unit\nA -12.50 kN\nB 0.125 kN\n'
IMAGE=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7i8AAAAASUVORK5CYII=')


def pdf():
    writer=PdfWriter();writer.add_blank_page(width=300,height=200)
    stream=io.BytesIO();writer.write(stream);return stream.getvalue()


def mocked_recognition(content,page):
    if type(page) is not int or not 1<=page<=1:raise ValueError('Select an available explicit PDF page')
    return {'provider':'SYNTHETIC-MOCK','page':page,'text':TEXT,'lines':[{'text':TEXT,'confidence':0.1,'box':[0.1,0.1,0.8,0.4]}],
            'state':'PENDING_REVIEW','image':IMAGE,'warning':'SYNTHETIC MOCK; deliberately untrusted numbers and column relationships.'}


@pytest.fixture
def system(tmp_path,monkeypatch):
    monkeypatch.setenv('STRATA_OCR_ENABLED','1')
    monkeypatch.setattr('strata.ocr_api.recognize',mocked_recognition)
    app=create_app(tmp_path/'runtime',testing=True,worker=False)
    with TestClient(app) as client:
        auth=client.post('/api/v1/auth/bootstrap',json={'username':'synthetic-reviewer','password':'synthetic-review-password'}).json()
        token=auth['token'];client.headers['Authorization']='Bearer '+token
        project=client.post('/api/v1/projects',json={'name':'SYNTHETIC MOCK OCR review'}).json()['project']
        base='/api/v1/projects/'+project['id']
        original=upload(client,base,'synthetic-scan.pdf',pdf())
        yield app,client,base,original,token


def upload(client,base,name,content):
    response=client.post(base+'/files',json={'filename':name,'content_base64':base64.b64encode(content).decode()})
    assert response.status_code==200,response.text
    return response.json()['file']


def extract(client,base,original):
    response=client.post(base+'/files/'+original['id']+'/ocr',json={'page':1})
    assert response.status_code==200,response.text
    return response.json()['ocr']


def confirm(client,base,ocr,**changes):
    body={'text':TEXT.replace('MOCK recognition','human-corrected test transcription'),
          'reason':'SYNTHETIC API test: independently checked numbers, signs, units and table columns',
          'numbers_units_columns_checked':True}
    body.update(changes)
    return client.post(base+'/ocr/'+ocr['id']+'/confirm',json=body)


def snapshot(client,base,file_id):
    return client.post(base+'/snapshots',json={'file_id':file_id,'title':'SYNTHETIC explicit fields','input':{'synthetic':True,'configuration_complete':True,'mass':{'include_self_weight':True,'source':'approved-schedule'}},'mapping_note':'SYNTHETIC manual mapping against a human-confirmed transcription; no engineering approval'})


def test_pending_scan_and_image_cannot_authorize_engineering_mapping(system):
    _,client,base,original,_=system
    assert original['ingestion']['status']=='NEEDS_OCR'
    assert snapshot(client,base,original['id']).status_code==422
    ocr=extract(client,base,original)
    assert ocr['state']=='PENDING_REVIEW' and ocr['provider']=='SYNTHETIC-MOCK'
    assert 'transcription_file_id' not in ocr
    assert snapshot(client,base,ocr['image_file_id']).status_code==422
    assert not client.get(base+'/dashboard').json()['snapshots']


@pytest.mark.parametrize('change',[{'numbers_units_columns_checked':False},{'text':''},{'text':'   \n\t'}, {'reason':'   '}])
def test_confirmation_requires_actual_text_and_explicit_human_checks(system,change):
    _,client,base,original,_=system;ocr=extract(client,base,original)
    assert confirm(client,base,ocr,**change).status_code==422
    assert client.get(base+'/files/'+original['id']+'/ocr').json()['items'][0]['state']=='PENDING_REVIEW'


def test_only_reviewer_can_confirm_and_confirmation_is_not_replayable(system):
    _,client,base,original,reviewer_token=system;ocr=extract(client,base,original)
    account=client.post('/api/v1/users',json={'username':'synthetic-engineer','password':'synthetic-engineer-password'}).json()['user']
    assert client.post(base+'/members',json={'user_id':account['id'],'role':'engineer'}).status_code==200
    token=client.post('/api/v1/auth/login',json={'username':'synthetic-engineer','password':'synthetic-engineer-password'}).json()['token']
    client.headers['Authorization']='Bearer '+token
    assert confirm(client,base,ocr).status_code==403
    client.headers['Authorization']='Bearer '+reviewer_token
    response=confirm(client,base,ocr);assert response.status_code==200,response.text
    record=response.json()['ocr'];assert record['state']=='CONFIRMED' and record['confirmed_by']
    assert record['corrections'][0]['original']==TEXT and record['corrections'][0]['corrected']==record['confirmed_text']
    count=len(client.get(base+'/dashboard').json()['files'])
    assert confirm(client,base,ocr).status_code==422
    assert len(client.get(base+'/dashboard').json()['files'])==count
    assert snapshot(client,base,record['transcription_file_id']).status_code==200


def test_cross_project_ocr_image_transcription_and_mapping_are_isolated(system):
    _,client,base,original,_=system;ocr=extract(client,base,original)
    confirmed=confirm(client,base,ocr).json()['ocr']
    other=client.post('/api/v1/projects',json={'name':'SYNTHETIC isolated project'}).json()['project'];otherbase='/api/v1/projects/'+other['id']
    assert client.get(otherbase+'/files/'+original['id']+'/ocr').status_code==404
    assert client.post(otherbase+'/files/'+original['id']+'/ocr',json={'page':1}).status_code==404
    assert confirm(client,otherbase,ocr).status_code==404
    assert client.get(otherbase+'/files/'+ocr['image_file_id']+'/content').status_code==404
    assert snapshot(client,otherbase,confirmed['transcription_file_id']).status_code==404


@pytest.mark.parametrize('tamper',['pdf-bytes','image-bytes','extraction-text','source-metadata','image-metadata','image-other-project'])
def test_tamper_before_confirmation_cannot_create_trusted_transcription(system,tamper):
    app,client,base,original,_=system;ocr=extract(client,base,original)
    if tamper in ('pdf-bytes','image-bytes'):
        sha=original['sha256'] if tamper=='pdf-bytes' else ocr['image_sha256'];(app.state.store.blobs/sha).write_bytes(b'CORRUPTED SYNTHETIC SOURCE')
    else:
        with app.state.store.session.begin() as session:
            if tamper=='extraction-text':
                row=session.get(Resource,ocr['id']);app.state.store.change(session,row,{**row.data,'text':'Tampered recognized values'})
            elif tamper=='source-metadata':
                row=session.get(Resource,original['id']);app.state.store.change(session,row,{**row.data,'sha256':app.state.store.put_blob(b'ANOTHER PDF SOURCE')})
            else:
                row=session.get(Resource,ocr['image_file_id'])
                if tamper=='image-other-project':row.project_id='OTHER-PROJECT'
                else:app.state.store.change(session,row,{**row.data,'sha256':app.state.store.put_blob(b'ANOTHER IMAGE')})
    response=confirm(client,base,ocr)
    assert response.status_code in (404,422),response.text
    assert not any(f.get('ocr_id') for f in client.get(base+'/dashboard').json()['files'])


def test_confirmed_source_tamper_is_rejected_before_new_snapshot(system):
    app,client,base,original,_=system;ocr=extract(client,base,original)
    confirmed=confirm(client,base,ocr).json()['ocr']
    (app.state.store.blobs/ocr['image_sha256']).write_bytes(b'CORRUPTED IMAGE')
    response=snapshot(client,base,confirmed['transcription_file_id'])
    assert response.status_code==422,response.text
    assert client.get(base+'/dashboard').json()['snapshots']==[]


def test_same_content_plain_file_cannot_bypass_ocr_provenance_on_dashboard(system):
    app,client,base,original,_=system
    client.post(base+'/seed')
    ocr=extract(client,base,original);confirmed=confirm(client,base,ocr).json()['ocr']
    plain=upload(client,base,'synthetic-manual-source.txt',confirmed['confirmed_text'].encode())
    ids=[]
    for source_id in (plain['id'],confirmed['transcription_file_id']):
        made=snapshot(client,base,source_id);assert made.status_code==200,made.text
        run=client.post(base+'/runs',json={'task_id':'mass-source','snapshot_id':made.json()['snapshot']['id']}).json()['run']
        app.state.runner.process(run['id']);assert client.get(base+'/runs/'+run['id']).json()['run']['status']=='PASS'
        ids.append(run['id'])
    (app.state.store.blobs/ocr['image_sha256']).write_bytes(b'CORRUPTED SYNTHETIC IMAGE')
    dashboard=client.get(base+'/dashboard');assert dashboard.status_code==200,dashboard.text
    runs={r['id']:r for r in dashboard.json()['runs']}
    assert runs[ids[0]]['status']=='PASS' and runs[ids[0]].get('integrity_status')!='INVALID'
    assert runs[ids[1]]['status']=='NOT VERIFIED' and runs[ids[1]]['integrity_status']=='INVALID'
    assert client.get(base+'/runs/'+ids[1]+'/report?format=json').status_code==422


def test_backup_restore_retains_original_image_text_corrections_and_confirmation(system,tmp_path):
    app,client,base,original,_=system;ocr=extract(client,base,original)
    confirmed=confirm(client,base,ocr).json()['ocr']
    spec=importlib.util.spec_from_file_location('ocr_backup_v12',ROOT/'scripts/backup.py');backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
    result=backup.create_backup(app.state.store.root,tmp_path/'backup')
    assert result['blob_count']==3 # original PDF, derived image, human-confirmed TXT
    restored=backup.restore_backup(tmp_path/'backup',tmp_path/'restored');assert restored['sessions_invalidated']==1
    from strata.storage import Store
    copied=Store(tmp_path/'restored')
    with copied.session() as session:
        text_file=session.get(Resource,confirmed['transcription_file_id'])
        assert validate_file(copied,session,text_file)==confirmed['confirmed_text'].encode()
        stored=session.get(Resource,ocr['id'])
        assert stored.data['corrections']==confirmed['corrections'] and stored.data['confirmation_hash']==confirmed['confirmation_hash']
        assert copied.get_blob(original['sha256'])==pdf()
        assert copied.get_blob(ocr['image_sha256'])==IMAGE
    copied.engine.dispose()


@pytest.mark.parametrize('raw',[b'{"name":"first","name":"second"}',b'{"name":"test","n":NaN}',b'{"name":"test","n":Infinity}',b'{"name":"test","n":1e999}',b'{"name":"test","n":1e-999}',b'{"name":"test","n":'+b'['*40+b'0'+b']'*40+b'}'])
def test_raw_api_json_is_never_silently_coerced(system,raw):
    _,client,_,_,_=system
    response=client.post('/api/v1/projects',content=raw,headers={'Content-Type':'application/json'})
    assert response.status_code==422 and response.json()['detail']['kind']=='INVALID_INPUT'


def test_confirmation_limits_apply_to_original_text_not_trimmed_text(system):
    _,client,base,original,_=system;ocr=extract(client,base,original)
    assert confirm(client,base,ocr,text='A'+' '*200000).status_code==422
    assert confirm(client,base,ocr,reason='A'+' '*1000).status_code==422


def test_revoked_engineer_cannot_publish_ocr_after_recognition(system,monkeypatch):
    from strata.storage import Membership
    app,client,base,original,_=system
    account=client.post('/api/v1/users',json={'username':'synthetic-ocr-engineer','password':'synthetic-ocr-password'}).json()['user']
    client.post(base+'/members',json={'user_id':account['id'],'role':'engineer'})
    token=client.post('/api/v1/auth/login',json={'username':'synthetic-ocr-engineer','password':'synthetic-ocr-password'}).json()['token'];client.headers['Authorization']='Bearer '+token
    project=base.rsplit('/',1)[-1]
    def interrupted(content,page):
        with app.state.store.session.begin() as session:
            member=session.get(Membership,(project,account['id']));member.role='viewer'
        return mocked_recognition(content,page)
    monkeypatch.setattr('strata.ocr_api.recognize',interrupted)
    assert client.post(base+'/files/'+original['id']+'/ocr',json={'page':1}).status_code==403
    dashboard=client.get(base+'/dashboard').json()
    assert len(dashboard['files'])==1 and client.get(base+'/files/'+original['id']+'/ocr').json()['items']==[]


def test_confirmation_storage_failure_preserves_pending_state_and_retry(system,monkeypatch):
    app,client,base,original,_=system;ocr=extract(client,base,original)
    original_audit=app.state.store.audit
    def fail_confirm(session,project,actor,action,*args,**kwargs):
        if action=='ocr.confirmed':raise ValueError('SYNTHETIC storage fault during confirmation')
        return original_audit(session,project,actor,action,*args,**kwargs)
    monkeypatch.setattr(app.state.store,'audit',fail_confirm)
    assert confirm(client,base,ocr).status_code==422
    assert client.get(base+'/files/'+original['id']+'/ocr').json()['items'][0]['state']=='PENDING_REVIEW'
    assert not any(f.get('ocr_id') for f in client.get(base+'/dashboard').json()['files'])
    monkeypatch.setattr(app.state.store,'audit',original_audit)
    assert confirm(client,base,ocr).status_code==200


def test_missing_confirmation_metadata_is_an_integrity_error_not_server_crash(system):
    app,client,base,original,_=system;ocr=extract(client,base,original)
    confirmed=confirm(client,base,ocr).json()['ocr']
    with app.state.store.session.begin() as session:
        row=session.get(Resource,ocr['id']);changed=copy.deepcopy(row.data);del changed['image_file_id'];app.state.store.change(session,row,changed)
    response=snapshot(client,base,confirmed['transcription_file_id'])
    assert response.status_code==422,response.text


def test_ocr_renderer_timeout_is_an_explainable_error_not_server_crash(system,monkeypatch):
    import subprocess
    import strata.ocr as ocr_module
    _,client,base,original,_=system
    monkeypatch.setattr('strata.ocr_api.recognize',ocr_module.recognize)
    monkeypatch.setattr(ocr_module,'capabilities',lambda:{'enabled':True,'available':True,'provider':'SYNTHETIC-MOCK-RENDERER'})
    monkeypatch.setattr(ocr_module.shutil,'which',lambda name:'/synthetic/'+name)
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('synthetic-renderer',30)
    monkeypatch.setattr(ocr_module.subprocess,'run',timeout)
    response=client.post(base+'/files/'+original['id']+'/ocr',json={'page':1})
    assert response.status_code==422
    message=str(response.json()).lower()
    assert ('timeout' in message or 'timed out' in message) and 'manual transcription' in message
