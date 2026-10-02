import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {COMBINATION_VERSION, COMBINATION_SCENARIOS, getCombinationSample, validateCombinationInput, runCombinationChecks, createCombinationRun, combinationReport} from '../dist/combinations.js';

const clean = () => getCombinationSample();
const first = input => runCombinationChecks(input).results[0];
const single = (values, factors, reportedValue) => {
  const input = clean();
  input.baseCases = values.map((value, i) => ({id: `B${i}`, value, evidenceRef: 'reference-responses'}));
  input.combinations = [{id: 'EDGE', terms: factors.map((factor, i) => ({caseId: `B${i}`, factor})), reportedValue, evidenceRef: 'reported-combinations'}];
  return input;
};

test('hand-derived fixture: 120 + 75 = 195 and 100 - 50 = 50 kN', () => {
  const result = runCombinationChecks(clean());
  assert.equal(result.version, COMBINATION_VERSION);
  assert.deepEqual(result.summary, {PASS: 2, FAIL: 0, 'NOT VERIFIED': 0});
  assert.deepEqual(result.results.map(row => [row.id, row.details[0].expected, row.details[0].actual, row.details[0].tolerance]), [['C1', 195, 195, 1.95], ['C2', 50, 50, 1]]);
  assert.equal(result.status, 'PASS');
});
test('four stable scenarios have independently specified outcomes', () => {
  assert.deepEqual(COMBINATION_SCENARIOS.map(row => row.id), ['clean', 'mismatch', 'missing', 'unsupported']);
  const expected = {clean: ['PASS', 'PASS'], mismatch: ['FAIL', 'PASS'], missing: ['NOT VERIFIED', 'NOT VERIFIED'], unsupported: ['NOT VERIFIED', 'NOT VERIFIED']};
  for (const [id, statuses] of Object.entries(expected)) assert.deepEqual(runCombinationChecks(getCombinationSample(id)).results.map(row => row.status), statuses, id);
  assert.throws(() => getCombinationSample('unknown'), /Unknown/);
});
test('fixture files match public sample inputs', async () => {
  for (const {id} of COMBINATION_SCENARIOS) {
    const file = await readFile(new URL(`../dist/examples/combination-${id}.json`, import.meta.url), 'utf8');
    assert.deepEqual(JSON.parse(file), getCombinationSample(id));
  }
});
test('reported responses remain independent when reference input changes', () => {
  const input = clean();
  input.baseCases[0].value = 200;
  const results = runCombinationChecks(input).results;
  assert.deepEqual(results.map(row => row.details[0].expected), [315, 150]);
  assert.deepEqual(results.map(row => row.details[0].actual), [195, 50]);
  assert.deepEqual(results.map(row => row.status), ['FAIL', 'FAIL']);
});
test('changing a reported response does not regenerate reference values', () => {
  const input = clean();
  input.combinations[0].reportedValue = 210;
  assert.deepEqual(input.baseCases.map(row => row.value), [100, 50]);
  assert.equal(first(input).details[0].expected, 195);
  assert.equal(first(input).status, 'FAIL');
});
test('signed values and signed factors are permitted for a linear response', () => {
  // -80 × 1.5 + 20 × -2 = -120 - 40 = -160.
  const row = first(single([-80, 20], [1.5, -2], -160));
  assert.equal(row.details[0].expected, -160);
  assert.equal(row.status, 'PASS');
});
test('exact cancellation gives zero with the absolute 1 kN tolerance', () => {
  const row = first(single([100, 100], [1, -1], 0));
  assert.equal(row.details[0].expected, 0);
  assert.equal(row.details[0].tolerance, 1);
  assert.equal(row.status, 'PASS');
});
test('compensated summation retains a small response amid cancellation', () => {
  // Exact arithmetic: 10^16 + 3 - 10^16 = 3, not 4 or 0.
  const row = first(single([1e16, 3, -1e16], [1, 1, 1], 3));
  assert.equal(row.details[0].expected, 3);
  assert.equal(row.status, 'PASS');
});
test('fixed tolerance includes both endpoints and excludes a just-outside value', () => {
  for (const [expected, accepted, rejected] of [[200, [198, 202], [197.9999, 202.0001]], [0, [-1, 1], [-1.0001, 1.0001]], [-200, [-202, -198], [-202.0001, -197.9999]]]) {
    for (const actual of accepted) assert.equal(first(single([expected], [1], actual)).status, 'PASS');
    for (const actual of rejected) assert.equal(first(single([expected], [1], actual)).status, 'FAIL');
  }
  const input = clean();
  input.combinations[0].reportedValue = 196.95;
  assert.equal(first(input).status, 'PASS');
});
test('zero values and zero factors can be verified with complete evidence', () => {
  assert.equal(first(single([100, 0], [0, 1], 0)).status, 'PASS');
  assert.equal(first(single([-0], [1], 0)).status, 'PASS');
});
test('missing base case is NOT VERIFIED even with a zero factor', () => {
  const input = clean();
  input.combinations[0].terms[0] = {caseId: 'UNKNOWN', factor: 0};
  assert.equal(first(input).status, 'NOT VERIFIED');
  assert.equal(first(input).details[0].expected, null);
});
test('empty base cases or empty terms cannot create a vacuous PASS', () => {
  for (const mutate of [input => {input.baseCases = [];}, input => {input.combinations[0].terms = [];}]) {
    const input = clean(); mutate(input);
    assert.equal(first(input).status, 'NOT VERIFIED');
  }
});
test('no combinations produces one explicit NOT VERIFIED input result', () => {
  const input = clean(); input.combinations = [];
  const result = runCombinationChecks(input);
  assert.equal(result.status, 'NOT VERIFIED');
  assert.deepEqual(result.summary, {PASS: 0, FAIL: 0, 'NOT VERIFIED': 1});
  assert.equal(result.results[0].id, 'COMB-INPUT');
});
test('missing, dangling and blank source evidence blocks affected combinations', () => {
  for (const mutate of [
    input => {input.evidence = [];},
    input => {input.baseCases[0].evidenceRef = 'missing';},
    input => {delete input.baseCases[0].evidenceRef;},
    input => {input.combinations[0].evidenceRef = null;},
    input => {input.evidence[0].content = ' ';},
    input => {delete input.evidence[0].locator;},
    input => {input.evidence[1].title = '';},
  ]) {
    const input = clean(); mutate(input);
    assert.equal(first(input).status, 'NOT VERIFIED');
  }
});
test('reference and reported response cannot cite the identical evidence record', () => {
  const input = clean();
  input.combinations[0].evidenceRef = input.baseCases[0].evidenceRef;
  assert.equal(first(input).status, 'NOT VERIFIED');
  assert.match(first(input).summary, /same evidence record/);
});
test('unknown units, unsupported analyses and non-synthetic scope are NOT VERIFIED', () => {
  for (const [field, value] of [['unit', 'N'], ['unit', 'kg'], ['analysisType', 'envelope'], ['analysisType', 'nonlinear'], ['synthetic', false]]) {
    const input = clean(); input[field] = value;
    assert.deepEqual(runCombinationChecks(input).results.map(row => row.status), ['NOT VERIFIED', 'NOT VERIFIED']);
  }
});
test('unsupported-unit responses retain their declared unit in details and report', async () => {
  const input = clean(); input.unit = 'N'; input.combinations[0].reportedValue = 195000;
  const detail = first(input).details[0];
  assert.equal(detail.actual, 195000);
  assert.equal(detail.unit, 'N');
  assert.equal(detail.expected, null);
  assert.equal(detail.tolerance, null);
  const report = await combinationReport(await createCombinationRun(input));
  assert.ok(report.includes('| — | 195000 | N | — |'));
});
test('nested combination references are never treated as base response values', () => {
  const input = clean(); input.combinations[1].terms = [{caseId: 'C1', factor: 1}];
  assert.equal(runCombinationChecks(input).results[1].status, 'NOT VERIFIED');
});
test('duplicate records and repeated terms are rejected without de-duplication', () => {
  for (const field of ['baseCases', 'combinations', 'evidence']) {
    const input = clean(); input[field].push({...input[field][0]});
    assert.throws(() => runCombinationChecks(input), /duplicate/);
  }
  const input = clean(); input.combinations[0].terms.push({...input.combinations[0].terms[0]});
  assert.throws(() => runCombinationChecks(input), /duplicate/);
});
test('ambiguous base and combination ID namespaces are rejected', () => {
  const input = clean(); input.baseCases[0].id = 'C1';
  assert.throws(() => runCombinationChecks(input), /distinct/);
});
test('non-numeric, non-finite and missing values are rejected before checking', () => {
  for (const bad of [null, '100', Infinity, -Infinity, NaN, true]) {
    for (const mutate of [input => {input.baseCases[0].value = bad;}, input => {input.combinations[0].reportedValue = bad;}, input => {input.combinations[0].terms[0].factor = bad;}]) {
      const input = clean(); mutate(input);
      assert.throws(() => runCombinationChecks(input));
    }
  }
  const input = clean(); delete input.combinations[0].reportedValue;
  assert.throws(() => runCombinationChecks(input), /reportedValue/);
});
test('malformed schema and containers are rejected', () => {
  for (const input of [null, [], {}, {...clean(), schemaVersion: '1.0'}, {...clean(), project: {name: 'no revision'}}, {...clean(), evidence: {}}, {...clean(), synthetic: 'true'}]) assert.throws(() => validateCombinationInput(input));
});
test('JSON snapshots cannot coerce NaN, cycles or sparse arrays into valid data', async () => {
  const extra = clean(); extra.extra = NaN;
  await assert.rejects(createCombinationRun(extra), /finite JSON/);
  const cyclic = clean(); cyclic.extra = cyclic;
  assert.throws(() => runCombinationChecks(cyclic), /cyclic/);
  const sparse = clean(); sparse.baseCases = Array(2);
  assert.throws(() => runCombinationChecks(sparse), /sparse/);
});
test('multiplication, accumulation and comparison overflow are NOT VERIFIED', () => {
  for (const input of [single([1e308], [10], 0), single([1e308, 1e308, -1e308], [1, 1, 1], 1e308), single([1e308], [1], -1e308)]) {
    assert.equal(first(input).status, 'NOT VERIFIED');
    assert.match(first(input).summary, /overflow/);
  }
});
test('underflow cannot silently turn a nonzero product into zero', () => {
  const row = first(single([1e-300], [1e-300], 0));
  assert.equal(row.status, 'NOT VERIFIED');
  assert.match(row.summary, /underflow/);
});
test('FAIL remains visible when another combination lacks verification evidence', () => {
  const input = getCombinationSample('mismatch');
  input.combinations[1].evidenceRef = 'missing';
  const result = runCombinationChecks(input);
  assert.equal(result.status, 'FAIL');
  assert.deepEqual(result.summary, {PASS: 0, FAIL: 1, 'NOT VERIFIED': 1});
});
test('details retain every required field, formula, locations and evidence references', () => {
  const detail = first(clean()).details[0];
  for (const key of ['label', 'expected', 'actual', 'unit', 'formula', 'tolerance', 'reason', 'location', 'evidenceRefs']) assert.ok(Object.hasOwn(detail, key), key);
  assert.match(detail.formula, /1\.2 × 100 \(SDL\)/);
  assert.match(detail.formula, /1\.5 × 50 \(LIVE\)/);
  assert.match(detail.location, /combinations\[0\]\.reportedValue/);
  assert.deepEqual(new Set(detail.evidenceRefs), new Set(['reference-responses', 'reported-combinations']));
});
test('sample copies and checks do not mutate one another or the caller input', () => {
  const input = clean(), before = structuredClone(input);
  validateCombinationInput(input); runCombinationChecks(input);
  assert.deepEqual(input, before);
  input.baseCases[0].value = 200;
  assert.equal(clean().baseCases[0].value, 100);
});
test('runs snapshot the input and use repeatable SHA-256 without sharing results', async () => {
  const input = clean();
  const run = await createCombinationRun(input), second = await createCombinationRun(input);
  assert.match(run.inputHash, /^[a-f0-9]{64}$/);
  assert.equal(run.inputHash, second.inputHash);
  assert.notEqual(run.id, second.id);
  input.baseCases[0].value = 200;
  assert.equal(run.input.baseCases[0].value, 100);
  assert.deepEqual(run.reviews, []);
  assert.equal(run.version, COMBINATION_VERSION);
});
test('verified report includes sources, formulas, synthetic boundaries and review note', async () => {
  const run = await createCombinationRun(getCombinationSample('mismatch'));
  run.reviews.push({at: new Date().toISOString(), reviewer: 'Demo reviewer', note: 'Investigate C1; note does not resolve failure.', disposition: 'request_evidence'});
  const report = await combinationReport(run);
  for (const part of [run.inputHash, 'Synthetic', 'NOT ENGINEERING APPROVAL', 'AS 1170', '195', '210', '1.2 × 100', 'reference-responses', 'Fixture reference sheet', 'Demo reviewer', 'Investigate C1', 'Input snapshot', 'Overall: FAIL']) assert.ok(report.includes(part), part);
  assert.equal(run.status, 'FAIL');
});
test('unreviewed report remains labelled DRAFT', async () => {
  const run = await createCombinationRun(clean());
  assert.match(await combinationReport(run), /DRAFT — NOT REVIEWED/);
});
test('reports reject altered technical results, summaries and stale versions', async () => {
  for (const mutate of [run => {run.status = 'FAIL';}, run => {run.summary.PASS = 999;}, run => {run.results[0].details[0].expected = 999;}, run => {run.results[0].details[0].formula = 'invented';}, run => {run.version = 'old';}]) {
    const run = await createCombinationRun(clean()); mutate(run);
    await assert.rejects(combinationReport(run), /replay|stale/);
  }
});
test('reports reject changed input metadata even when numeric results still match', async () => {
  const run = await createCombinationRun(clean()); run.input.project.revision = 'COMB-R02';
  await assert.rejects(combinationReport(run), /SHA-256/);
  const other = await createCombinationRun(clean()); other.inputHash = '0'.repeat(64);
  await assert.rejects(combinationReport(other), /SHA-256/);
});
test('invalid review or run metadata cannot be exported as reviewed evidence', async () => {
  for (const review of [{at: 'invalid', reviewer: 'A', note: 'B', disposition: 'reviewed'}, {at: new Date().toISOString(), reviewer: '', note: 'B', disposition: 'reviewed'}, {at: new Date().toISOString(), reviewer: 'A', note: 'B', disposition: 'approved'}]) {
    const run = await createCombinationRun(clean()); run.reviews.push(review);
    await assert.rejects(combinationReport(run), /review/);
  }
  const run = await createCombinationRun(clean()); run.createdAt = 'invalid';
  await assert.rejects(combinationReport(run), /timestamp/);
});
test('report verification is insulated from mutations during its asynchronous hash check', async () => {
  const run = await createCombinationRun(clean());
  const pending = combinationReport(run);
  run.input.project.name = 'CHANGED AFTER SNAPSHOT';
  run.results[0].status = 'FAIL';
  run.reviews.push({at: new Date().toISOString(), reviewer: 'LATE REVIEW', note: 'After verification began', disposition: 'reviewed'});
  const report = await pending;
  assert.ok(!report.includes('CHANGED AFTER SNAPSHOT'));
  assert.ok(!report.includes('LATE REVIEW'));
  assert.match(report, /Overall: PASS/);
});
test('source text cannot prematurely close the report input snapshot code fence', async () => {
  const input = clean(); input.evidence[0].content += '\n```\n<script>not executed</script>';
  const report = await combinationReport(await createCombinationRun(input));
  assert.ok(report.includes('````json'));
  assert.ok(report.includes('&lt;script&gt;'));
  assert.ok(report.endsWith('````\n'));
});
