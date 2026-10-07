"""The executable rule contract. Registered tools only; never eval/code/formula."""
from __future__ import annotations
import math
from .adapters import exact, pointer
from .data_tools import UNITS, _json, _pointer
from .knowledge import validate_rule

REQUIRED = {
    'gravity-full':[f'QA-00{i}' for i in range(1,7)],
    'gravity-distribution':['QA-003'], 'gravity-balance':['QA-005'],
    'load-combination':['COMB-001'], 'combination-configuration':['COMB-CONFIG'],
    'handoff':['HANDOFF'], 'seismic-configuration':['SEISMIC'],
    'mass-source':['MASS-SOURCE'], 'additional-settings':['SETTINGS'],
}
LEGACY={'gravity-full','gravity-distribution','gravity-balance','load-combination'}

def bounded(items,label,maximum=1000):
    if not isinstance(items,list) or not 0<len(items)<=maximum: raise ValueError(f'{label}: expected 1–{maximum} items')

def finite(value):
    try: return type(value) in (int,float) and math.isfinite(value)
    except OverflowError: return False

def scalar(value): return isinstance(value,(str,bool)) or finite(value)

def predicate(item):
    if not isinstance(item,dict): raise ValueError('Comparison must be an object')
    op=item.get('operator')
    exact(item, ['path','operator','min','max'] if op=='range' else ['path','operator','value'],'Comparison')
    pointer(item['path'])
    if op=='range':
        if not finite(item['min']) or not finite(item['max']) or item['min']>item['max']: raise ValueError('Range bounds must be finite and ordered')
    elif op=='eq':
        if not scalar(item['value']): raise ValueError('Equality requires a non-null scalar')
    elif op=='in':
        bounded(item['value'],'Membership')
        if not all(scalar(x) for x in item['value']): raise ValueError('Membership requires non-null scalars')
    else: raise ValueError('Only eq/in/range operators are registered')

def matches(item, data):
    try: value=_pointer(data,item['path'])
    except ValueError: return None
    if not scalar(value): return None
    def equal(a,b): return a==b if finite(a) and finite(b) else type(a) is type(b) and a==b
    if item['operator']=='range': return item['min']<=value<=item['max'] if finite(value) else None
    if item['operator']=='eq': return equal(value,item['value'])
    return any(equal(value,x) for x in item['value'])

def applicable(rule,data):
    """Unknown applicability cannot authorise a check. False predicates exclude."""
    return all(matches(condition,data) is True for condition in rule.get('conditions',[]))

def _executable_rule(value):
    rule=validate_rule(value)
    allowed={'id','project_id','version','title','text','locator','task_ids','check_ids','status','authority','source_sha256','approved_by','approved_at','parameters','conditions'}
    if set(rule)-allowed: raise ValueError('Unsupported executable rule fields; code and formulas are forbidden')
    if any(task not in REQUIRED for task in rule['task_ids']): raise ValueError('Rule references an unregistered tool/task')
    if 'conditions' in rule and (not isinstance(rule['conditions'],list) or len(rule['conditions'])>20): raise ValueError('conditions must be a list of at most 20 comparisons')
    for condition in rule.get('conditions',[]): predicate(condition)
    params=rule.get('parameters',{})
    for task in rule['task_ids']:
        if not set(rule['check_ids']) & set(REQUIRED[task]): raise ValueError(f'Rule check IDs do not cover task {task}')
        if task in LEGACY:
            if rule['authority']!='synthetic' or params: raise ValueError('Legacy arithmetic tools have a fixed synthetic-only profile')
        elif task in {'mass-source','seismic-configuration','additional-settings'}:
            exact(params,['settings'],'Settings parameters'); bounded(params['settings'],'Settings')
            for item in params['settings']: predicate(item)
            if len({p['path'] for p in params['settings']})!=len(params['settings']): raise ValueError('Duplicate setting paths')
        elif task=='combination-configuration':
            exact(params,['required_base_cases','required_combinations','allow_extra_base_cases','allow_extra_combinations','factor_tolerance'],'Combination parameters')
            if any(type(params[x]) is not bool for x in ('allow_extra_base_cases','allow_extra_combinations')) or not finite(params['factor_tolerance']) or params['factor_tolerance']<0: raise ValueError('Explicit finite tolerance and extra-item policies required')
            cases=params['required_base_cases']; bounded(cases,'Base cases')
            if not all(isinstance(x,str) and x for x in cases) or len(set(cases))!=len(cases): raise ValueError('Base case IDs must be unique strings')
            combos=params['required_combinations']; bounded(combos,'Combinations')
            ids=[]
            for combo in combos:
                exact(combo,['id','terms'],'Combination'); ids.append(combo['id']); bounded(combo['terms'],'Terms')
                terms=[]
                for term in combo['terms']:
                    exact(term,['caseId','factor'],'Term')
                    if term['caseId'] not in cases or not finite(term['factor']): raise ValueError('Invalid term reference or factor')
                    terms.append(term['caseId'])
                if len(terms)!=len(set(terms)): raise ValueError('Duplicate terms')
            if any(not isinstance(x,str) or not x for x in ids) or len(ids)!=len(set(ids)) or set(ids)&set(cases): raise ValueError('Invalid combination namespace')
        else:
            exact(params,['source_revision','target_revision','required_source_paths','required_target_paths','mappings'],'Handoff parameters')
            if any(not isinstance(params[k],str) or not params[k] for k in ('source_revision','target_revision')): raise ValueError('Explicit handoff revisions required')
            maps=params['mappings']; bounded(maps,'Mappings')
            for mapping in maps:
                exact(mapping,['id','source_path','target_path','source_unit_path','target_unit_path','comparison_unit','absolute_tolerance','relative_tolerance'],'Handoff mapping')
                if not isinstance(mapping['id'],str) or not mapping['id']: raise ValueError('Mapping ID required')
                for k in ('source_path','target_path','source_unit_path','target_unit_path'): pointer(mapping[k])
                if mapping['comparison_unit'] not in UNITS or any(not finite(mapping[k]) or mapping[k]<0 for k in ('absolute_tolerance','relative_tolerance')): raise ValueError('Known unit and finite nonnegative tolerances required')
            for field in ('id','source_path','target_path'):
                if len({m[field] for m in maps})!=len(maps): raise ValueError(f'Duplicate mapping {field}')
            for side in ('source','target'):
                paths=params['required_'+side+'_paths']; bounded(paths,'Required paths')
                for p in paths: pointer(p)
                if len(paths)!=len(set(paths)) or set(paths)!={m[side+'_path'] for m in maps}: raise ValueError('Required paths must exactly match mappings')
    _json(rule)
    return rule

def registry():
    return [{'task_id':task,'check_ids':ids,'parameters':'none (fixed synthetic profile)' if task in LEGACY else 'explicit settings' if task in {'mass-source','seismic-configuration','additional-settings'} else 'explicit combination configuration' if task=='combination-configuration' else 'explicit transfer manifest','synthetic_only':task in LEGACY} for task,ids in REQUIRED.items()]


def executable_rule(value):
    try:
        return _executable_rule(value)
    except (TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError("Malformed executable_rule configuration; use the documented types") from error
