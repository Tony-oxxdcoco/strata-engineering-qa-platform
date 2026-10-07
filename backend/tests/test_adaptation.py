import base64
import copy
import io
import json
import pytest
from fastapi.testclient import TestClient
from strata.adapters import apply_profile, MappingError, validate_profile
from strata.app import create_app
from strata.storage import Resource, digest

@pytest.fixture
def profile():
    return {'schema':'strata-adapter/1','id':'TEST-TRANSFER','version':'1','title':'SYNTHETIC table transfer adapter','authority':'synthetic','format':'csv','base':{'synthetic':True,'project':{'revision':'E1'}},'tables':[{'source':'csv','target':'/transfer','mode':'single','ignored_columns':[],'fields':[{'aliases':['Force','Vertical'],'target':'/vertical','type':'number','required':True,'unit':{'aliases':['Unit'],'target':'kN','output':'/unit'}}]}]}

@pytest.fixture
def system(tmp_path):
    app=create_app(tmp_path,testing=True,worker=False)
    with TestClient(app) as client:
        auth=client.post('/api/v1/auth/bootstrap',json={'username':'reviewer','password':'long-test-password'}).json()
        client.headers['Authorization']='Bearer '+auth['token']
        project=client.post('/api/v1/projects',json={'name':'Synthetic adaptation'}).json()['project']
        yield app,client,'/api/v1/projects/'+project['id'],project

def upload(client,base,name,content,**extra):
    response=client.post(base+'/files',json={'filename':name,'content_base64':base64.b64encode(content).decode(),**extra})
    assert response.status_code==200,response.text
    return response.json()['file']

def test_conversion_preserves_original_and_alias(profile):
    result=apply_profile('forces.csv',b'Vertical,Unit\n100000,N\n',profile)
    assert result['input']['transfer']=={'vertical':100,'unit':'kN'}
    evidence=result['provenance'][0]
    assert evidence['original_value']=='100000' and evidence['original_unit']=='N'
    assert evidence['location']['row']==2 and evidence['location']['column']=='Vertical'

@pytest.mark.parametrize('content,reason',[(b'Force,Unit\n1,kip\n','Unknown unit'),(b'Force,Unit\n1,m2\n','Incompatible'),(b'Force,Vertical,Unit\n1,2,kN\n','Ambiguous'),(b'Force,Unit,Guess\n1,kN,x\n','Unknown column'),(b'Force,Unit\ntrue,kN\n','decimal'),(b'Force,Unit\n,kN\n','missing'),(b'Force,Unit\n1e-999,kN\n','underflow')])
def test_explicit_errors_have_locations(profile,content,reason):
    with pytest.raises(MappingError) as caught: apply_profile('bad.csv',content,profile)
    assert any(reason.lower() in e['reason'].lower() for e in caught.value.errors)
    assert all(e['file']=='bad.csv' and e['table']=='csv' and e['field'] for e in caught.value.errors)

def test_xlsx_formula_rejected_and_cell_preserved(profile):
    from openpyxl import Workbook
    profile['format']='xlsx';profile['tables'][0]['source']='Loads'
    book=Workbook();sheet=book.active;sheet.title='Loads';sheet.append(['Force','Unit']);sheet.append([100000,'N'])
    content=io.BytesIO();book.save(content)
    assert apply_profile('forces.xlsx',content.getvalue(),profile)['provenance'][0]['location']['cell']=='A2'
    sheet['A2']='=100*1000';content=io.BytesIO();book.save(content)
    with pytest.raises(MappingError,match='Explicit mapping'): apply_profile('forces.xlsx',content.getvalue(),profile)

def test_json_rows_and_duplicate_keys(profile):
    profile['format']='json';profile['tables'][0]['source']='/rows';profile['tables'][0]['mode']='rows'
    assert apply_profile('f.json',b'{"rows":[{"Force":100,"Unit":"kN"}]}',profile)['input']['transfer'][0]['vertical']==100
    with pytest.raises(MappingError): apply_profile('f.json',b'{"rows":[],"rows":[]}',profile)

def test_profile_immutable_export_and_failed_mapping_keeps_source(system,profile):
    app,client,base,project=system
    aid=client.post(base+'/adapters',json={'profile':profile}).json()['adapter']['id']
    assert client.post(base+'/adapters',json={'profile':profile}).status_code==409
    source=upload(client,base,'raw.csv',b'Force,Unit\n1,unknown\n',source_only=True)
    failed=client.post(base+'/adapters/'+aid+'/apply',json={'file_id':source['id']})
    assert failed.status_code==422 and failed.json()['detail']['errors'][0]['file']=='raw.csv'
    assert client.get(base+'/files/'+source['id']+'/content').content==b'Force,Unit\n1,unknown\n'
    assert not client.get(base+'/dashboard').json()['snapshots']
    good=upload(client,base,'raw.csv',b'Force,Unit\n100000,N\n',source_only=True)
    preview=client.post(base+'/adapters/'+aid+'/apply',json={'file_id':good['id'],'preview':True})
    assert preview.status_code==200 and not client.get(base+'/dashboard').json()['snapshots']
    mapped=client.post(base+'/adapters/'+aid+'/apply',json={'file_id':good['id']}).json()['snapshot']
    assert mapped['mapping']=='adapter' and mapped['adapter_hash']==digest(profile)
    assert client.get(base+'/adapters/'+aid+'/export').json()==profile
    with app.state.store.session.begin() as session:
        row=session.get(Resource,aid);app.state.store.change(session,row,{**row.data,'profile':{**profile,'version':'tampered'}})
    assert client.post(base+'/adapters/'+aid+'/apply',json={'file_id':good['id']}).status_code==422

def test_rule_package_roundtrip_reset_approval_and_atomic_validation(system):
    app,client,base,project=system
    assert client.post(base+'/seed').status_code==200
    package=client.get(base+'/rule-packages/export').json()
    assert package['schema']=='strata-rule-package/1'
    other=client.post('/api/v1/projects',json={'name':'Second project'}).json()['project'];target='/api/v1/projects/'+other['id']
    broken=copy.deepcopy(package);next(r for r in broken['rules'] if 'parameters' in r)['parameters']['formula']='eval(1)'
    assert client.post(target+'/rule-packages/import',json={'package':broken}).status_code==422
    assert not client.get(target+'/dashboard').json()['rules']
    assert client.post(target+'/rule-packages/validate',json={'package':package}).status_code==200
    result=client.post(target+'/rule-packages/import',json={'package':package})
    assert result.status_code==200,result.text
    assert all(r['rule']['status']=='draft' and r['rule']['approved_by'] is None and r['rule']['project_id']==other['id'] for r in result.json()['rules'])
    assert client.post(target+'/rule-packages/import',json={'package':package}).status_code==409
    for r in result.json()['rules']: assert client.post(target+'/rules/'+r['id']+'/approve',json={}).status_code==200

def case_for(seed,index=16,expected='PASS'):
    return {'schema':'strata-case/1','case_id':'SYNTHETIC-MASS','version':'1','title':'SYNTHETIC independent mass configuration oracle','authority':'synthetic','task_id':'mass-source','snapshot_id':seed['snapshots'][index]['id'],'rule_versions':[{'id':'MASS-SOURCE','version':'CONTROLLED-1'}],'expected':{'status':expected,'complete':True,'findings':[{'key':'MASS-SOURCE','status':expected},{'key':'MASS-SOURCE/setting-1','status':'PASS'},{'key':'MASS-SOURCE/setting-2','status':expected}]},'truth':{'author':'Synthetic fixture author','basis':'Hand-written requirement: true self-weight and approved-schedule. Missing source is NOT VERIFIED. Not client engineering truth.','independent':True}}

def test_batch_retains_oracle_and_detects_missing_evidence(system):
    app,client,base,_=system;seed=client.post(base+'/seed').json();ids=[]
    for index,status in [(16,'PASS'),(17,'NOT VERIFIED')]:
        case=case_for(seed,index,status);case['case_id']+='-'+str(index)
        response=client.post(base+'/cases',json={'case':case});assert response.status_code==200,response.text
        ids.append(response.json()['case']['id'])
    batch=client.post(base+'/evaluations',json={'case_ids':ids});assert batch.status_code==200,batch.text
    record=batch.json()['evaluation']
    for entry in record['entries']: app.state.runner.process(entry['run_id'])
    result=client.get(base+'/evaluations/'+record['id']).json()['evaluation']
    assert result['summary']['matched']==2 and result['summary']['false_pass_cases']==0
    missing=client.get(base+'/runs/'+record['entries'][1]['run_id']).json()['run']
    assert any(r['what']=='/mass/source' and r['where']['field']=='/mass/source' for r in missing['material_requests'])
    assert client.get(base+'/evaluations/'+record['id']+'/report').json()==result
    assert 'Material requests' in client.get(base+'/runs/'+missing['id']+'/report?format=html').text
    rule=next(r for r in client.get(base+'/dashboard').json()['rules'] if r['rule']['id']=='MASS-SOURCE')
    assert client.post(base+'/rules/'+rule['id']+'/retire',json={}).status_code==200
    outdated=client.get(base+'/evaluations/'+record['id']).json()['evaluation']
    assert outdated['summary']['invalid_cases']==2 and outdated['summary']['matched']==0
    assert client.post(base+'/evaluations',json={'case_ids':ids}).status_code==422

def test_comparator_detects_missed_false_alarm_false_pass_and_tolerance():
    from strata.cases import compare
    seed={'snapshots':[{'id':'snapshot'}]*19};case=case_for(seed,16,'FAIL');case['expected']['complete']=False
    case['expected']['findings'][1]['numbers']=[{'path':'/actual','value':100,'absolute_tolerance':.1,'relative_tolerance':0}]
    run={'id':'test','status':'PASS','state':'COMPLETED','results':[{'id':'MASS-SOURCE','status':'PASS','details':[{'id':'setting-1','status':'FAIL','actual':100.2},{'id':'setting-2','status':'PASS'}]}]}
    result=compare(case,run)
    assert result['counts']['missed_issues']==2 and result['counts']['false_alarms']==1 and result['counts']['false_pass']==2
    assert result['counts']['numeric_mismatches']==1 and result['false_pass_case'] and not result['matched']
    run['results'][0]['details'][0]['actual']=100.05
    assert compare(case,run)['counts']['numeric_mismatches']==0

def test_review_invalidated_by_mapped_revision(system,profile):
    app,client,base,_=system;seed=client.post(base+'/seed').json()
    sid=seed['snapshots'][16]['id'];client.post(base+'/snapshots/'+sid+'/activate',json={})
    rid=client.post(base+'/runs',json={'snapshot_id':sid,'task_id':'mass-source'}).json()['run']['id'];app.state.runner.process(rid)
    assert client.post(base+'/runs/'+rid+'/review',json={'action':'approve','note':'Synthetic test review only'}).status_code==200
    aid=client.post(base+'/adapters',json={'profile':profile}).json()['adapter']['id'];source=upload(client,base,'raw.csv',b'Force,Unit\n1,kN\n',source_only=True)
    assert client.post(base+'/adapters/'+aid+'/apply',json={'file_id':source['id']}).status_code==200
    old=client.get(base+'/runs/'+rid).json()['run']
    assert old['stale'] and old['review_state']=='STALE' and old['reviews']
    assert client.post(base+'/runs/'+rid+'/review',json={'action':'approve','note':'Cannot approve stale'}).status_code==409

def test_adapter_and_case_permission_isolation(system,profile):
    app,client,base,_=system
    aid=client.post(base+'/adapters',json={'profile':profile}).json()['adapter']['id']
    other=client.post('/api/v1/projects',json={'name':'Other'}).json()['project'];otherbase='/api/v1/projects/'+other['id']
    assert client.get(otherbase+'/adapters/'+aid+'/export').status_code==404
    uid=client.post('/api/v1/users',json={'username':'viewer','password':'viewer-test-password'}).json()['user']['id']
    client.post(base+'/members',json={'user_id':uid,'role':'viewer'})
    token=client.post('/api/v1/auth/login',json={'username':'viewer','password':'viewer-test-password'}).json()['token'];client.headers['Authorization']='Bearer '+token
    assert client.get(base+'/adapters').status_code==200
    assert client.post(base+'/adapters',json={'profile':profile}).status_code==403
    assert client.post(base+'/evaluations',json={'case_ids':['a']}).status_code==403
    assert client.get(base+'/rule-packages/export').status_code==403

@pytest.mark.parametrize('change',[{'format':[]},{'tables':[{}]},{'base':{'synthetic':False}},{'tables':'not-a-list'}])
def test_malformed_adapter_is_422(system,profile,change):
    _,client,base,_=system;profile.update(change)
    assert client.post(base+'/adapters',json={'profile':profile}).status_code==422

def test_bad_package_source_excerpt_rolls_back_all_resources(system):
    _,client,base,_=system
    from pathlib import Path
    package=json.loads((Path(__file__).resolve().parents[2]/'examples/rule-package.synthetic.json').read_text())
    package['rules'][-1]['text']='Unsupported invented engineering clause'
    response=client.post(base+'/rule-packages/import',json={'package':package})
    assert response.status_code==422
    dashboard=client.get(base+'/dashboard').json()
    assert dashboard['files']==[] and dashboard['rules']==[]

def test_conditional_rule_missing_context_blocks_with_field_request(system):
    app,client,base,project=system;seed=client.post(base+'/seed').json()
    old=next(r for r in client.get(base+'/dashboard').json()['rules'] if r['rule']['id']=='MASS-SOURCE')
    rule={**old['rule'],'version':'CONDITIONAL-2','conditions':[{'path':'/scope/material','operator':'eq','value':'concrete'}]}
    saved=client.post(base+'/rules',json={'rule':rule});assert saved.status_code==200,saved.text
    assert client.post(base+'/rules/'+saved.json()['rule']['id']+'/approve',json={}).status_code==200
    rid=client.post(base+'/runs',json={'task_id':'mass-source','snapshot_id':seed['snapshots'][16]['id']}).json()['run']['id'];app.state.runner.process(rid)
    run=client.get(base+'/runs/'+rid).json()['run']
    assert run['status']=='NOT VERIFIED' and any(r['what']=='/scope/material' for r in run['material_requests'])

def test_pinned_case_version_cannot_silently_change(system):
    app,client,base,_=system;seed=client.post(base+'/seed').json();case=case_for(seed)
    cid=client.post(base+'/cases',json={'case':case}).json()['case']['id'];batch=client.post(base+'/evaluations',json={'case_ids':[cid]}).json()['evaluation']
    old=next(r for r in client.get(base+'/dashboard').json()['rules'] if r['rule']['id']=='MASS-SOURCE')
    rule={**old['rule'],'version':'CHANGED-2'}
    row=client.post(base+'/rules',json={'rule':rule}).json()['rule'];client.post(base+'/rules/'+row['id']+'/approve',json={})
    app.state.runner.process(batch['entries'][0]['run_id'])
    result=client.get(base+'/evaluations/'+batch['id']).json()['evaluation']
    assert not result['items'][0]['matched'] and result['items'][0]['actual']=='NOT VERIFIED'

def test_case_tampering_and_queued_counts_are_not_success(system):
    app,client,base,_=system;seed=client.post(base+'/seed').json();case=case_for(seed)
    cid=client.post(base+'/cases',json={'case':case}).json()['case']['id'];batch=client.post(base+'/evaluations',json={'case_ids':[cid]}).json()['evaluation']
    queued=client.get(base+'/evaluations/'+batch['id']).json()['evaluation']
    assert queued['state']=='RUNNING' and queued['summary']['total']==0 and queued['progress']['total']==1
    with app.state.store.session.begin() as session:
        row=session.get(Resource,batch['id']);entries=copy.deepcopy(row.data['entries']);entries[0]['case']['expected']['status']='FAIL';app.state.store.change(session,row,{**row.data,'entries':entries})
    assert client.get(base+'/evaluations/'+batch['id']).status_code==422

def test_input_and_own_hash_tampering_still_invalidates_checked_result(system):
    app,client,base,_=system;seed=client.post(base+'/seed').json();sid=seed['snapshots'][16]['id']
    rid=client.post(base+'/runs',json={'task_id':'mass-source','snapshot_id':sid}).json()['run']['id'];app.state.runner.process(rid)
    with app.state.store.session.begin() as session:
        row=session.get(Resource,sid);payload=copy.deepcopy(row.data['input']);payload['mass']['source']='tampered';app.state.store.change(session,row,{**row.data,'input':payload,'input_hash':digest(payload)})
    run=client.get(base+'/runs/'+rid).json()['run']
    assert run['status']=='NOT VERIFIED' and run['integrity_status']=='INVALID'

def test_rule_without_registered_tool_is_rejected(system):
    _,client,base,_=system;client.post(base+'/seed')
    rule=next(r['rule'] for r in client.get(base+'/dashboard').json()['rules'] if r['rule']['id']=='MASS-SOURCE')
    rule={**rule,'version':'INVALID-2','parameters':{'settings':[{'path':'/mass/source','operator':'formula','value':'__import__("os")'}]}}
    assert client.post(base+'/rules',json={'rule':rule}).status_code==422

@pytest.mark.parametrize('kind',['self-derived','unknown-field'])
def test_oracle_independence_is_required(system,kind):
    _,client,base,_=system;seed=client.post(base+'/seed').json();case=case_for(seed)
    if kind=='self-derived': case['truth']['independent']=False
    else: case['expected']['formula']='checker.output'
    assert client.post(base+'/cases',json={'case':case}).status_code==422

def test_mapped_correction_keeps_original_provenance(system,profile):
    _,client,base,_=system
    aid=client.post(base+'/adapters',json={'profile':profile}).json()['adapter']['id']
    source=upload(client,base,'raw.csv',b'Force,Unit\n100000,N\n',source_only=True)
    original=client.post(base+'/adapters/'+aid+'/apply',json={'file_id':source['id']}).json()['snapshot']
    correction={'path':'/transfer/vertical','original':100.0,'value':120,'reason':'Explicit synthetic revision','source_locator':'Synthetic case author / revised field'}
    response=client.post(base+'/snapshots/'+original['id']+'/corrections',json={'corrections':[correction]})
    assert response.status_code==200,response.text
    changed=response.json()['snapshot']
    assert changed['parent_id']==original['id'] and changed['adapter_hash']==original['adapter_hash'] and changed['provenance']==original['provenance']
    assert changed['input']['transfer']['vertical']==120 and changed['provenance'][0]['original_value']=='100000'

def test_failed_aggregate_still_requests_missing_child_evidence():
    from strata.evidence import requests
    results=[{'id':'MASS-SOURCE','status':'FAIL','details':[{'id':'setting-1','status':'FAIL'},{'id':'setting-2','status':'NOT VERIFIED','reason':'Missing mapped path /mass/source','dependencies':['/mass/source','/configuration_complete']}]}]
    items=requests(results,{'configuration_complete':True,'mass':{'include_self_weight':False}})
    assert len(items)==1 and items[0]['what']=='/mass/source'
