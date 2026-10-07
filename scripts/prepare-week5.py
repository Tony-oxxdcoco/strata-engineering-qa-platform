#!/usr/bin/env python3
"""Prepare synthetic demo fixtures through the public API. No stored credentials.

Primary mode saves draft rule and independent cases, without running checks.
The CLI verifies the marked local demo directory and its port. Recorded
fallbacks come from a completed checkpoint, not precomputed by preparation.
No account or data is cleared by this script.
"""
import argparse,base64,getpass,json,os,re,time
from pathlib import Path
from urllib.parse import urlparse
import httpx
ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'examples/week5'

def prepare(client):
    def call(method,path,body=None):
        response=client.request(method,'/api/v1'+path,json=body) if body is not None else client.request(method,'/api/v1'+path)
        response.raise_for_status();return response.json()
    name='SYNTHETIC P144 Week 5 LIVE START'
    if any(p['name']==name for p in call('GET','/projects')['items']):raise ValueError('A prepared project with this name exists. Restore the marked demo checkpoint or choose another isolated demo directory; existing projects are never deleted.')
    health=call('GET','/health')
    base='/projects/'+call('POST','/projects',{'name':name})['project']['id']
    package=json.loads((FIXTURES/'rule-package.synthetic.json').read_text())
    call('POST',base+'/rule-packages/validate',{'package':package})
    rules=call('POST',base+'/rule-packages/import',{'package':package})['rules']
    profile=json.loads((FIXTURES/'reference-adapter.synthetic.json').read_text())
    adapter=call('POST',base+'/adapters',{'profile':profile})['adapter']
    truth=json.loads((FIXTURES/'independent-expectations.synthetic.json').read_text())
    snapshots={};files={};cases=[]
    for item in truth['cases']:
        content=(FIXTURES/item['file']).read_bytes()
        source=call('POST',base+'/files',{'filename':item['file'],'content_base64':base64.b64encode(content).decode()})['file'];files[item['key']]=source['id']
        title={'pass':'01 PASS - complete synthetic input','fail':'02 FAIL - deliberate 210 kN export','missing':'03 NOT VERIFIED - independent LIVE missing'}[item['key']]
        snapshot=call('POST',base+'/snapshots',{'file_id':source['id'],'title':title,'mapping_note':'Prepared controlled synthetic JSON; independent reference and separately supplied export; no guessed input'})['snapshot'];snapshots[item['key']]=snapshot['id']
        case={'schema':'strata-case/1','case_id':item['case_id'],'version':'1','title':'SYNTHETIC '+item['case_id'],'authority':'synthetic','task_id':'load-combination','snapshot_id':snapshot['id'],'rule_versions':truth['rule_versions'],'expected':item['expected'],'truth':truth['truth']}
        cases.append(call('POST',base+'/cases',{'case':case})['case']['id'])
    for key,filename,raw in [('repair','combination-repaired.synthetic.json',False),('reference','reference-base-responses.synthetic.csv',True)]:
        source=call('POST',base+'/files',{'filename':filename,'content_base64':base64.b64encode((FIXTURES/filename).read_bytes()).decode(),'source_only':raw})['file'];files[key]=source['id']
    call('POST',base+'/snapshots/'+snapshots['pass']+'/activate',{})
    return {'schema':'strata-week5-preparation/1','version':health['version'],'mode':'primary','material_type':'synthetic','project_id':base.split('/')[-1],'project_name':name,'snapshots':snapshots,'files':files,'adapter_id':adapter['id'],'rule_id':rules[0]['id'],'rule_status':'draft','cases':cases,'runs_precomputed':0,'model_live':False,'scope':'The reference-only CSV preview is incomplete for a combination check. Live start contains no prior engineering results. Review approval is for software test use only.'}


def verify_demo_instance(client, nonce):
    if not isinstance(nonce,str) or not re.fullmatch(r'[0-9a-f]{32}',nonce):
        raise ValueError('Invalid managed demo instance identifier; no HTTP request was sent')
    response=client.get('/api/v1/health');response.raise_for_status()
    if response.json().get('week5_instance') != nonce:
        raise ValueError('HTTP server does not match the running marked demo instance; no login or preparation was sent')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:4190');parser.add_argument('--username',default='week5-demo');parser.add_argument('--directory',type=Path,default=ROOT/'output/week5-environment');parser.add_argument('--output',type=Path,default=ROOT/'output/week5/preparation.json')
    args=parser.parse_args();url=urlparse(args.url)
    if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost'} or url.username or url.password or url.path not in {'','/'} or url.query or url.fragment:raise ValueError('Use a local HTTP demo server URL, without credentials or paths')
    import importlib.util
    spec=importlib.util.spec_from_file_location('week5_environment',ROOT/'scripts/week5-environment.py')
    manager=importlib.util.module_from_spec(spec);spec.loader.exec_module(manager)
    _,metadata=manager.environment(args.directory)
    if url.port != metadata['port']:raise ValueError('URL port must match the marked demo environment')
    if not manager.status(args.directory)['manager_running']:raise ValueError('Start this marked environment with week5-environment.py before preparing fixtures')
    directory,metadata=manager.environment(args.directory)
    service=manager.read_json(directory/'service.json')
    if service.get('identity') != metadata['identity'] or service.get('state') != 'RUNNING':raise ValueError('No matching owned demo service is running')
    with httpx.Client(base_url=args.url,timeout=30) as client:
        verify_demo_instance(client,service['nonce'])
        password=getpass.getpass('Local demo password (not stored): ')
        setup=client.get('/api/v1/auth/setup');setup.raise_for_status()
        if setup.json()['needs_setup']:
            headers={}
            if setup.json().get('token_required'):headers['X-Setup-Token']=getpass.getpass('Setup token (not stored): ')
            auth=client.post('/api/v1/auth/bootstrap',json={'username':args.username,'password':password},headers=headers)
        else:auth=client.post('/api/v1/auth/login',json={'username':args.username,'password':password})
        auth.raise_for_status();client.headers['Authorization']='Bearer '+auth.json()['token']
        record=prepare(client)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'project':record['project_name'],'version':record['version'],'draft_rule':True,'precomputed_runs':0,'receipt':str(args.output)},ensure_ascii=False))
if __name__=='__main__':main()
