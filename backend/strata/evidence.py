"""Actionable material requests, based on actual missing tool dependencies."""
from .data_tools import _pointer
from .storage import digest

def requests(results, input_data=None, target=None, missing=None, task=None):
    items=[]; seen=set()
    def add(kind,what,why,where,finding=None):
        key=(kind,what,str(where))
        if key in seen: return
        seen.add(key)
        items.append({'id':'material-'+digest(key)[:12],'kind':kind,'what':what,'why':why,'where':where,'finding':finding,'state':'OPEN'})
    for finding in results:
        for detail in finding.get('details',[]):
            if not isinstance(detail,dict) or detail.get('status')!='NOT VERIFIED': continue
            dependencies=detail.get('dependencies',[])
            requested=False
            # Missing objects are identified by the registered tool, not by
            # parsing a model explanation or guessing customer field names.
            for need in detail.get('materialNeeds',[]):
                requested=True
                field=need['field'];object_id=need['object_id']
                add(need['kind'],field+' / '+object_id,need['reason'],{'view':'Versions','action':'Create a corrected snapshot or re-import the original export','side':'source','field':field,'object_id':object_id},finding['id'])
            sides=[('source',input_data or {})]+([('target',target)] if target is not None else [])
            for side,data in sides:
                # Handoff dependencies belong to explicit input sides. A target
                # path need not exist in the source schema (and vice versa).
                side_paths=detail.get('dependency_sides',{}).get(side,dependencies)
                for path in side_paths:
                    try: value=_pointer(data,path); absent=value is None or path=='/configuration_complete' and value is not True
                    except ValueError: absent=True
                    if not absent: continue
                    requested=True
                    add('input_field',path,detail.get('reason') or 'The deterministic check requires this field.',{'view':'Versions','action':'Create a corrected snapshot or re-import the original export','side':side,'field':path},finding['id']+'/'+str(detail.get('id','detail')))
            if not requested:
                add('data_review',detail.get('path') or detail.get('id') or finding['id'],detail.get('reason') or 'Inspect the explicit source values and mapping.',{'view':'Versions','action':'Inspect source and create a corrected revision; never fill guessed values'},finding['id'])
    for item in missing or []:
        text=str(item)
        if text.startswith('approved rules:'):
            add('rule',text.partition(':')[2].strip(),'This task lacks the required applicable approved rule versions. Conditions may be false or missing.',{'view':'Knowledge','action':'Upload an authorised source, import a rule package, then request reviewer approval'},'WORKFLOW-GATE')
        elif text.startswith('/'):
            add('input_field',text,'Rule applicability cannot be established without this explicit field.',{'view':'Versions','action':'Supply the source value and create a corrected snapshot','field':text,'side':'source'},'WORKFLOW-GATE')
        elif text in ('snapshot','compare_to'):
            add('input_file','Target snapshot' if text=='compare_to' else 'Input snapshot','A stored, traceable engineering input is required.',{'view':'Workspace','action':'Upload a source, apply an adapter and select this snapshot','field':text},'WORKFLOW-GATE')
        elif not items:
            add('workflow_review',text,'The workflow did not establish enough evidence to verify this request.',{'view':'Review','action':'Inspect execution trace, supply the stated material, then create a linked follow-up'},'WORKFLOW-GATE')
    if not items and any(r.get('status')=='NOT VERIFIED' for r in results):
        add('workflow_review','Unverified tool prerequisites','Inspect the tool reason; no missing values or methods were inferred.',{'view':'Review','action':'Inspect findings and rule parameters before a linked rerun'})
    return items
