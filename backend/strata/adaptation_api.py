"""Project-scoped adaptation resources, retaining the existing storage and worker."""
import base64
import hashlib
from fastapi import Body, Depends, HTTPException
from .adapters import validate_profile, apply_profile, exact
from .contracts import executable_rule, registry
from .storage import public, digest, canonical
from .data_tools import ingest


def register_adaptation(app, store, runner, user, access, resource, require_fields, add_file, add_snapshot, source_contains, new_run, run_view):
    prefix='/api/v1/projects/{project_id}'

    @app.get('/api/v1/tool-contracts')
    def contracts(account=Depends(user)):
        return {'items':registry(),'policy':'Only implemented deterministic tools; no uploaded code or formulas.'}

    @app.post(prefix+'/adapters')
    def save_adapter(project_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['profile'],['profile']); profile=validate_profile(body['profile'])
        with store.session.begin() as session:
            access(session,project_id,account,{'engineer','reviewer'})
            if any(r.data['profile']['id']==profile['id'] and r.data['profile']['version']==profile['version'] for r in store.list(session,project_id,'adapter')): raise HTTPException(409,'Adapter version already exists; register a new version')
            row=store.add(session,'adapter',project_id,{'profile':profile,'profile_hash':digest(profile),'created_by':account['id']})
            store.audit(session,project_id,account['id'],'adapter.created',row.id,{'hash':digest(profile)})
            return {'adapter':public(row)}

    @app.get(prefix+'/adapters')
    def adapters(project_id:str,account=Depends(user)):
        with store.session() as session:
            access(session,project_id,account)
            return {'items':[public(r) for r in store.list(session,project_id,'adapter')]}

    @app.get(prefix+'/adapters/{adapter_id}/export')
    def export_adapter(project_id:str,adapter_id:str,account=Depends(user)):
        with store.session() as session:
            access(session,project_id,account)
            row=resource(session,project_id,'adapter',adapter_id)
            if digest(row.data['profile'])!=row.data['profile_hash']: raise ValueError('Adapter integrity failed')
            return row.data['profile']

    @app.post(prefix+'/adapters/{adapter_id}/apply')
    def mapping(project_id:str,adapter_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['file_id','title','parent_id','preview'],['file_id'])
        if 'preview' in body and type(body['preview']) is not bool: raise ValueError('preview must be boolean')
        with store.session.begin() as session:
            project,_=access(session,project_id,account,{'engineer','reviewer'})
            adapter=resource(session,project_id,'adapter',adapter_id)
            if digest(adapter.data['profile'])!=adapter.data['profile_hash']: raise ValueError('Adapter integrity failed')
            source=resource(session,project_id,'file',body['file_id'])
            result=apply_profile(source.data['filename'],store.get_blob(source.data['sha256']),adapter.data['profile'])
            if body.get('preview'): return {'mapping':result,'preview':True}
            snap=add_snapshot(session,project,source,{'input':result['input'],'title':body.get('title'),'parent_id':body.get('parent_id'),'mapping_note':f"Explicit adapter {adapter.data['profile']['id']} / {adapter.data['profile']['version']}"},account['id'])
            store.change(session,snap,{**snap.data,'mapping':'adapter','adapter_id':adapter.id,'adapter_hash':result['adapter_sha256'],'provenance':result['provenance']})
            store.audit(session,project_id,account['id'],'adapter.applied',snap.id,{'adapter_id':adapter.id,'file_id':source.id,'source_sha256':source.data['sha256']})
            return {'snapshot':public(snap)}

    def prepare_package(package,project_id):
        exact(package,['schema','title','material_type','rules','sources'],'Rule package')
        if package['schema']!='strata-rule-package/1' or package['material_type'] not in ('synthetic','client') or not isinstance(package['title'],str) or not 1<=len(package['title'])<=160: raise ValueError('Invalid rule package metadata')
        if not isinstance(package['rules'],list) or not 1<=len(package['rules'])<=50 or not isinstance(package['sources'],list) or len(package['sources'])>20: raise ValueError('Rule package limits: 1–50 rules, at most 20 sources')
        files={}; total=0
        for source in package['sources']:
            exact(source,['filename','sha256','content_base64'],'Package source')
            from pathlib import Path
            if not isinstance(source["filename"],str) or not source["filename"] or len(source["filename"])>180 or Path(source["filename"]).name!=source["filename"] or "\\" in source["filename"]: raise ValueError("Package sources require simple filenames")
            try: content=base64.b64decode(source['content_base64'],validate=True)
            except (ValueError,TypeError) as error: raise ValueError('Invalid package source base64') from error
            total+=len(content)
            if total>10_000_000: raise ValueError('Rule package sources exceed 10 MB')
            sha=hashlib.sha256(content).hexdigest()
            if sha!=source['sha256'] or sha in files: raise ValueError('Duplicate or mismatched package source hash')
            # Preflight all sources before mutating the database.
            ingest(source['filename'],content)
            files[sha]=(source['filename'],content)
        rules=[executable_rule({**r,'project_id':project_id,'status':'draft','approved_by':None,'approved_at':None}) for r in package['rules'] if isinstance(r,dict)]
        if len(rules)!=len(package['rules']) or len({(r['id'],r['version']) for r in rules})!=len(rules): raise ValueError('Invalid or duplicate rule versions')
        if any(r['authority']!=package['material_type'] for r in rules): raise ValueError('Package authority must match every rule')
        return rules,files

    @app.post(prefix+'/rule-packages/validate')
    def validate_package(project_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['package'],['package'])
        with store.session() as session:
            access(session,project_id,account,{'engineer','reviewer'})
            rules,files=prepare_package(body['package'],project_id)
            check_package_sources(session,project_id,rules,files)
        return {'valid':True,'rules':len(rules),'sources':len(files),'approval_policy':'Import creates drafts; local reviewer approval required'}

    def check_package_sources(session,project_id,rules,files):
        from types import SimpleNamespace
        for rule in rules:
            sha=rule['source_sha256']
            if sha in files:
                filename,content=files[sha]
                extraction=ingest(filename,content)
                source=SimpleNamespace(data={'filename':filename,'sha256':sha,'ingestion':extraction})
            else:
                source=next((s for s in store.list(session,project_id,'file') if s.data['sha256']==sha),None)
            if source is None or not source_contains(source,rule['text'],raw=files[sha][1] if sha in files else None): raise ValueError(f"Rule {rule['id']}/{rule['version']}: exact source excerpt missing")

    @app.post(prefix+'/rule-packages/import')
    def import_package(project_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['package'],['package'])
        with store.session.begin() as session:
            access(session,project_id,account,{'engineer','reviewer'})
            rules,files=prepare_package(body['package'],project_id)
            check_package_sources(session,project_id,rules,files)
            existing={(r.data['rule']['id'],r.data['rule']['version']) for r in store.list(session,project_id,'rule')}
            if any((r['id'],r['version']) in existing for r in rules): raise HTTPException(409,'A package rule version already exists')
            known={f.data['sha256'] for f in store.list(session,project_id,'file')}
            for sha,(filename,content) in files.items():
                if sha not in known: add_file(session,project_id,filename,content,account['id'])
            rows=[store.add(session,'rule',project_id,{'rule':rule,'created_by':account['id'],'package_title':body['package']['title']}) for rule in rules]
            store.audit(session,project_id,account['id'],'rule_package.imported',project_id,{'rules':[r.id for r in rows],'hash':digest(body['package'])})
            return {'rules':[public(r) for r in rows],'approval_policy':'Drafts only; imported approval metadata is never trusted'}

    @app.get(prefix+'/rule-packages/export')
    def export_package(project_id:str,material_type:str='synthetic',account=Depends(user)):
        if material_type not in ('synthetic','client'): raise ValueError('Select synthetic or client material_type')
        with store.session() as session:
            access(session,project_id,account,{'reviewer'})
            rules=[r.data['rule'] for r in store.list(session,project_id,'rule') if r.data['rule']['authority']==material_type and r.data['rule']['status']!='retired']
            if not rules: raise ValueError('No exportable rules of this material type')
            sources=[]
            for sha in sorted({r['source_sha256'] for r in rules}):
                source=next((f for f in store.list(session,project_id,'file') if f.data['sha256']==sha),None)
                if not source: raise ValueError('Rule source is unavailable')
                sources.append({'filename':source.data['filename'],'sha256':sha,'content_base64':base64.b64encode(store.get_blob(sha)).decode()})
            package={'schema':'strata-rule-package/1','title':f"{material_type} rule package",'material_type':material_type,'rules':rules,'sources':sources}
            prepare_package(package,project_id)
            return package
    from .cases import validate_case, compare, summary

    @app.post(prefix+'/cases')
    def save_case(project_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['case'],['case']); case=validate_case(body['case'])
        with store.session.begin() as session:
            access(session,project_id,account,{'engineer','reviewer'})
            snapshots=[resource(session,project_id,'snapshot',case[key]) for key in ('snapshot_id','compare_to') if case.get(key)]
            if any(type(snap.data['input'].get('synthetic')) is not bool or snap.data['input']['synthetic']!=(case['authority']=='synthetic') for snap in snapshots): raise ValueError('Case authority must match every input snapshot')
            if any(r.data['case']['case_id']==case['case_id'] and r.data['case']['version']==case['version'] for r in store.list(session,project_id,'case')): raise HTTPException(409,'Case version exists; create a new version')
            for binding in case['rule_versions']:
                if not any(r.data['rule']['id']==binding['id'] and r.data['rule']['version']==binding['version'] and r.data['rule']['authority']==case['authority'] for r in store.list(session,project_id,'rule')): raise ValueError(f"Missing matching rule version {binding['id']}/{binding['version']}")
            row=store.add(session,'case',project_id,{'case':case,'oracle_hash':digest(case),'created_by':account['id'],'input_hashes':{s.id:s.data['input_hash'] for s in snapshots}})
            store.audit(session,project_id,account['id'],'case.registered',row.id,{'oracle_hash':digest(case),'independence':'Declared by author; client engineer must verify'})
            return {'case':public(row)}

    @app.get(prefix+'/cases')
    def cases(project_id:str,account=Depends(user)):
        with store.session() as session:
            access(session,project_id,account)
            return {'items':[public(r) for r in store.list(session,project_id,'case')]}

    @app.post(prefix+'/evaluations')
    def evaluate(project_id:str,body:dict=Body(...),account=Depends(user)):
        require_fields(body,['case_ids'],['case_ids'])
        ids=body['case_ids']
        if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids): raise ValueError('Select 1–20 unique case resource IDs')
        with store.session.begin() as session:
            access(session,project_id,account,{'engineer','reviewer'})
            queued=sum(r.data['state'] in {'QUEUED','RUNNING'} for r in store.list(session,project_id,'run'))
            if queued+len(ids)>20: raise HTTPException(429,'Project queue is full; wait before submitting this batch')
            entries=[]
            for cid in ids:
                row=resource(session,project_id,'case',cid);case=row.data['case']
                if digest(case)!=row.data['oracle_hash']: raise ValueError('Case oracle integrity failed')
                for sid,sha in row.data['input_hashes'].items():
                    snap=resource(session,project_id,'snapshot',sid)
                    if digest(snap.data['input'])!=sha: raise ValueError('Case input integrity failed')
                rules=store.list(session,project_id,'rule')
                for binding in case['rule_versions']:
                    if not any(r.data['rule']['id']==binding['id'] and r.data['rule']['version']==binding['version'] and r.data['rule']['status']=='approved' for r in rules): raise ValueError('Case requires the pinned approved rule versions')
                run=new_run(session,project_id,{key:case[key] for key in ('snapshot_id','task_id','compare_to') if key in case}|{'use_model':False,'pinned_rule_versions':case['rule_versions']},account['id'])
                entries.append({'case_id':cid,'case':case,'oracle_hash':row.data['oracle_hash'],'run_id':run.id})
            evaluation=store.add(session,'evaluation',project_id,{'entries':entries,'entries_hash':digest(entries),'created_by':account['id']})
            store.audit(session,project_id,account['id'],'evaluation.queued',evaluation.id,{'cases':ids,'entries_hash':digest(entries)})
            return {'evaluation':public(evaluation)}

    def evaluation_view(session,project,row):
        entries=row.data['entries']
        if digest(entries)!=row.data['entries_hash']: raise ValueError('Evaluation oracle integrity failed')
        items=[]
        for entry in entries:
            if digest(entry['case'])!=entry['oracle_hash']: raise ValueError('Evaluation case integrity failed')
            run=run_view(session,project,resource(session,project.id,'run',entry['run_id']))
            items.append(compare(entry['case'],run))
        finished=[i for i in items if i['state'] not in {'QUEUED','RUNNING'}]
        return {'id':row.id,'created_at':row.created_at,'state':'RUNNING' if len(finished)!=len(items) else 'COMPLETED','progress':{'finished':len(finished),'total':len(items)},'summary':summary(finished),'items':items,'scope':'Declared independent oracles. Synthetic cases are software tests; client technical validation is still required.'}

    @app.get(prefix+'/evaluations/{evaluation_id}')
    def get_evaluation(project_id:str,evaluation_id:str,account=Depends(user)):
        with store.session() as session:
            project,_=access(session,project_id,account)
            return {'evaluation':evaluation_view(session,project,resource(session,project_id,'evaluation',evaluation_id))}

    @app.get(prefix+'/evaluations/{evaluation_id}/report')
    def evaluation_report(project_id:str,evaluation_id:str,account=Depends(user)):
        from fastapi.responses import Response
        with store.session() as session:
            project,_=access(session,project_id,account)
            result=evaluation_view(session,project,resource(session,project_id,'evaluation',evaluation_id))
            return Response(canonical(result),media_type='application/json',headers={'Content-Disposition':'attachment; filename="case-evaluation.json"'})
