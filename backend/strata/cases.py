"""Independent case oracles and comparisons. No expected answer from tool output."""
import copy
from .adapters import exact
from .contracts import REQUIRED, finite
from .storage import digest
from .data_tools import _json, _pointer

STATUSES={'PASS','FAIL','NOT VERIFIED'}
SCHEMA='strata-case/1'

def _validate_case(value):
    _json(value)
    required={'schema','case_id','version','title','authority','task_id','snapshot_id','rule_versions','expected','truth'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'compare_to'}: raise ValueError('Case has missing or unsupported fields')
    if value['schema']!=SCHEMA or value['authority'] not in ('synthetic','client') or value['task_id'] not in REQUIRED: raise ValueError('Unsupported case schema, authority or task')
    for key in ('case_id','version','title','snapshot_id'):
        if not isinstance(value[key],str) or not 1<=len(value[key])<=160: raise ValueError(f'Invalid case {key}')
    if 'compare_to' in value and (not isinstance(value['compare_to'],str) or not value['compare_to']): raise ValueError('compare_to must reference a target snapshot')
    bindings=value['rule_versions']
    if not isinstance(bindings,list) or not 0<len(bindings)<=50: raise ValueError('Pin 1–50 independent rule versions')
    for binding in bindings:
        exact(binding,['id','version'],'Rule binding')
        if any(not isinstance(v,str) or not v or len(v)>128 for v in binding.values()): raise ValueError('Rule binding needs ID and version')
    if len({b['id'] for b in bindings})!=len(bindings): raise ValueError('Duplicate rule bindings')
    truth=value['truth'];exact(truth,['author','basis','independent'],'Truth provenance')
    if truth['independent'] is not True or any(not isinstance(truth[k],str) or not truth[k].strip() or len(truth[k])>2000 for k in ('author','basis')): raise ValueError('Record independent truth author and basis; system outputs are not a valid oracle')
    expected=value['expected'];exact(expected,['status','findings','complete'],'Expected result')
    if expected['status'] not in STATUSES or type(expected['complete']) is not bool or not isinstance(expected['findings'],list) or not 0<len(expected['findings'])<=1000: raise ValueError('Explicit status and per-item expectations required')
    keys=[]
    for finding in expected['findings']:
        if not isinstance(finding,dict) or not {'key','status'}<=set(finding) or set(finding)-{'key','status','numbers'}: raise ValueError('Invalid expected finding')
        if not isinstance(finding['key'],str) or not 1<=len(finding['key'])<=256 or finding['status'] not in STATUSES: raise ValueError('Invalid finding key/status')
        keys.append(finding['key'])
        if 'numbers' in finding:
            numbers=finding['numbers']
            if not isinstance(numbers,list) or not 0<len(numbers)<=20: raise ValueError('Expected 1–20 numeric assertions')
            for number in numbers:
                exact(number,['path','value','absolute_tolerance','relative_tolerance'],'Numeric assertion')
                from .adapters import pointer
                pointer(number['path'])
                if not all(finite(number[k]) for k in ('value','absolute_tolerance','relative_tolerance')) or number['absolute_tolerance']<0 or number['relative_tolerance']<0: raise ValueError('Numeric oracle and tolerances must be finite; never infer tolerance')
    if len(keys)!=len(set(keys)): raise ValueError('Duplicate expected finding keys')
    return copy.deepcopy(value)

def flattened(results):
    found={}
    for finding in results:
        key=finding.get('id')
        if not isinstance(key,str) or key in found: raise ValueError('Duplicate or invalid observed finding IDs')
        found[key]=finding
        for item in finding.get('details',[]):
            if not isinstance(item,dict) or not item.get('id'): continue
            child=key+'/'+item['id']
            if child in found: raise ValueError('Duplicate observed detail IDs')
            if item.get('status') in STATUSES: found[child]=item
    return found

def compare(case,run):
    """Evaluate pinned inputs; workspace active revision is irrelevant to a case.

    Rule/tool/source integrity and recorded execution errors still invalidate it.
    complete=True rejects unexpected FAIL/NOT VERIFIED items; extra PASS details
    are allowed so engines can add informational checks without masking failures.
    """
    validate_case(case)
    observations=flattened(run.get('results',[]))
    rows=[]; totals={'missed_issues':0,'false_alarms':0,'false_pass':0,'insufficient_evidence':0,'numeric_mismatches':0,'missing_findings':0,'unexpected_findings':0}
    invalid=[reason for reason in run.get('stale_reasons',[]) if reason!='A newer input revision is active']
    invalid+=['Execution did not finish successfully'] if run.get('state') in {'ERROR','CANCELLED','QUEUED','RUNNING'} else []
    for expected in case['expected']['findings']:
        actual=observations.get(expected['key']); status=actual.get('status') if actual else 'MISSING'
        row={'key':expected['key'],'expected':expected['status'],'actual':status,'matched':expected['status']==status and not invalid,'numbers':[]}
        if actual is None: totals['missing_findings']+=1
        if expected['status']=='FAIL' and status!='FAIL': totals['missed_issues']+=1
        if expected['status']!='FAIL' and status=='FAIL': totals['false_alarms']+=1
        if expected['status']!='PASS' and status=='PASS': totals['false_pass']+=1
        if status=='NOT VERIFIED': totals['insufficient_evidence']+=1
        for number in expected.get('numbers',[]):
            observed=None
            try: observed=_pointer(actual or {},number['path'])
            except ValueError: pass
            tolerance=max(number['absolute_tolerance'],abs(number['value'])*number['relative_tolerance'])
            ok=finite(observed) and finite(tolerance) and abs(observed-number['value'])<=tolerance
            row['numbers'].append({**number,'actual':observed,'tolerance':tolerance,'matched':ok})
            if not ok: totals['numeric_mismatches']+=1;row['matched']=False
        rows.append(row)
    expected_keys={e['key'] for e in case['expected']['findings']}
    unexpected=[]
    if case['expected']['complete']:
        # A child expectation also accounts for its parent aggregate.
        accounted=expected_keys|{key.split('/')[0] for key in expected_keys}
        unexpected=[{'key':key,'actual':item['status']} for key,item in observations.items() if key not in accounted and item['status']!='PASS']
        totals['unexpected_findings']=len(unexpected)
    status_match=run.get('status')==case['expected']['status']
    return {'case_id':case['case_id'],'version':case['version'],'title':case['title'],'authority':case['authority'],'run_id':run.get('id'),'expected':case['expected']['status'],'actual':run.get('status'),'state':run.get('state'),'matched':status_match and all(r['matched'] for r in rows) and not unexpected and not invalid,'false_pass_case':case['expected']['status']!='PASS' and run.get('status')=='PASS','invalid_reasons':invalid,'counts':totals,'items':rows,'unexpected_items':unexpected,'truth':case['truth'],'oracle_sha256':digest(case),'scope':'Pinned case inputs. A match evaluates this declared oracle, not structural safety.'}

def summary(items):
    keys=['missed_issues','false_alarms','false_pass','insufficient_evidence','numeric_mismatches','missing_findings','unexpected_findings']
    return {'total':len(items),'matched':sum(i['matched'] for i in items),'false_pass_cases':sum(i['false_pass_case'] for i in items),'expected_nonpass_cases':sum(i['expected']!='PASS' for i in items),'invalid_cases':sum(bool(i['invalid_reasons']) for i in items),'findings':{key:sum(i['counts'][key] for i in items) for key in keys}}


def validate_case(value):
    try:
        return _validate_case(value)
    except (TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError("Malformed validate_case configuration; use the documented types") from error
