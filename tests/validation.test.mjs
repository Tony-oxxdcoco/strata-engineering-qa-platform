import test from 'node:test';
import assert from 'node:assert/strict';
import {runValidation} from '../dist/validation.js';
import {runChecks} from '../dist/engine.js';

test('visible golden suite matches independent expected statuses and reference numbers', () => {
  const report = runValidation();
  assert.equal(report.summary.total,16);
  assert.deepEqual(report.cases.filter(c => !c.matched).map(c => ({id:c.id, actual:c.actual, error:c.error, numbers:c.numericChecks})), []);
  assert.equal(report.summary.falsePass,0);
  assert.equal(report.summary.expectedNotVerified,report.summary.actualNotVerified);
});
test('returning NOT VERIFIED for everything does not pass the validation suite', () => {
  const report = runValidation({gravityRunner:input => {
    const result = runChecks(input);
    result.results.forEach(r => r.status = 'NOT VERIFIED');
    return result;
  }});
  assert.ok(report.summary.mismatched >= 10);
  assert.equal(report.summary.falsePass,0);
  assert.ok(report.summary.actualNotVerified > report.summary.expectedNotVerified);
});
test('false PASS count uses expected non-PASS outcomes, not an overall pass rate', () => {
  const report = runValidation({gravityRunner:input => {
    const result = runChecks(input);
    result.results.forEach(r => r.status = 'PASS');
    return result;
  }});
  assert.ok(report.summary.falsePass > 0);
  assert.ok(report.summary.mismatched > 0);
});
test('duplicate IDs, malformed output and altered actual values cannot pass or crash validation', () => {
  for (const corrupt of [
    result => result.results.push(structuredClone(result.results[0])),
    result => {result.results[3].details=undefined;},
    result => result.results.forEach(r => r.details.forEach(d => {if('actual' in d)d.actual=999999;}))
  ]) {
    const report=runValidation({gravityRunner:input=>{const result=runChecks(input);corrupt(result);return result;}});
    assert.ok(report.summary.mismatched>0);
    assert.equal(report.cases.find(c=>c.id==='G01').matched,false);
  }
});
