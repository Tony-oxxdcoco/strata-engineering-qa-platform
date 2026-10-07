#!/usr/bin/env python3
"""Replay fixed synthetic dev/holdout queries; never tune on the holdout."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from strata.contracts import applicable
from strata.knowledge import RETRIEVAL_VERSION, check_coverage, retrieve


def evaluate(dataset):
    if dataset.get('material_type')!='synthetic':raise ValueError('This research fixture must be explicitly synthetic')
    rows=[]
    for case in dataset['queries']:
        corpus=copy.deepcopy(dataset['corpus'])
        for change in case.get('mutations',[]):
            for rule in corpus:
                if rule['id']==change['id']:rule.update(change)
        corpus.extend(copy.deepcopy(case.get('add_rules',[])))
        # Match the existing execution gate: missing conditions cannot authorise
        # a calculation. This does not infer applicability from lexical scores.
        corpus=[rule for rule in corpus if applicable(rule,case.get('context',{}))]
        for method in ('bm25','candidate-synonyms'):
            query=case['query']
            expansions=[]
            if method=='candidate-synonyms':
                expansions=[target for word,target in dataset['candidate']['synonyms'].items() if re.search(r'\b'+re.escape(word)+r'\b',query.lower())]
                query+=' '+' '.join(expansions)
            started=time.perf_counter()
            result=retrieve(query,case['task_id'],corpus,case['project_id'],limit=50)
            elapsed=(time.perf_counter()-started)*1000
            gate=check_coverage(result,case['required_check_ids']) if case.get('required_check_ids') else None
            actual_ids=[rule['id'] for rule in result['rules']]
            matched=(result['status']=='NOT VERIFIED' if case['expected_top'] is None else bool(actual_ids) and actual_ids[0]==case['expected_top'])
            if case.get('expected_rule_ids'):matched=matched and sorted(actual_ids)==sorted(case['expected_rule_ids'])
            if case.get('expected_version'):matched=matched and bool(result['rules']) and result['rules'][0]['version']==case['expected_version']
            if gate:matched=matched and gate['status']=='FOUND'
            rows.append({'case_id':case['case_id'],'split':case['split'],'method':method,'query':case['query'],'expanded_terms':expansions,
                         'expected_top':case['expected_top'],'actual_rule_ids':actual_ids,'status':result['status'],'coverage':gate,
                         'matched':matched,'unsupported_match':case['expected_top'] is None and result['status']=='FOUND','elapsed_ms':round(elapsed,3)})
    summaries=[]
    for split in ('development','holdout'):
        for method in ('bm25','candidate-synonyms'):
            items=[r for r in rows if r['split']==split and r['method']==method]
            positives=[r for r in items if r['expected_top'] is not None]
            negatives=[r for r in items if r['expected_top'] is None]
            summaries.append({'split':split,'method':method,'cases':len(items),'matched':sum(r['matched'] for r in items),
                              'positive_top1_hits':sum(r['matched'] for r in positives),'positive_cases':len(positives),
                              'negative_correct_rejections':sum(r['matched'] for r in negatives),'negative_cases':len(negatives),
                              'unsupported_matches':sum(r['unsupported_match'] for r in items),'median_ms':sorted(r['elapsed_ms'] for r in items)[len(items)//2]})
    return {'material_type':'synthetic','baseline_version':RETRIEVAL_VERSION,'candidate':dataset['candidate'],'experimental_protocol':dataset.get('experimental_protocol',{}),'summaries':summaries,'rows':rows,
            'limitations':['Hand-authored synthetic retrieval fixture; not engineering QA accuracy.','Development and holdout labels are fixed before this single experiment; this small holdout has now been observed and must not be reused for tuning claims.',
                           'Candidate synonyms are unapproved global vocabulary. Extra lexical hits do not prove applicability.','No semantic model, embedding service, or paid API used. Production retrieval remains BM25; execution additionally uses exact registered check IDs and coverage gates.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'examples/retrieval-evaluation.synthetic.json')
    parser.add_argument('--output',type=Path,default=ROOT/'output/retrieval-evaluation-v12.json')
    args=parser.parse_args();report=evaluate(json.loads(args.dataset.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'output':str(args.output),'material_type':'synthetic','summaries':report['summaries']},indent=2))

if __name__=='__main__':main()
