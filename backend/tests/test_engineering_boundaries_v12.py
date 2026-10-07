"""Hand-authored synthetic adversarial cases, never client engineering approval."""
import copy
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from strata.adapters import MappingError, apply_profile, validate_profile
from strata.contracts import applicable, executable_rule, matches
from strata.data_tools import DataValidationError, ingest, verify_handoff, verify_settings
from strata.knowledge import check_coverage, retrieve


def adapter(fmt='csv', mode='rows'):
    return {'schema':'strata-adapter/1','id':'SYNTHETIC-ROWS','version':'1',
            'title':'SYNTHETIC explicit object-force table','authority':'synthetic','format':fmt,
            'base':{'synthetic':True},'tables':[{'source':'csv' if fmt=='csv' else '/rows' if fmt=='json' else 'Loads',
            'target':'/objects','mode':mode,'ignored_columns':[],
            'fields':[{'aliases':['Object','Object Name'],'target':'/id','type':'string','required':True},
                      {'aliases':['Force','Vertical'],'target':'/value','type':'number','required':True,
                       'unit':{'aliases':['Unit'],'target':'kN','output':'/unit'}}]}]}


def xlsx(rows, second=None):
    book=Workbook(); book.active.title='Loads'
    for row in rows: book.active.append(row)
    if second:
        sheet=book.create_sheet('Other')
        for row in second: sheet.append(row)
    stream=io.BytesIO();book.save(stream);book.close();return stream.getvalue()


@pytest.mark.parametrize('literal',['1e-999','-1e-999','1e999'])
def test_json_numeric_loss_is_located_and_rejected(literal):
    raw=('{"rows":[{"Object":"A","Force":'+literal+',"Unit":"kN"}]}').encode()
    with pytest.raises(MappingError) as caught: apply_profile('raw.json',raw,adapter('json'))
    error=caught.value.errors[0]
    assert error['file']=='raw.json' and error['table']=='/rows' and error['field']=='/rows/0/Force'
    assert 'flow' in error['reason'].lower()


def test_json_source_pointer_and_original_value_survive_conversion():
    result=apply_profile('raw.json',b'{"rows":[{"Object Name":"A","Vertical":-1250,"Unit":"N"}]}',adapter('json'))
    item=next(p for p in result['provenance'] if p['target']=='/objects/0/value')
    assert item['original_value']==-1250 and item['value']==-1.25
    assert item['location']['json_pointer']=='/rows/0/Vertical'


def test_empty_rows_preserve_physical_source_lines_and_column_order():
    definition=adapter(); definition['tables'][0]['ignored_columns']=['Comment']
    raw=b'Comment,Unit,Vertical,Object Name\n\n,,,\ntrace,N,1000,A\n'
    mapped=apply_profile('raw.csv',raw,definition)
    assert mapped['input']['objects']==[{'id':'A','unit':'kN','value':1}]
    assert all(item['location']['row']==4 for item in mapped['provenance'])


def test_partially_empty_rows_are_not_discarded():
    with pytest.raises(MappingError) as caught:
        apply_profile('partial.csv',b'Object,Force,Unit\nA,,kN\n',adapter())
    assert caught.value.errors[0]['row']==2 and caught.value.errors[0]['field']=='Force'


def test_explicit_duplicate_identity_reports_both_rows_without_merging():
    definition=adapter();definition['tables'][0]['unique_by']=['/id']
    with pytest.raises(MappingError) as caught:
        apply_profile('duplicate.csv',b'Object,Force,Unit\nA,1,kN\nA,2,kN\n',definition)
    assert any(item['row']==3 and 'row 2' in item['reason'] for item in caught.value.errors)


def test_numeric_identity_uses_numeric_equality_not_json_spelling():
    definition=adapter('json');definition['tables'][0]['fields'][0]['type']='number'
    definition['tables'][0]['unique_by']=['/id']
    with pytest.raises(MappingError):
        apply_profile('numeric.json',b'{"rows":[{"Object":1,"Force":10,"Unit":"kN"},{"Object":1.0,"Force":20,"Unit":"kN"}]}',definition)


@pytest.mark.parametrize('paths',[[],['/not-mapped'],['/id','/id']])
def test_uniqueness_configuration_must_be_explicit_and_mapped(paths):
    definition=adapter();definition['tables'][0]['unique_by']=paths
    with pytest.raises(ValueError):validate_profile(definition)


def test_profiles_do_not_share_mutable_base_units_aliases_or_source_selection():
    first=adapter();second=adapter();second['id']='SYNTHETIC-N';second['tables'][0]['fields'][1]['unit']['target']='N'
    raw=b'Object,Force,Unit\nA,1000,N\n'
    before=copy.deepcopy((first,second))
    assert apply_profile('f.csv',raw,first)['input']['objects'][0]['value']==1
    assert apply_profile('f.csv',raw,second)['input']['objects'][0]['value']==1000
    assert (first,second)==before
    wrong=copy.deepcopy(second);wrong['tables'][0]['fields'][1]['aliases']=['Pressure']
    with pytest.raises(MappingError):apply_profile('f.csv',raw,wrong)
    assert apply_profile('f.csv',raw,first)['input']['objects'][0]['value']==1


def test_xlsx_multisheet_aliases_and_cells_are_exact():
    raw=xlsx([['Object','Unit','Vertical'],[None,None,None],['A','N',1000]], [['Object','Unit','Vertical'],['B','N',999999]])
    result=apply_profile('book.xlsx',raw,adapter('xlsx'))
    assert result['input']['objects'][0]['id']=='A'
    assert next(p for p in result['provenance'] if p['target']=='/objects/0/value')['location']['cell']=='C3'


def test_xlsx_headers_are_not_silently_trimmed():
    raw=xlsx([[' Object ','Force','Unit'],['A',100,'kN']])
    with pytest.raises(MappingError):apply_profile('book.xlsx',raw,adapter('xlsx'))
    definition=adapter('xlsx');definition['tables'][0]['fields'][0]['aliases']=[' Object ']
    result=apply_profile('book.xlsx',raw,definition)
    assert result['provenance'][0]['location']['column']==' Object '


@pytest.mark.parametrize('literal',['1e-999','-1e-999','1e999'])
def test_xlsx_xml_numeric_loss_is_rejected_before_openpyxl(literal):
    raw=xlsx([['Object','Force','Unit'],['A',12345,'kN']]);output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(output,'w') as target:
        for entry in source.infolist():
            content=source.read(entry)
            if entry.filename=='xl/worksheets/sheet1.xml':content=content.replace(b'<v>12345</v>',('<v>'+literal+'</v>').encode())
            target.writestr(entry,content)
    with pytest.raises(DataValidationError,match='B2'):ingest('loss.xlsx',output.getvalue())


def test_deep_json_is_a_mapping_failure_not_server_error():
    raw=b'{"rows":'+b'['*80+b'0'+b']'*80+b'}'
    with pytest.raises(MappingError):apply_profile('deep.json',raw,adapter('json'))


def rule(identifier, check='MASS-SOURCE', **overrides):
    value={'id':identifier,'project_id':'SYNTHETIC-PROJECT','version':'1','title':'SYNTHETIC check rule',
           'text':'Synthetic declared requirement only; not a client standard.','locator':'synthetic.txt#line=1',
           'task_ids':['mass-source'],'check_ids':[check],'status':'approved','authority':'synthetic',
           'source_sha256':'a'*64,'approved_by':'synthetic-author','approved_at':'2026-10-07T09:00:00+11:00',
           'parameters':{'settings':[{'path':'/mass/include_self_weight','operator':'eq','value':True}]}}
    return {**value,**overrides}


def test_different_rule_ids_cannot_silently_discard_conflicting_requirements():
    conflicting=rule('SYNTHETIC-TWO',parameters={'settings':[{'path':'/mass/include_self_weight','operator':'eq','value':False}]})
    retrieval=retrieve('MASS-SOURCE','mass-source',[rule('SYNTHETIC-ONE'),conflicting],'SYNTHETIC-PROJECT',limit=50)
    gate=check_coverage(retrieval,['MASS-SOURCE'])
    assert gate['status']=='NOT VERIFIED' and 'aggregation is not registered' in gate['reason']


def test_multiple_independent_required_checks_still_have_coverage():
    retrieval=retrieve('CHECK-A CHECK-B','mass-source',[rule('SYNTHETIC-A','CHECK-A'),rule('SYNTHETIC-B','CHECK-B')],'SYNTHETIC-PROJECT',limit=50)
    assert check_coverage(retrieval,['CHECK-A','CHECK-B'])['status']=='FOUND'


def test_conditions_require_known_typed_values():
    sample=rule('SYNTHETIC-CONDITION',conditions=[{'path':'/scope/material','operator':'eq','value':'concrete'}])
    assert applicable(executable_rule(sample),{'scope':{'material':'concrete'}})
    assert not applicable(sample,{'scope':{'material':'steel'}})
    assert matches(sample['conditions'][0],{}) is None
    assert not applicable(sample,{})
    assert matches({'path':'/v','operator':'eq','value':1},{'v':True}) is False


def test_handoff_tolerance_is_independently_derived_with_decimal():
    source={'project':{'revision':'A'},'force':-12.5,'unit':'kN'}
    target={'project':{'revision':'B'},'force':-12500,'unit':'N'}
    manifest={'id':'SYNTHETIC-TRANSFER','version':'1','approved':True,'source_revision':'A','target_revision':'B',
              'required_source_paths':['/force'],'required_target_paths':['/force'],
              'mappings':[{'id':'force','source_path':'/force','target_path':'/force','source_unit_path':'/unit','target_unit_path':'/unit',
                           'comparison_unit':'kN','absolute_tolerance':0.125,'relative_tolerance':0.01}]}
    independently_computed=Decimal('-12500')*Decimal('0.001')
    tolerance=max(Decimal('0.125'),abs(Decimal('-12.5'))*Decimal('0.01'))
    for actual,expected in [(-12375,'PASS'),(-12625,'PASS'),(-12374.99,'FAIL'),(-12625.01,'FAIL')]:
        target['force']=actual;outcome=verify_handoff(source,target,manifest)
        assert outcome['status']==expected
        detail=outcome['details'][0]
        assert Decimal(str(detail['expected']))==independently_computed
        assert Decimal(str(detail['tolerance']))==tolerance


@pytest.mark.parametrize('actual,status',[(0,'PASS'),(1,'PASS'),(True,'NOT VERIFIED'),(None,'NOT VERIFIED'),(-0.01,'FAIL'),(1.01,'FAIL')])
def test_settings_inclusive_bounds_no_defaults_and_no_boolean_coercion(actual,status):
    result=verify_settings({'configuration_complete':True,'value':actual},{'id':'SYNTHETIC-RANGE','version':'1','approved':True,'settings':[{'path':'/value','operator':'range','min':0,'max':1}]})
    assert result['status']==status


def test_nonzero_area_times_pressure_never_silently_becomes_zero():
    data=json.loads((Path(__file__).resolve().parents[2]/'dist/examples/clean.json').read_text())
    data['floors'][0]['area']=1e-300
    data['requirements'][0]['q']=1e-300
    with pytest.raises(DataValidationError,match='underflow'):
        ingest('synthetic-underflow.json',json.dumps(data).encode())


def test_xlsx_duplicate_archive_parts_are_ambiguous_and_rejected():
    raw=xlsx([['Object','Force','Unit'],['A',12345,'kN']]);output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(output,'w') as target:
        for entry in source.infolist():target.writestr(entry,source.read(entry))
        with pytest.warns(UserWarning,match='Duplicate name'):
            target.writestr('xl/worksheets/sheet1.xml',source.read('xl/worksheets/sheet1.xml'))
    with pytest.raises(DataValidationError,match='archive entry'):
        ingest('ambiguous.xlsx',output.getvalue())


def test_conflicting_parameter_rules_block_actual_workflow(tmp_path):
    from fastapi.testclient import TestClient
    from strata.app import create_app
    app=create_app(tmp_path,testing=True,worker=False)
    with TestClient(app) as client:
        auth=client.post('/api/v1/auth/bootstrap',json={'username':'synthetic-reviewer','password':'synthetic-only-password'}).json()
        client.headers['Authorization']='Bearer '+auth['token']
        project=client.post('/api/v1/projects',json={'name':'SYNTHETIC multiple rule gate'}).json()['project']
        base='/api/v1/projects/'+project['id'];seed=client.post(base+'/seed').json()
        original=next(r['rule'] for r in client.get(base+'/dashboard').json()['rules'] if r['rule']['id']=='MASS-SOURCE')
        conflict={**original,'id':'SYNTHETIC-SECOND-MASS','parameters':{'settings':[{'path':'/mass/include_self_weight','operator':'eq','value':False}]}}
        response=client.post(base+'/rules',json={'rule':conflict});assert response.status_code==200,response.text
        assert client.post(base+'/rules/'+response.json()['rule']['id']+'/approve',json={}).status_code==200
        queued=client.post(base+'/runs',json={'task_id':'mass-source','snapshot_id':seed['snapshots'][16]['id']}).json()['run']
        app.state.runner.process(queued['id']);run=client.get(base+'/runs/'+queued['id']).json()['run']
        assert run['status']=='NOT VERIFIED' and 'aggregation' in run['explanation']
