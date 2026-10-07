"""Different source/target schemas must yield actionable, correctly sided requests."""
from copy import deepcopy
import pytest
from strata.data_tools import verify_handoff
from strata.evidence import requests

@pytest.mark.parametrize('missing_side', ['source', 'target', 'both'])
def test_distinct_handoff_paths_request_only_their_own_side(missing_side):
    source={'schemaVersion':'generic-1.0','project':{'revision':'S17'},'loads':{'force':1850000,'unit':'N'}}
    target={'schemaVersion':'generic-1.0','project':{'revision':'T6'},'received':{'force':1850,'unit':'kN'}}
    rule={'id':'synthetic-side-test','version':'1','approved':True,'source_revision':'S17','target_revision':'T6',
          'required_source_paths':['/loads/force'],'required_target_paths':['/received/force'],
          'mappings':[{'id':'different-schemas','source_path':'/loads/force','target_path':'/received/force',
                       'source_unit_path':'/loads/unit','target_unit_path':'/received/unit','comparison_unit':'kN',
                       'absolute_tolerance':.25,'relative_tolerance':0}]}
    if missing_side in ('source','both'):source['loads']={}
    if missing_side in ('target','both'):target['received']={}
    originals=deepcopy((source,target,rule))
    outcome=verify_handoff(source,target,rule)
    assert outcome['status']=='NOT VERIFIED'
    needed=requests([{'id':'HANDOFF',**outcome}],source,target)
    pairs={(v['where']['side'],v['where']['field']) for v in needed}
    expected=set()
    if missing_side in ('source','both'):expected|={('source','/loads/force'),('source','/loads/unit')}
    if missing_side in ('target','both'):expected|={('target','/received/force'),('target','/received/unit')}
    assert pairs==expected
    assert (source,target,rule)==originals

def test_missing_combination_object_has_a_concrete_material_destination():
    result={'id':'C1','status':'NOT VERIFIED','details':[{'status':'NOT VERIFIED','materialNeeds':[{'kind':'input_field','field':'/baseCases','object_id':'LIVE','reason':'Missing independent base case LIVE; unknown or nested combinations cannot be evaluated.'}]}]}
    needed=requests([result],{'baseCases':[{'id':'SDL','value':100}]})
    assert len(needed)==1
    assert needed[0]['what']=='/baseCases / LIVE'
    assert needed[0]['where']['side']=='source' and needed[0]['where']['object_id']=='LIVE'
    assert needed[0]['where']['field']=='/baseCases' and needed[0]['where']['view']=='Versions'
