import test from 'node:test';
import assert from 'node:assert/strict';
import {getSample,SCENARIOS} from '../dist/samples.js';
import {
  ENGINE_VERSION,RULE_VERSION,createRun,addReview,runChecks,
  verifyRun,markdownReport,verifiedMarkdownReport
} from '../dist/engine.js';

const cleanRun=()=>createRun(getSample('clean'));

test('all generated scenarios survive storage round-trip and integrity verification',async()=>{
  assert.equal(ENGINE_VERSION,'0.2.0');
  for(const scenario of SCENARIOS){
    const run=await createRun(getSample(scenario.id));
    const restored=JSON.parse(JSON.stringify(run));
    assert.equal(run.ruleVersion,RULE_VERSION);
    assert.deepEqual(await verifyRun(restored),{valid:true,reason:''});
    assert.match(run.audit[0].detail,new RegExp(`^${run.results.length} 个规则已执行`));
  }
});

test('changed numerical input cannot export its stale PASS through either report API',async()=>{
  const run=await cleanRun();
  run.input.assignments[0].force=999999;
  const result=await verifyRun(run);
  assert.equal(result.valid,false);
  assert.match(result.reason,/重算结果不一致/);
  assert.throws(()=>markdownReport(run),/重算结果不一致/);
  await assert.rejects(verifiedMarkdownReport(run),/重算结果不一致/);
});

test('hash verification catches input edits that leave all numerical results unchanged',async()=>{
  const run=await cleanRun();
  run.input.project.revision='Changed after checking';
  assert.deepEqual(runChecks(run.input).results,run.results);
  const result=await verifyRun(run);
  assert.equal(result.valid,false);
  assert.match(result.reason,/SHA-256 不一致/);
  await assert.rejects(verifiedMarkdownReport(run),/SHA-256 不一致/);
});

test('all stored deterministic outputs are verified, including detailed evidence references',async()=>{
  const changes=[
    run=>{run.results[0].status='FAIL';},
    run=>{run.summary.PASS=999;},
    run=>{run.status='FAIL';},
    run=>{run.comparisons[0].actual=999999;},
    run=>{run.results.find(r=>r.id==='QA-005').details[0].evidenceRefs.pop();}
  ];
  for(const change of changes){
    const run=await cleanRun();
    change(run);
    assert.equal((await verifyRun(run)).valid,false);
    assert.throws(()=>markdownReport(run),/重算结果不一致/);
    await assert.rejects(verifiedMarkdownReport(run),/重算结果不一致/);
  }
});

test('unsupported engine and rule versions require a new run',async()=>{
  for(const [field,value] of [['engineVersion','0.1.0'],['ruleVersion','unknown-rule-version']]){
    const run=await cleanRun();
    run[field]=value;
    const result=await verifyRun(run);
    assert.equal(result.valid,false);
    assert.match(result.reason,/版本不匹配/);
    await assert.rejects(verifiedMarkdownReport(run),/版本不匹配/);
  }
});

test('valid human reviews are preserved without changing technical results',async()=>{
  const run=await createRun(getSample('issues'));
  const reviewed=addReview(run,{
    ruleId:'QA-003',reviewer:'Test engineer',note:'Check this floor allocation.',disposition:'request_evidence'
  });
  const saved=JSON.stringify(reviewed);
  assert.deepEqual(await verifyRun(reviewed),{valid:true,reason:''});
  const report=await verifiedMarkdownReport(reviewed);
  assert.match(report,/Test engineer/);
  assert.match(report,/Check this floor allocation/);
  assert.match(report,/request_evidence/);
  assert.equal(JSON.stringify(reviewed),saved);
  assert.deepEqual(reviewed.results,run.results);
  assert.equal(reviewed.inputHash,run.inputHash);
});

test('malformed records return invalid instead of leaking errors into history rendering',async()=>{
  for(const run of [null,{},[],{engineVersion:ENGINE_VERSION}]){
    const result=await verifyRun(run);
    assert.equal(result.valid,false);
    assert.equal(typeof result.reason,'string');
    assert.ok(result.reason.length>0);
  }
  const changes=[
    run=>{run.id=null;},
    run=>{run.createdAt='invalid-date';},
    run=>{run.reviews=null;},
    run=>{run.reviews.push({ruleId:'QA-003'});},
    run=>{run.audit={};},
    run=>{run.audit[0].at='invalid-date';},
    run=>{run.audit[0].detail=null;},
    run=>{run.inputHash='bad-hash';},
    run=>{run.inputHash='0'.repeat(64);},
    run=>{run.input.floors[0].area=Infinity;}
  ];
  for(const change of changes){
    const run=await cleanRun();
    change(run);
    const result=await verifyRun(run);
    assert.equal(result.valid,false);
    assert.ok(result.reason);
    await assert.rejects(verifiedMarkdownReport(run));
  }
});

test('nonfinite stored values cannot masquerade as null during replay comparison',async()=>{
  const run=await createRun(getSample('missing'));
  const detail=run.results.find(r=>r.id==='QA-005').details[0];
  assert.equal(detail.actual,null);
  detail.actual=Infinity;
  assert.equal((await verifyRun(run)).valid,false);
});

test('equivalent result objects may have reordered keys without becoming invalid',async()=>{
  const run=await cleanRun();
  run.summary=Object.fromEntries(Object.entries(run.summary).reverse());
  run.results=run.results.map(result=>Object.fromEntries(Object.entries(result).reverse()));
  assert.deepEqual(await verifyRun(run),{valid:true,reason:''});
});

test('verified export uses one snapshot even when caller changes the run during hashing',async()=>{
  const run=await cleanRun();
  const reportPromise=verifiedMarkdownReport(run);
  run.input.assignments[0].force=999999;
  run.input.project.name='Changed after export started';
  const report=await reportPromise;
  assert.match(report,/Harbour House/);
  assert.doesNotMatch(report,/999999|Changed after export started/);
  assert.equal((await verifyRun(run)).valid,false);
});

test('reaction findings identify the support schedule whether supplied or missing',()=>{
  for(const missing of [false,true]){
    const input=getSample('clean');
    if(missing)input.evidence=input.evidence.filter(e=>e.id!=='support-schedule');
    const result=runChecks(input).results.find(r=>r.id==='QA-005');
    assert.equal(result.status,missing?'NOT VERIFIED':'PASS');
    for(const detail of result.details)assert.ok(detail.evidenceRefs.includes('support-schedule'));
  }
});
