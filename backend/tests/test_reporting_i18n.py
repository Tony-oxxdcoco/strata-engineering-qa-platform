"""Report presentation changes must preserve source records and remain HTML safe."""
import copy
import json
from pathlib import Path

import pytest

from strata.reporting import render_report


def records():
    project = {'name': 'Client PASS project <img src=x onerror=alert(1)>'}
    run = {
        'id':'run-1', 'status':'NOT VERIFIED', 'review_state':'STALE', 'stale':True,
        'stale_reasons':['Original rule/version reason'], 'workflow_version':'v-test', 'rule_hash':'abc',
        'explanation':'ORIGINAL explanation PASS / FAIL / NOT VERIFIED',
        'results':[{'id':'CHECK-1','status':'NOT VERIFIED','summary':'Original technical summary.',
                    'details':[{'id':'field-1','status':'NOT VERIFIED','actual':-1.25,'unit':'kN',
                                'reason':'Original reason.', 'formula':'1.2 × F',
                                'Client_Original_FIELD':'UNMODIFIED <script>run()</script>'}]}],
        'citations':[{'rule_id':'CLIENT-1','version':'r-1','title':'Client original standard',
                      'locator':'Original p. 3','quote':'PASS -1.25 kN <script>bad()</script>',
                      'authority':'client','source_sha256':'source-hash','approved_by':'Reviewer original'}],
        'reviews':[{'action':'request_evidence','username':'Original Reviewer','note':'<img src=x> Original note PASS',
                    'created_at':'2026-10-07T00:00:00Z'}],
        'material_requests':[{'what':'/Client_Original_FIELD','why':'ORIGINAL missing evidence reason',
                              'where':{'field':'/Client_Original_FIELD','view':'Versions'},'finding':'CHECK-1'}],
    }
    provenance = [{'side':'source','title':'Original title','filename':'原文件.json',
                   'snapshot_id':'snapshot-1','source_sha256':'file-hash','input_hash':'input-hash',
                   'synthetic':True,'mapping_provenance':[{'original_value':'PASS','value':-1.25,'unit':'kN'}],
                   'corrections':[{'path':'/Client_Original_FIELD','original':'PASS','value':'FAIL','reason':'Original correction note'}]}]
    findings = [{'finding_id':'CHECK-1','state':'OPEN','technical_status':'NOT VERIFIED','source_run_id':'run-1',
                 'notes':[{'at':'2026-10-07T00:00:00Z','username':'Original Reviewer','action':'request_evidence','note':'Original issue note'}]}]
    return project,run,provenance,findings


def test_chinese_report_translates_presentation_preserves_records_and_escapes_injection():
    args=records();before=copy.deepcopy(args)
    result=render_report(*args,'2026-10-07T01:00:00Z',language='zh-CN')
    assert '<html lang="zh-CN">' in result
    for label in ('技术状态: 未验证','来源引用','输入来源与映射','已过期','合成软件测试样例','原始技术说明'):
        assert label in result
    for original in ('Client PASS project','Original technical summary.','Client_Original_FIELD','1.2 × F','-1.25','kN','request_evidence','Original correction note','Original p. 3'):
        assert original in result
    assert '<script>' not in result and '<img src=x' not in result
    assert '&lt;script&gt;' in result and '&lt;img src=x' in result
    assert args==before
    assert args[1]['status']=='NOT VERIFIED' and args[1]['results'][0]['details'][0]['unit']=='kN'


def test_english_is_default_invalid_languages_rejected_and_empty_sections_are_translated():
    args=records();args[1].update(results=[],citations=[],reviews=[],material_requests=[],stale=False)
    english=render_report(*args,'2026-10-07T01:00:00Z')
    assert '<html lang="en">' in english and 'Technical status: NOT VERIFIED' in english
    assert 'Source citations' in english and 'Current at export' in english
    chinese=render_report(*args,'2026-10-07T01:00:00Z',language='zh-CN')
    assert '没有待补资料请求。' in chinese and '没有可用的批准来源引用。' in chinese
    assert '尚未经复核者确认。' in chinese
    with pytest.raises(ValueError,match='Report language'):
        render_report(*args,'2026-10-07T01:00:00Z',language='../../private')


def test_report_catalogues_have_identical_nonempty_keys():
    root=Path(__file__).parents[1]/'strata'/'locales'
    en=json.loads((root/'en.json').read_text());zh=json.loads((root/'zh-CN.json').read_text())
    assert en.keys()==zh.keys() and all(isinstance(v,str) and v for v in en.values())
    assert all(isinstance(v,str) and v for v in zh.values())


@pytest.mark.parametrize('state,displayed',[('UNREVIEWED','未复核'),('EVIDENCE_REQUESTED','已请求补证据'),('APPROVED','已批准')])
def test_actual_review_states_are_translated_without_changing_protocol_records(state,displayed):
    args=records();args[1]['review_state']=state
    before=copy.deepcopy(args)
    chinese=render_report(*args,'2026-10-07T01:00:00Z',language='zh-CN')
    assert '<dt>复核状态</dt><dd>'+displayed+'</dd>' in chinese
    english=render_report(*args,'2026-10-07T01:00:00Z')
    assert '<dt>Review state</dt><dd>'+state+'</dd>' in english
    assert args==before


@pytest.mark.parametrize('state,stale,label,zh_label', [
    ('UNREVIEWED',False,'DRAFT - NOT REVIEWED','草稿 - 尚未复核'),
    ('EVIDENCE_REQUESTED',False,'DRAFT - NOT REVIEWED','草稿 - 尚未复核'),
    ('APPROVED',False,'REVIEWED SOFTWARE RECORD','已复核的软件检查记录'),
    ('APPROVED',True,'DRAFT - CURRENT REVIEW REQUIRED','草稿 - 需要重新复核当前资料'),
])
def test_report_document_state_requires_a_current_review(state,stale,label,zh_label):
    args=records();args[1].update(review_state=state,stale=stale)
    before=copy.deepcopy(args)
    en=render_report(*args,'2026-10-07T01:00:00Z')
    zh=render_report(*args,'2026-10-07T01:00:00Z',language='zh-CN')
    assert '<strong>'+label+'</strong>' in en
    assert '<strong>'+zh_label+'</strong>' in zh
    assert args==before
