#!/usr/bin/env python3
"""Reproducible adaptation demo, offline server API or a real localhost server.

Reads independent expectations from a suite JSON. Never constructs truth from
checker results. Runtime accounts and customer files are never packaged.
"""
import argparse
import base64
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fastapi.testclient import TestClient
from strata.app import create_app
from strata.storage import digest, now
from strata.workflow import TOOL_FINGERPRINT

def read(path): return json.loads(path.read_text(encoding='utf-8'))

def demonstrate(client,suite_path,output,process=None):
    suite=read(suite_path);directory=suite_path.parent
    if suite.get('schema')!='strata-demo-suite/1': raise ValueError('Expected strata-demo-suite/1')
    def local(name):
        path=(directory/name).resolve()
        if not path.is_relative_to(directory.resolve()): raise ValueError('Suite file paths must stay inside the suite directory')
        return path
    def call(method,path,body=None):
        response=client.request(method,'/api/v1'+path,json=body) if body is not None else client.request(method,'/api/v1'+path)
        if response.status_code>=400: raise ValueError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return response
    base='/projects/'+call('POST','/projects',{'name':'SYNTHETIC adaptation demo '+now()}).json()['project']['id']
    package=read(local(suite['rule_package']))
    call('POST',base+'/rule-packages/validate',{'package':package})
    imported=call('POST',base+'/rule-packages/import',{'package':package}).json()['rules']
    for rule in imported: call('POST',base+'/rules/'+rule['id']+'/approve',{})
    adapters={};snapshots={}
    for item in suite['inputs']:
        content=local(item['file']).read_bytes()
        source=call('POST',base+'/files',{'filename':Path(item['file']).name,'content_base64':base64.b64encode(content).decode(),'source_only':'adapter' in item}).json()['file']
        if 'adapter' in item:
            name=item['adapter']
            if name not in adapters: adapters[name]=call('POST',base+'/adapters',{'profile':read(local(name))}).json()['adapter']['id']
            snapshot=call('POST',base+'/adapters/'+adapters[name]+'/apply',{'file_id':source['id'],'title':'SYNTHETIC '+item['key']}).json()['snapshot']
        else:
            snapshot=call('POST',base+'/snapshots',{'file_id':source['id'],'input':read(local(item['file'])),'mapping_note':'Exact hand-written synthetic JSON; no inferred fields','title':'SYNTHETIC '+item['key']}).json()['snapshot']
        snapshots[item['key']]=snapshot['id']
    ids=[]
    for spec in suite['cases']:
        case={'schema':'strata-case/1','case_id':spec['case_id'],'version':'1','title':'SYNTHETIC '+spec['case_id'],'authority':'synthetic','task_id':spec['task_id'],'snapshot_id':snapshots[spec['input']],'rule_versions':spec['rule_versions'],'expected':spec['expected'],'truth':suite['truth']}
        if spec.get('target'): case['compare_to']=snapshots[spec['target']]
        ids.append(call('POST',base+'/cases',{'case':case}).json()['case']['id'])
    record=call('POST',base+'/evaluations',{'case_ids':ids}).json()['evaluation']
    if process:
        for entry in record['entries']: process(entry['run_id'])
    deadline=time.monotonic()+60
    while True:
        result=call('GET',base+'/evaluations/'+record['id']).json()['evaluation']
        if result['state']=='COMPLETED': break
        if time.monotonic()>deadline: raise ValueError('Demo queue timeout; check worker and logs')
        time.sleep(.2)
    output.mkdir(parents=True,exist_ok=True)
    artifact={**result,'generated_at':now(),'tool_fingerprint':TOOL_FINGERPRINT,'suite_sha256':digest(suite)}
    (output/'case-evaluation.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
    for index,entry in enumerate(record['entries']):
        rid=entry['run_id']
        (output/f'case-{index+1}.html').write_bytes(call('GET',base+'/runs/'+rid+'/report?format=html').content)
        (output/f'case-{index+1}.json').write_bytes(call('GET',base+'/runs/'+rid+'/report?format=json').content)
    # Confirm a current PASS, change the active input, and prove the historical
    # review is retained but cannot be reused as a current confirmation.
    passing=next(i for i in result['items'] if i['actual']=='PASS')
    row=call('GET',base+'/runs/'+passing['run_id']).json()['run']
    active=row.get('compare_to') or row['snapshot_id']
    call('POST',base+'/snapshots/'+active+'/activate',{})
    call('POST',base+'/runs/'+row['id']+'/review',{'action':'approve','note':'Synthetic demo review only; not engineering certification'})
    different=next(s for s in snapshots.values() if s!=active)
    call('POST',base+'/snapshots/'+different+'/activate',{})
    stale=call('GET',base+'/runs/'+row['id']).json()['run']
    assert stale['stale'] and stale['review_state']=='STALE' and stale['reviews']
    artifact['review_invalidation']={'verified':True,'retained_reviews':len(stale['reviews']),'reasons':stale['stale_reasons']}
    (output/'case-evaluation.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'project_url':base,'output':str(output),'summary':result['summary'],'review_invalidation':True},ensure_ascii=False))
    return result['summary']['matched']==len(ids)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--suite',type=Path,default=ROOT/'examples/case-suite.synthetic.json');parser.add_argument('--output',type=Path,default=ROOT/'output/adaptation-demo');parser.add_argument('--url');parser.add_argument('--username')
    args=parser.parse_args()
    if args.url:
        from urllib.parse import urlsplit
        import getpass,httpx
        url=urlsplit(args.url)
        if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost','::1'} or url.path not in ('','/'): raise ValueError('Use a plain local HTTP origin; cloud deployment is deferred')
        with httpx.Client(base_url=args.url,timeout=20) as client:
            response=client.post('/api/v1/auth/login',json={'username':args.username or input('Local STRATA username: '),'password':getpass.getpass('Local STRATA password: ')})
            response.raise_for_status();client.headers['Authorization']='Bearer '+response.json()['token']
            ok=demonstrate(client,args.suite.resolve(),args.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='strata-demo-') as runtime:
            app=create_app(runtime,testing=True,worker=False)
            with TestClient(app) as client:
                auth=client.post('/api/v1/auth/bootstrap',json={'username':'synthetic-demo','password':secrets.token_urlsafe(24)}).json()
                client.headers['Authorization']='Bearer '+auth['token']
                ok=demonstrate(client,args.suite.resolve(),args.output.resolve(),app.state.runner.process)
    sys.exit(0 if ok else 1)
