#!/usr/bin/env python3
"""Actual isolated Docker delivery verification. Never install Docker or models.

Create unique projects/volumes. Credentials remain in memory. Stop the created
containers on completion; retain only these test volumes for diagnosis. This
checks real Linux containers on the current engine, not Windows launchers/CSI.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import httpx

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / 'package.json').read_text())['version']


def write_private_log(path, payload):
    """Set owner-only access before writing; chmod alone is not a Windows ACL."""
    fd, name = tempfile.mkstemp(prefix='.docker-log-', dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        if os.name == 'nt':
            # Pass the path as data, never interpolate it into shell source.
            env = dict(os.environ, STRATA_PRIVATE_LOG_PATH=str(temporary))
            # GitHub's pwsh parent can carry a module path for another PS version.
            env.pop('PSModulePath', None)
            script = """$ErrorActionPreference='Stop'
$p=$env:STRATA_PRIVATE_LOG_PATH
$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl=New-Object System.Security.AccessControl.FileSecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true,$false)
$rule=[System.Security.AccessControl.FileSystemAccessRule]::new($sid,[System.Security.AccessControl.FileSystemRights]::FullControl,[System.Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($rule)
[System.IO.File]::SetAccessControl($p,$acl)
$actual=[System.IO.File]::GetAccessControl($p)
$rules=@($actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))
if(-not $actual.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne $sid.Value -or $rules[0].AccessControlType -ne 'Allow' -or $rules[0].FileSystemRights -ne 'FullControl'){throw 'Owner-only log ACL verification failed'}
"""
            try:
                subprocess.run(['powershell.exe','-NoProfile','-NonInteractive',
                                '-Command',script],env=env,check=True,
                               capture_output=True,text=True,timeout=20)
            except subprocess.CalledProcessError as error:
                raise VerificationError('Windows private log ACL failed: '+error.stderr[:1500]) from error
        else:
            temporary.chmod(0o600)
        temporary.write_text(payload, encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition: raise VerificationError(message)


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


class Verification:
    def __init__(self,args):
        self.args=args;self.nonce=secrets.token_hex(5)
        self.projects=[f'strata-week5-check-{self.nonce}',f'strata-week5-restore-{self.nonce}']
        self.token=secrets.token_urlsafe(32);self.password=secrets.token_urlsafe(24)
        self.username='week5-docker-check';self.image_tag=f'{VERSION}-check-{self.nonce}'
        self.touched=[];self.log=[]
        self.result={'schema':'strata-docker-verification/1','version':VERSION,'status':'IN PROGRESS',
                     'material_type':'synthetic','started_at':datetime.now(timezone.utc).isoformat(),
                     'scope':'Actual Docker image/core HTTP workflow/persistence/independent-volume recovery only; no client truth or CSI',
                     'projects':self.projects,'checks':{},'limitations':['No real ETABS/SAFE, customer engineering acceptance or Windows launcher verification.','Model disabled; no Ollama image or weights downloaded.']}

    def command(self,args,env=None,timeout=90,input_data=None):
        r=subprocess.run([self.args.docker,*args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=timeout,input=input_data)
        self.log.append({'command':[self.args.docker,*args],'return_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode: raise VerificationError('Docker command failed: '+' '.join(args[:5])+'; see the private local command log')
        return r.stdout.strip()

    def phase(self,name):
        self.result['current_phase']=name
        self.args.output.parent.mkdir(parents=True,exist_ok=True)
        self.args.output.write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'phase':name,'version':VERSION,'status':self.result['status']}),flush=True)

    def compose(self,index,*args,timeout=90,input_data=None):
        env=dict(os.environ)
        env.update(STRATA_WEEK5_PORT=str(self.args.port if index==0 else self.args.restore_port),
                   STRATA_WEEK5_SETUP_TOKEN=self.token,STRATA_IMAGE_TAG=self.image_tag)
        command=['compose','-p',self.projects[index],'-f','compose.yaml','-f','compose.week5.yaml',*args]
        return self.command(command,env,timeout,input_data) if input_data is not None else self.command(command,env,timeout)

    def copy_checkpoint(self,source):
        """Keep UID10001/cap_drop; no root, chmod relaxation or bind mount."""
        backup=module('week5_verifier_backup',ROOT/'scripts/backup.py')
        verified=backup.verify_backup(source)
        paths=[source/'manifest.json',source/'strata.db',*sorted((source/'blobs').iterdir())]
        require(sum(p.stat().st_size for p in paths)<=32*1024*1024,'Synthetic checkpoint exceeds verifier transfer limit')
        require(all(not p.is_symlink() and p.stat().st_nlink==1 for p in paths),'Checkpoint links are refused')
        payload=json.dumps({'files':[{ 'path':p.relative_to(source).as_posix(),
            'bytes':base64.b64encode(p.read_bytes()).decode()} for p in paths]})
        # stdin is never added to the command transcript. Receiver only writes
        # exclusive private files inside this fresh, marked test volume.
        code="""import base64,json,os,re,sys
from pathlib import Path
p=Path('/backups/week5/checkpoints/completed');assert not p.exists();p.mkdir(mode=0o700);(p/'blobs').mkdir(mode=0o700)
data=json.load(sys.stdin);assert set(data)=={'files'} and 2<=len(data['files'])<=1002
total=0;seen=set()
for f in data['files']:
 assert set(f)=={'path','bytes'} and (f['path'] in {'manifest.json','strata.db'} or re.fullmatch(r'blobs/[0-9a-f]{64}',f['path'])) and f['path'] not in seen
 seen.add(f['path']);b=base64.b64decode(f['bytes'],validate=True);total+=len(b);assert total<=32*1024*1024
 fd=os.open(p/f['path'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as out:out.write(b)
assert {'manifest.json','strata.db'}<=seen
print(json.dumps({'copied_files':len(seen),'uid':os.getuid()}))"""
        copied=json.loads(self.compose(1,'run','--rm','--no-deps','-T','app','python','-c',code,input_data=payload))
        require(copied['uid']==10001 and copied['copied_files']==len(paths),'Checkpoint copy did not preserve normal app UID')
        destination=json.loads(self.compose(1,'run','--rm','--no-deps','app','python','scripts/backup.py','verify','/backups/week5/checkpoints/completed'))
        require(destination['database_sha256']==verified['database_sha256'] and destination['blob_count']==verified['blob_count'],'Transferred backup identity differs')
        self.result['checks']['checkpoint_transfer']={'uid':copied['uid'],'private_files':True,'database_sha256':verified['database_sha256'],'blob_count':verified['blob_count'],'destination_hashes_verified':True}

    def wait_health(self,index):
        url='http://127.0.0.1:'+str(self.args.port if index==0 else self.args.restore_port)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:
                r=httpx.get(url+'/api/v1/health',trust_env=False,timeout=2)
                if r.status_code==200 and r.json().get('status')=='ok' and r.json().get('worker') is True:
                    require(r.json()['version']==VERSION,'Running container version differs from the current source version')
                    return url,r.json()
            except (httpx.HTTPError,ValueError): pass
            time.sleep(.5)
        raise VerificationError('Created container did not become healthy within 60 seconds')

    @staticmethod
    def api(client,method,path,body=None,**kwargs):
        r=client.request(method,'/api/v1'+path,json=body,**kwargs) if body is not None else client.request(method,'/api/v1'+path,**kwargs)
        r.raise_for_status();return r.json()

    def wait_run(self,client,path,run_id):
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            run=self.api(client,'GET',path+'/runs/'+run_id)['run']
            if run['state'] not in ['QUEUED','RUNNING']: return run
            time.sleep(.2)
        raise VerificationError('Core queued task exceeded 60 seconds')

    def reports_and_files(self,client,path,run_id):
        dashboard=self.api(client,'GET',path+'/dashboard')
        require(dashboard['audit']['valid'] is True,'Audit chain is invalid')
        files=[]
        for f in dashboard['files']:
            r=client.get('/api/v1'+path+'/files/'+f['id']+'/content');r.raise_for_status()
            require(hashlib.sha256(r.content).hexdigest()==f['sha256'],'Original source download hash differs')
            files.append({'filename':f['filename'],'sha256':f['sha256'],'bytes':len(r.content)})
        reports=[]
        for format_,language in [('json','en'),('html','en'),('html','zh-CN')]:
            r=client.get('/api/v1'+path+'/runs/'+run_id+'/report',params={'format':format_,'language':language});r.raise_for_status()
            if format_=='json': require(r.json()['run']['review_state']=='APPROVED','Restored report lost approval')
            else: require(len(r.content)>1000,'HTML report is incomplete')
            reports.append({'format':format_,'language':language,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest()})
        return {'original_files':files,'reports':reports,'audit_valid':True}

    def image_sources(self,image):
        code="import hashlib,json;from pathlib import Path;p=Path('/app');files=[f for d in ['backend/strata','web','dist'] for f in (p/d).rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.pyc'];files+=[p/f for f in ['package.json','backend/requirements.txt','backend/constraints.txt','scripts/week5-environment.py','scripts/backup.py','scripts/tool-bridge.mjs','scripts/prepare-week5.py']];print(json.dumps({f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}))"
        return json.loads(self.command(['run','--rm','--entrypoint','python',image,'-c',code]))

    def final_refresh(self):
        """Display-only source refresh after a separately recorded full chain."""
        reference=self.args.final_source_receipt
        prior=json.loads(reference.read_text())
        require(prior.get('schema')=='strata-docker-verification/1' and prior.get('version')==VERSION and prior.get('status')=='PASS' and prior.get('checks',{}).get('independent_volume_restore',{}).get('result')=='PASS','Final binding requires a same-version actual complete Docker receipt')
        require(self.args.output.resolve()!=reference.resolve(),'Final source binding must not overwrite the full-chain receipt')
        self.result.update(schema='strata-docker-final-binding/1',
            scope='Current source/image identity and one independent synthetic PASS with reports. Full workflow/persistence/restore refer to the separate actual full-chain receipt; not repeated here.',
            full_workflow_reference={'receipt':str(reference),'image':prior['image'],'status':'PASS'})
        for port in [self.args.port,self.args.restore_port]:
            with socket.socket() as sock:
                try:sock.bind(('127.0.0.1',port))
                except OSError as error:raise VerificationError('Selected port is occupied; no existing service will be stopped') from error
        original=json.loads(self.command(['image','inspect',prior['image']['name']]))[0]
        require(original['Id']==prior['image']['id'],'Full-chain image tag identity changed')
        old_source=self.image_sources(prior['image']['name'])
        changed=[p for p,h in old_source.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
        require(set(changed)<= {'web/locales/en.js','web/locales/zh-CN.js'},'Only the reviewed display-language files may use the tiny final refresh; rerun the affected full workflow for other core changes')
        self.result['changed_core_files']=changed
        self.compose(0,'config','--quiet');self.result['checks']['compose_config']='PASS'
        self.phase('final display-source cached image refresh')
        self.compose(0,'build','app',timeout=1200);self.result['checks']['cached_build']='PASS'
        image='strata-week5:'+self.image_tag;info=json.loads(self.command(['image','inspect',image]))[0]
        self.result['image']={'name':image,'id':info['Id'],'os':info['Os'],'architecture':info['Architecture'],'created':info['Created']}
        new_source=self.image_sources(image)
        require(all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in new_source.items()),'Final image runtime source differs from current files')
        self.result['core_source_sha256']=hashlib.sha256(json.dumps(new_source,sort_keys=True).encode()).hexdigest()
        self.result['checks']['image_core_source_hashes']='PASS'
        self.touched.append(0)
        self.compose(0,'run','--rm','--no-deps','app','python','scripts/week5-environment.py','init','--directory','/backups/week5','--port','4180')
        self.compose(0,'up','-d','--no-build','--pull','never','app');url,health=self.wait_health(0)
        state=json.loads(self.compose(0,'exec','-T','app','python','-c',"import json;print(json.dumps(json.load(open('/backups/week5/service.json'))))"))
        require(health.get('week5_instance')==state['nonce'],'Current HTTP service is not bound to the managed instance identity')
        self.result['checks']['health_and_instance_binding']='PASS'
        self.phase('one frozen PASS case, human review and bilingual reports')
        prepare=module('week5_final_prepare',ROOT/'scripts/prepare-week5.py')
        with httpx.Client(base_url=url,trust_env=False,timeout=30) as client:
            auth=self.api(client,'POST','/auth/bootstrap',{'username':self.username,'password':self.password},headers={'X-Setup-Token':self.token})
            client.headers['Authorization']='Bearer '+auth['token']
            prepared=prepare.prepare(client);path='/projects/'+prepared['project_id']
            require(prepared['runs_precomputed']==0,'Preparation unexpectedly precomputed checks')
            self.api(client,'POST',path+'/rules/'+prepared['rule_id']+'/approve')
            evaluation=self.api(client,'POST',path+'/evaluations',{'case_ids':[prepared['cases'][0]]})['evaluation']
            run=self.wait_run(client,path,evaluation['entries'][0]['run_id'])
            compared=self.api(client,'GET',path+'/evaluations/'+evaluation['id'])['evaluation']
            require(compared['state']=='COMPLETED' and compared['summary']['matched']==1 and run['status']=='PASS','Frozen final PASS example did not match')
            self.api(client,'POST',path+'/runs/'+run['id']+'/review',{'action':'approve','note':'SYNTHETIC final display-source binding exercise only; no engineering approval'})
            self.result['checks']['one_independent_pass']=compared['summary']
            self.result['checks']['reports_and_original_files']=self.reports_and_files(client,path,run['id'])
        # Keep any former local tag recoverable; never remove images or volumes.
        old_tag=self.command(['image','ls','--no-trunc','--format','{{.ID}}','--filter','reference=strata-week5:local']).splitlines()
        if old_tag and old_tag[0]!=info['Id']:
            preserved='strata-week5:previous-'+self.nonce;self.command(['image','tag',old_tag[0],preserved]);self.result['previous_local_image_preserved_as']=preserved
        self.command(['image','tag',image,'strata-week5:local'])
        self.result['local_tag']='strata-week5:local';self.result['status']='PASS';self.phase('complete: stop owned final-source test service')

    def run(self):
        self.phase('preflight: unique projects and unused host ports')
        require(ROOT.joinpath('compose.week5.yaml').is_file(),'Week5 override is missing')
        require(self.args.port!=self.args.restore_port,'Use two distinct host ports')
        for port in [self.args.port,self.args.restore_port]:
            require(1024<=port<=65535,'Port must be 1024–65535')
            with socket.socket() as sock:
                try: sock.bind(('127.0.0.1',port))
                except OSError as error: raise VerificationError('Selected port is occupied; no existing service will be stopped') from error
        versions=json.loads(self.command(['version','--format','json']))
        # Keep machine paths, context settings and operator details out of the
        # public receipt; the actual command transcript remains private.
        self.result['engine']={side:{key:versions.get(side,{}).get(key)
            for key in ['Version','ApiVersion','Os','Arch','KernelVersion']}
            for side in ['Client','Server']}
        compose_version=self.command(['compose','version','--short'])
        numbers=tuple(int(x) for x in re.findall(r'\d+',compose_version)[:3])
        require(numbers>=(2,24,4),'Compose >=2.24.4 is required for safe !override merging')
        self.result['compose_version']=compose_version
        self.compose(0,'config','--quiet');self.result['checks']['compose_config']='PASS'
        # No-cache application build. Record the produced OCI image identity.
        if getattr(self.args,'reuse_image_receipt',None):
            receipt=json.loads(self.args.reuse_image_receipt.read_text())
            image=receipt.get('image',{})
            prior_version=receipt.get('version','')
            same_version=prior_version==VERSION
            candidate_promoted=bool(getattr(self.args,'refresh_reused_image',False) and re.fullmatch(re.escape(VERSION)+r'-rc\.\d+',prior_version))
            require(receipt.get('schema')=='strata-docker-verification/1' and (same_version or candidate_promoted) and receipt.get('checks',{}).get('clean_build')=='PASS','Reuse requires the same release-line actual clean-build receipt; candidate promotion needs a cached refresh')
            prefix='strata-week5:'+prior_version+'-check-'
            require(image.get('name','').startswith(prefix) and re.fullmatch(r'[0-9a-f]{10}',image['name'][len(prefix):]),'Reuse image is outside the verifier-owned namespace')
            info=json.loads(self.command(['image','inspect',image['name']]))[0]
            require(info['Id']==image['id'],'Reuse image tag no longer binds to the first image ID')
            self.result['checks']['clean_build']='PASS'
            self.result['build_reused_from']={'receipt':str(self.args.reuse_image_receipt),'version':prior_version,'image_id':info['Id'],'note':'Clean-build check comes from this actual first receipt. API workflow repeats to use new ephemeral credentials, not new independent test samples.'}
            if getattr(self.args,'refresh_reused_image',False):
                self.phase('cached application refresh; preserve original no-cache build evidence')
                self.compose(0,'build','app',timeout=1200)
                self.result['checks']['cached_application_rebuild']='PASS'
                self.result['build_reused_from']['mode']='Original clean build plus cached source refresh; current image identity and runtime-source hashes checked separately'
            else:
                self.image_tag=image['name'].split(':',1)[1]
                self.phase('reuse exact previously verified image; no rebuild')
                self.result['build_reused_from']['mode']='Exact original image; no rebuild'
        else:
            self.phase('clean image build')
            self.compose(0,'build','--no-cache','app',timeout=1200);self.result['checks']['clean_build']='PASS'
        image='strata-week5:'+self.image_tag
        info=json.loads(self.command(['image','inspect',image]))[0]
        self.result['image']={'name':image,'id':info['Id'],'os':info['Os'],'architecture':info['Architecture'],'created':info['Created']}
        image_core=self.image_sources(image)
        source_core={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in image_core}
        require(image_core==source_core,'Image runtime source differs from current core source; rebuild is required')
        self.result['core_source_sha256']=hashlib.sha256(json.dumps(source_core,sort_keys=True).encode()).hexdigest()
        self.result['checks']['image_core_source_hashes']='PASS'
        fixture_code="import hashlib,json;from pathlib import Path;p=Path('/app/examples/week5');print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file()}))"
        in_image=json.loads(self.command(['run','--rm','--entrypoint','python',image,'-c',fixture_code]))
        expected={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'examples/week5').iterdir() if f.is_file()}
        require(in_image==expected,'Week5 image fixtures are missing, extra or differ from source')
        self.result['checks']['image_fixture_hashes']='PASS'
        self.result['fixture_sha256']=expected
        self.phase('initialise two independent volumes and start application')
        for i in [0,1]:
            self.touched.append(i)
            self.compose(i,'run','--rm','--no-deps','app','python','scripts/week5-environment.py','init','--directory','/backups/week5','--port','4180')
        self.compose(0,'up','-d','--no-build','--pull','never','app')
        url,health=self.wait_health(0);self.result['checks']['base_health']='PASS'
        prepare=module('week5_docker_prepare',ROOT/'scripts/prepare-week5.py')
        with httpx.Client(base_url=url,trust_env=False,timeout=30) as c:
            setup=self.api(c,'GET','/auth/setup');require(setup['needs_setup'] and setup['token_required'],'Docker first setup protection was not enabled')
            auth=self.api(c,'POST','/auth/bootstrap',{'username':self.username,'password':self.password},headers={'X-Setup-Token':self.token})
            c.headers['Authorization']='Bearer '+auth['token'];old_token=auth['token']
            require(self.api(c,'GET','/model')['enabled'] is False,'Week5 model unexpectedly enabled')
            require(self.api(c,'GET','/tools')['etabs']['configured'] is False,'Week5 CSI unexpectedly enabled')
            require(self.api(c,'GET','/ocr')['available'] is False,'Linux image unexpectedly reports macOS Vision available')
            prepared=prepare.prepare(c);path='/projects/'+prepared['project_id']
            require(prepared['runs_precomputed']==0,'Primary preparation must not precompute results')
            self.api(c,'POST',path+'/rules/'+prepared['rule_id']+'/approve')
            self.phase('independent PASS / FAIL / NOT VERIFIED and human review')
            evaluation=self.api(c,'POST',path+'/evaluations',{'case_ids':prepared['cases']})['evaluation']
            for entry in evaluation['entries']: self.wait_run(c,path,entry['run_id'])
            evaluated=self.api(c,'GET',path+'/evaluations/'+evaluation['id'])['evaluation']
            require(evaluated['state']=='COMPLETED' and evaluated['summary']['matched']==3 and evaluated['summary']['false_pass_cases']==0,'Independent PASS/FAIL/missing-evidence cases did not all match')
            self.result['checks']['independent_core_cases']=evaluated['summary']
            fail_entry=next(e for e in evaluation['entries'] if e['case']['case_id']=='W5-FAIL')
            repair=self.api(c,'POST',path+'/snapshots',{'file_id':prepared['files']['repair'],'title':'SYNTHETIC corrected export 195 kN','parent_id':prepared['snapshots']['fail'],'mapping_note':'Separate synthetic corrected original file; no silent edits'})['snapshot']
            resumed=self.api(c,'POST',path+'/runs/'+fail_entry['run_id']+'/resume',{'snapshot_id':repair['id']})['run']
            passed=self.wait_run(c,path,resumed['id']);require(passed['status']=='PASS' and passed['state']=='COMPLETED','Linked corrected run did not pass')
            draft=c.get('/api/v1'+path+'/runs/'+passed['id']+'/report',params={'format':'html','language':'en'});draft.raise_for_status()
            require('DRAFT - NOT REVIEWED' in draft.text,'Unreviewed PASS report has no clear draft warning')
            d=self.api(c,'GET',path+'/dashboard');issues=[i for i in d['issues'] if i['source_run_id']==fail_entry['run_id']]
            require(bool(issues),'Deliberate failing case did not publish its issue')
            for issue in issues:self.api(c,'POST',path+'/issues/'+issue['id'],{'action':'resolve','resolution_run_id':passed['id'],'note':'SYNTHETIC correction validated against independent 195 kN expectation; software exercise only'})
            self.api(c,'POST',path+'/runs/'+passed['id']+'/review',{'action':'approve','note':'SYNTHETIC software workflow check, not structural design approval'})
            approved=self.api(c,'GET',path+'/runs/'+passed['id'])['run'];require(approved['review_state']=='APPROVED' and not approved['stale'],'Approval is not current')
            before=self.reports_and_files(c,path,passed['id']);self.result['checks']['correction_review_reports']=before
            before_issues=self.api(c,'GET',path+'/dashboard')['issues']
            resolved_ids=[issue['id'] for issue in issues]
            self.result['checks']['draft_before_human_review']='PASS'
            # A different, frozen synthetic intake exercises the actual
            # container service and worker, not an in-process replacement.
            intake_module=module('week5_docker_intake',ROOT/'scripts/verify-client-intake-v13.py')
            artifact={'schema':'strata-docker-client-intake/1','status':'RUNNING',
                'mode':'actual Docker Linux service / authenticated HTTP / background worker',
                'application_version':VERSION,'material_type':'synthetic',
                'scope':'Independent synthetic intake only; no customer accuracy, native CSI or browser claim.',
                'mapped_inputs':[],'mapping_errors':[],'rules':[],'batches':[]}
            intake_dir=self.args.output.parent/('docker-client-intake-'+self.nonce)
            intake=intake_module.Intake(c,ROOT/'examples/client-intake-v13',intake_dir,artifact)
            self.phase('new independently frozen Excel / CSV / rule intake over HTTP')
            try:intake.execute()
            except Exception as error:
                artifact.update(status='FAIL',failed_phase=intake.phase,
                                error=type(error).__name__+': '+str(error)[:1000])
                raise
            finally:
                (intake_dir/'verification.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
            require(artifact['status']=='PASS','New independent intake did not pass against the container service')
            self.result['checks']['new_independent_intake']={
                'status':artifact['status'],'summary':artifact['summary'],
                'oracle_sha256':artifact['oracle_sha256'],
                'fixture_manifest_sha256':artifact['fixture_manifest_sha256'],
                'receipt':str(intake_dir/'verification.json')}
        self.phase('force-recreate: persistent source bytes, history and review')
        self.compose(0,'up','-d','--no-build','--pull','never','--force-recreate','app')
        url,_=self.wait_health(0)
        with httpx.Client(base_url=url,trust_env=False,timeout=30,headers={'Authorization':'Bearer '+old_token}) as c:
            still=self.api(c,'GET',path+'/runs/'+passed['id'])['run'];require(still['review_state']=='APPROVED' and not still['stale'],'Recreate lost persistent approval')
            persisted=self.reports_and_files(c,path,passed['id']);require(persisted['original_files']==before['original_files'],'Recreate changed original bytes')
        self.result['checks']['container_recreate_persistence']='PASS'
        self.phase('consistent checkpoint and restore into second independent volume')
        self.compose(0,'stop','app')
        self.compose(0,'run','--rm','--no-deps','app','python','scripts/week5-environment.py','checkpoint','--directory','/backups/week5','--name','completed')
        with tempfile.TemporaryDirectory(prefix='strata-week5-docker-check-') as scratch:
            cid=self.compose(0,'ps','-aq','app');require(bool(cid),'Stopped source container is missing')
            self.command(['cp',cid+':/backups/week5/checkpoints/completed',scratch])
            self.copy_checkpoint(Path(scratch)/'completed')
            restored=json.loads(self.compose(1,'run','--rm','--no-deps','app','python','scripts/week5-environment.py','restore','--directory','/backups/week5','--name','completed'))
            require(restored['sessions_invalidated']>=1,'Restore did not revoke the saved sessions')
        self.compose(1,'up','-d','--no-build','--pull','never','app');url,_=self.wait_health(1)
        with httpx.Client(base_url=url,trust_env=False,timeout=30) as c:
            require(c.get('/api/v1/projects',headers={'Authorization':'Bearer '+old_token}).status_code==401,'Old session remained valid after independent restore')
            auth=self.api(c,'POST','/auth/login',{'username':self.username,'password':self.password});c.headers['Authorization']='Bearer '+auth['token']
            recovered=self.api(c,'GET',path+'/runs/'+passed['id'])['run'];require(recovered['review_state']=='APPROVED' and not recovered['stale'],'Recovered approval is missing or stale')
            after=self.reports_and_files(c,path,passed['id']);require(after['original_files']==before['original_files'],'Independent restore changed source bytes')
            d=self.api(c,'GET',path+'/dashboard')
            require(all(any(i['id']==iid and i['state']=='RESOLVED' for i in d['issues']) for iid in resolved_ids),'Recovered linked FAIL issues lost their resolutions')
            require(sorted(d['issues'],key=lambda i:i['id'])==sorted(before_issues,key=lambda i:i['id']),'Independent restore changed the issue register')
            recovered_intake=self.api(c,'GET','/projects/'+artifact['project_id']+'/runs/'+artifact['final_review']['run_id'])['run']
            require(recovered_intake['review_state']=='APPROVED' and not recovered_intake['stale'],'Independent restore lost the new intake review')
        self.result['checks']['independent_volume_restore']={'result':'PASS','old_token_status':401,'sessions_invalidated':restored['sessions_invalidated'],'original_files':len(after['original_files']),'approval':'APPROVED','resolved_linked_issues':len(resolved_ids),'all_issue_history_preserved':True,'not_verified_findings_retained':True,'new_intake_review_preserved':True}
        self.result['status']='PASS'
        self.phase('complete: stop owned test services')

    def finish(self):
        for i in self.touched:
            try:
                self.compose(i,'stop','app')
                running=self.compose(i,'ps','--status','running','-q','app')
                require(not running,'Owned test service remained running after stop')
            except Exception as error:self.result.setdefault('cleanup_warnings',[]).append(type(error).__name__)
        if self.touched:
            self.result['owned_test_services_stopped']=not bool(self.result.get('cleanup_warnings'))
            if self.result.get('cleanup_warnings') and self.result['status']=='PASS':self.result['status']='FAILED'
        self.result['finished_at']=datetime.now(timezone.utc).isoformat()
        self.result['retained_test_volumes']=[self.projects[i]+'_week5-state' for i in self.touched]
        self.args.output.parent.mkdir(parents=True,exist_ok=True)
        log=self.args.output.with_name('docker-commands.private.json')
        try:
            write_private_log(log,json.dumps(self.log,ensure_ascii=False,indent=2)+'\n')
        except Exception as error:
            self.result['status']='FAILED'
            self.result['private_log_error']=type(error).__name__
            self.args.output.write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n')
            raise
        self.args.output.write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--docker',default='docker');p.add_argument('--port',type=int,default=4194);p.add_argument('--restore-port',type=int,default=4195);p.add_argument('--output',type=Path,default=ROOT/'output/week5/docker-verification.json');p.add_argument('--reuse-image-receipt',type=Path,help='Same release-line actual clean-build receipt; binds exact image ID and current core source before reuse');p.add_argument('--refresh-reused-image',action='store_true',help='With the clean-build receipt, perform a cached rebuild for changed application files; preserve the original no-cache evidence');p.add_argument('--final-source-receipt',type=Path,help='Same-version complete PASS receipt; only display-language files may differ; validates current source/image with one PASS and reports');args=p.parse_args()
    if args.refresh_reused_image and not args.reuse_image_receipt:p.error('--refresh-reused-image requires --reuse-image-receipt')
    if args.final_source_receipt and (args.reuse_image_receipt or args.refresh_reused_image):p.error('--final-source-receipt is a separate verification mode')
    v=Verification(args)
    try:v.final_refresh() if args.final_source_receipt else v.run()
    except KeyboardInterrupt:
        v.result['status']='INTERRUPTED'
        v.result['failure']={'type':'KeyboardInterrupt','message':'Verification interrupted; created services are stopped by the owned-project cleanup.'}
    except Exception as error:
        v.result['status']='FAILED' if v.touched or v.result['checks'] else 'NOT RUN'
        v.result['failure']={'type':type(error).__name__,'message':str(error)[:1000]}
    finally:v.finish()
    print(json.dumps({'status':v.result['status'],'evidence':str(args.output),'version':VERSION},ensure_ascii=False))
    return 0 if v.result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
