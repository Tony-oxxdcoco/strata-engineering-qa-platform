// Synthetic linear-static response reconciliation; no design-code or capacity checks.
export const COMBINATION_VERSION = 'combination-demo-1.0.0';
export const COMBINATION_SCENARIOS = Object.freeze([
  {id: 'clean', title: '组合一致', note: '独立参考响应：SDL 100、LIVE 50 kN；C1 195、C2 50 kN。'},
  {id: 'mismatch', title: '组合结果不一致', note: '独立输入保持不变，C1 导出值为 210 kN，超过 195 ± 1.95 kN。'},
  {id: 'missing', title: '基础工况缺失', note: 'LIVE 参考响应缺失；两个依赖它的组合均不能核验。'},
  {id: 'unsupported', title: '分析类型不支持', note: '非线性响应不能用本演示的线性叠加公式核验。'},
].map(Object.freeze));

const isObject = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const nonempty = (v, max = 2000) => typeof v === 'string' && v.trim().length > 0 && v.length <= max;
const finite = v => typeof v === 'number' && Number.isFinite(v);
const identifier = v => nonempty(v, 160) && v === v.trim();
const unique = (rows, key, label) => {
  const seen = new Set();
  for (const row of rows) {
    const value = row[key];
    if (seen.has(value)) throw Error(`${label}: duplicate ${key} ${value}.`);
    seen.add(value);
  }
};
function objectAt(value, label) {
  if (!isObject(value)) throw Error(`${label} must be a JSON object.`);
}
function arrayAt(value, label) {
  if (!Array.isArray(value) || value.length > 1000) throw Error(`${label} must be an array with at most 1000 entries.`);
}
function optionalRef(value, label) {
  if (value !== undefined && value !== null && typeof value !== 'string') throw Error(`${label} must be a string when supplied.`);
}
// Prevent JSON snapshot coercion of NaN, Infinity, undefined, sparse arrays and cycles.
function assertJSON(value, path = 'input', ancestors = new Set(), depth = 0) {
  if (depth > 32) throw Error(`${path}: excessive JSON nesting.`);
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (finite(value)) return;
  if (typeof value !== 'object') throw Error(`${path}: expected finite JSON data.`);
  if (ancestors.has(value)) throw Error(`${path}: cyclic input is not supported.`);
  if (!Array.isArray(value) && ![Object.prototype, null].includes(Object.getPrototypeOf(value))) throw Error(`${path}: expected a plain JSON object.`);
  ancestors.add(value);
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      if (!Object.hasOwn(value, i)) throw Error(`${path}: sparse arrays are not supported.`);
      assertJSON(value[i], `${path}[${i}]`, ancestors, depth + 1);
    }
  } else {
    for (const key of Object.keys(value)) assertJSON(value[key], `${path}.${key}`, ancestors, depth + 1);
  }
  ancestors.delete(value);
}

/** Validate shape and unambiguous finite numeric inputs. Missing references are gated at run time. */
export function validateCombinationInput(input) {
  assertJSON(input);
  objectAt(input, 'input');
  if (input.schemaVersion !== 'combination-1.0') throw Error('schemaVersion must be combination-1.0.');
  if (typeof input.synthetic !== 'boolean') throw Error('synthetic must be explicitly true or false.');
  objectAt(input.project, 'project');
  for (const field of ['name', 'revision']) if (!nonempty(input.project[field])) throw Error(`project.${field} is required.`);
  for (const field of ['analysisType', 'unit']) if (!nonempty(input[field])) throw Error(`${field} is required.`);
  for (const field of ['baseCases', 'combinations', 'evidence']) arrayAt(input[field], field);
  for (const [i, base] of input.baseCases.entries()) {
    objectAt(base, `baseCases[${i}]`);
    if (!identifier(base.id) || !finite(base.value)) throw Error(`baseCases[${i}] needs an ID and a finite numeric value.`);
    optionalRef(base.evidenceRef, `baseCases[${i}].evidenceRef`);
  }
  for (const [i, combination] of input.combinations.entries()) {
    objectAt(combination, `combinations[${i}]`);
    if (!identifier(combination.id) || !finite(combination.reportedValue)) throw Error(`combinations[${i}] needs an ID and finite numeric reportedValue.`);
    optionalRef(combination.evidenceRef, `combinations[${i}].evidenceRef`);
    arrayAt(combination.terms, `combinations[${i}].terms`);
    for (const [j, term] of combination.terms.entries()) {
      objectAt(term, `combinations[${i}].terms[${j}]`);
      if (!identifier(term.caseId) || !finite(term.factor)) throw Error(`combinations[${i}].terms[${j}] needs a caseId and finite numeric factor.`);
    }
    unique(combination.terms, 'caseId', `combinations[${i}].terms`);
  }
  for (const [i, evidence] of input.evidence.entries()) {
    objectAt(evidence, `evidence[${i}]`);
    if (!identifier(evidence.id)) throw Error(`evidence[${i}].id is required.`);
    for (const field of ['title', 'locator', 'content']) {
      if (evidence[field] !== undefined && evidence[field] !== null && typeof evidence[field] !== 'string') throw Error(`evidence[${i}].${field} must be text when supplied.`);
    }
  }
  unique(input.baseCases, 'id', 'baseCases');
  unique(input.combinations, 'id', 'combinations');
  unique(input.evidence, 'id', 'evidence');
  const baseIds = new Set(input.baseCases.map(base => base.id));
  if (input.combinations.some(combination => baseIds.has(combination.id))) throw Error('Base-case and combination IDs must be distinct; nested combinations are unsupported.');
  return input;
}

// Neumaier compensated summation retains small signed contributions during cancellation.
// An overflowing intermediate is deliberately NOT VERIFIED, even if later terms cancel it.
function sumResponses(products) {
  let sum = 0, correction = 0;
  for (const product of products) {
    const next = sum + product;
    if (!Number.isFinite(next)) return null;
    const residual = Math.abs(sum) >= Math.abs(product) ? (sum - next) + product : (product - next) + sum;
    correction += residual;
    if (!Number.isFinite(correction)) return null;
    sum = next;
  }
  const result = sum + correction;
  return Number.isFinite(result) ? (result === 0 ? 0 : result) : null;
}
const numberText = value => String(Object.is(value, -0) ? 0 : value);
const toleranceFor = expected => Math.max(1, Math.abs(expected) * 0.01);

export function runCombinationChecks(input) {
  const data = validateCombinationInput(input);
  const bases = new Map(data.baseCases.map((base, i) => [base.id, {...base, location: `baseCases[${i}]`} ]));
  const evidence = new Map(data.evidence.map(record => [record.id, record]));
  const evidenceOK = ref => {
    const record = evidence.get(ref);
    return record && nonempty(record.title) && nonempty(record.locator) && nonempty(record.content, 100000);
  };
  const globalReasons = [];
  if (data.synthetic !== true) globalReasons.push('This demo only accepts explicitly synthetic cases; it does not verify real engineering data.');
  if (data.analysisType !== 'linear-static') globalReasons.push(`Unsupported analysisType ${data.analysisType}; only linear-static superposition is supported.`);
  if (data.unit !== 'kN') globalReasons.push(`Unsupported unit ${data.unit}; all responses must use kN.`);
  const results = data.combinations.map((combination, index) => {
    const reasons = [...globalReasons];
    const products = [];
    const materialNeeds = [];
    const refs = [combination.evidenceRef, ...combination.terms.map(term => bases.get(term.caseId)?.evidenceRef)].filter(ref => typeof ref === 'string' && ref.length > 0);
    if (!combination.terms.length) reasons.push('No base-case terms were supplied; an empty sum is not a verified response.');
    if (!evidenceOK(combination.evidenceRef)) reasons.push('Reported combination response is missing a source record with title, locator and content.');
    for (const term of combination.terms) {
      const base = bases.get(term.caseId);
      if (!base) {
        reasons.push(`Missing independent base case ${term.caseId}; unknown or nested combinations cannot be evaluated.`);
        materialNeeds.push({kind:'input_field', field:'/baseCases', object_id:term.caseId, reason:`Missing independent base case ${term.caseId}; unknown or nested combinations cannot be evaluated.`});
        continue;
      }
      if (!evidenceOK(base.evidenceRef)) reasons.push(`Base case ${base.id} is missing a source record with title, locator and content.`);
      if (base.evidenceRef && base.evidenceRef === combination.evidenceRef) reasons.push(`Base case ${base.id} and its reported combination use the same evidence record; separately supplied reference and reported sources are required.`);
      const reference=evidence.get(base.evidenceRef), reported=evidence.get(combination.evidenceRef);
      if(reference&&reported&&reference.id!==reported.id&&reference.locator===reported.locator&&reference.content===reported.content) reasons.push(`Base case ${base.id} and reported response have identical source content and location; independent evidence is not established.`);
      const product = term.factor * base.value;
      if (!Number.isFinite(product)) reasons.push(`Arithmetic overflow in ${term.caseId}: factor × base response.`);
      else if (product === 0 && term.factor !== 0 && base.value !== 0) reasons.push(`Arithmetic underflow in ${term.caseId}: factor × base response.`);
      else products.push(product);
    }
    let expected = null, tolerance = null;
    if (!reasons.length) {
      expected = sumResponses(products);
      if (expected === null) reasons.push('Arithmetic overflow while summing signed base-case contributions.');
      else {
        tolerance = toleranceFor(expected);
        if (!Number.isFinite(Math.abs(combination.reportedValue - expected))) reasons.push('Arithmetic overflow while comparing reported and expected responses.');
      }
    }
    // Form a closed tolerance interval: exact endpoints are accepted without a broad epsilon.
    const status = reasons.length ? 'NOT VERIFIED' : combination.reportedValue >= expected - tolerance && combination.reportedValue <= expected + tolerance ? 'PASS' : 'FAIL';
    const symbolic = combination.terms.map(term => `${numberText(term.factor)} × ${term.caseId}`).join(' + ') || 'no terms';
    const substituted = combination.terms.map(term => {
      const base = bases.get(term.caseId);
      return `${numberText(term.factor)} × ${base ? numberText(base.value) : '?'} (${term.caseId})`;
    }).join(' + ') || 'no terms';
    const formula = `Σ(factor × independent base response): ${symbolic}; ${substituted}${expected === null ? '' : ` = ${numberText(expected)} kN`}`;
    const reason = reasons.join(' ');
    return {
      id: combination.id,
      name: `Linear-static combination ${combination.id}`,
      status,
      summary: reason || (status === 'PASS' ? 'Separately supplied reported response matches linear superposition within the fixed demo tolerance.' : 'Reported response differs from linear superposition beyond the fixed demo tolerance.'),
      details: [{
        label: combination.id, status, materialNeeds, expected, actual: combination.reportedValue, unit: data.unit, formula,
        tolerance, reason: reason || (status === 'PASS' ? 'Within max(1 kN, 1% × |expected|).' : 'Outside max(1 kN, 1% × |expected|).'),
        location: `combinations[${index}].reportedValue ↔ ${combination.terms.map(term => bases.get(term.caseId)?.location || `missing base case ${term.caseId}`).join(', ')}`,
        evidenceRefs: [...new Set(refs)],
      }],
    };
  });
  if (!results.length) results.push({
    id: 'COMB-INPUT', name: 'Combination input completeness', status: 'NOT VERIFIED', summary: 'No combinations supplied.',
    details: [{label: 'Combination records', expected: null, actual: null, unit: data.unit, formula: 'Σ(factor × independent base response)', tolerance: null, reason: 'At least one combination is required.', location: 'combinations', evidenceRefs: []}],
  });
  const summary = {PASS: 0, FAIL: 0, 'NOT VERIFIED': 0};
  for (const result of results) summary[result.status]++;
  return {version: COMBINATION_VERSION, status: summary.FAIL ? 'FAIL' : summary['NOT VERIFIED'] ? 'NOT VERIFIED' : 'PASS', summary, results};
}

export function getCombinationSample(id = 'clean') {
  if (!COMBINATION_SCENARIOS.some(scenario => scenario.id === id)) throw Error(`Unknown combination scenario: ${id}.`);
  // These independently written reference and export values are not generated by the checker.
  const input = {
    schemaVersion: 'combination-1.0', synthetic: true,
    project: {name: 'Synthetic linear response fixture', revision: 'COMB-R01'},
    analysisType: 'linear-static', unit: 'kN',
    baseCases: [{id: 'SDL', value: 100, evidenceRef: 'reference-responses'}, {id: 'LIVE', value: 50, evidenceRef: 'reference-responses'}],
    combinations: [
      {id: 'C1', terms: [{caseId: 'SDL', factor: 1.2}, {caseId: 'LIVE', factor: 1.5}], reportedValue: 195, evidenceRef: 'reported-combinations'},
      {id: 'C2', terms: [{caseId: 'SDL', factor: 1}, {caseId: 'LIVE', factor: -1}], reportedValue: 50, evidenceRef: 'reported-combinations'},
    ],
    evidence: [
      {id: 'reference-responses', title: 'Independent synthetic base-response sheet', locator: 'Fixture reference sheet, rows SDL and LIVE', content: 'Independent reference responses for one fixed linear response component: SDL = 100 kN; LIVE = 50 kN. These numbers are supplied separately from the combination export.'},
      {id: 'reported-combinations', title: 'Separately supplied synthetic combination export', locator: 'Fixture combination export, rows C1 and C2', content: 'Reported response values: C1 = 195 kN; C2 = 50 kN. Synthetic chosen factors are C1: 1.2 SDL + 1.5 LIVE; C2: 1 SDL - 1 LIVE. These factors do not represent an AS 1170 compliance rule.'},
    ],
  };
  if (id === 'mismatch') {
    input.combinations[0].reportedValue = 210;
    input.evidence[1].content = 'Separately supplied synthetic export: C1 = 210 kN; C2 = 50 kN. C1 is intentionally inconsistent with the independent base responses and chosen factors.';
  }
  if (id === 'missing') {
    input.baseCases = input.baseCases.filter(base => base.id !== 'LIVE');
    input.evidence[0].content = 'Independent synthetic reference response: SDL = 100 kN. The LIVE reference response was not supplied; it must not be inferred.';
  }
  if (id === 'unsupported') input.analysisType = 'nonlinear';
  return input;
}

const jsonCopy = value => JSON.parse(JSON.stringify(value));
async function inputHash(input) {
  const bytes = new TextEncoder().encode(JSON.stringify(input));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
export async function createCombinationRun(input) {
  validateCombinationInput(input);
  const snapshot = jsonCopy(input);
  const result = runCombinationChecks(snapshot);
  return {...result, id: globalThis.crypto.randomUUID(), createdAt: new Date().toISOString(), inputHash: await inputHash(snapshot), input: snapshot, reviews: []};
}
function sameValue(actual, expected) {
  if (Object.is(actual, expected)) return true;
  if (Array.isArray(expected)) return Array.isArray(actual) && actual.length === expected.length && expected.every((item, index) => Object.hasOwn(actual, index) && sameValue(actual[index], item));
  if (!isObject(actual) || !isObject(expected)) return false;
  const keys = Object.keys(expected);
  return Object.keys(actual).length === keys.length && keys.every(key => Object.hasOwn(actual, key) && sameValue(actual[key], expected[key]));
}
const safe = value => String(value ?? '—').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replace(/[\\`*_\[\]{}#|]/g, '\\$&').replace(/[\r\n]+/g, ' ');

export async function combinationReport(run) {
  // Copy once before awaiting, so caller mutation cannot race verification and report rendering.
  assertJSON(run, 'run');
  const snapshot = jsonCopy(run);
  if (!isObject(snapshot) || snapshot.version !== COMBINATION_VERSION) throw Error('Combination run version is stale; run the current checker again.');
  const replay = runCombinationChecks(snapshot.input);
  for (const key of ['version', 'status', 'summary', 'results']) if (!sameValue(snapshot[key], replay[key])) throw Error(`Combination run ${key} differs from replay; rerun the checks.`);
  if (typeof snapshot.inputHash !== 'string' || !/^[a-f0-9]{64}$/.test(snapshot.inputHash) || await inputHash(snapshot.input) !== snapshot.inputHash) throw Error('Combination input SHA-256 mismatch; rerun the checks.');
  const date = value => nonempty(value) && Number.isFinite(Date.parse(value));
  if (!nonempty(snapshot.id) || !date(snapshot.createdAt) || !Array.isArray(snapshot.reviews)) throw Error('Invalid combination run identity, timestamp or reviews.');
  for (const review of snapshot.reviews) {
    if (!isObject(review) || !date(review.at) || !nonempty(review.reviewer) || !nonempty(review.note) || !['reviewed', 'request_evidence'].includes(review.disposition)) throw Error('Invalid combination review record.');
  }
  const lines = [
    '# Synthetic linear-static combination QA report', '',
    snapshot.reviews.length ? '> RECORDED REVIEW — NOT ENGINEERING APPROVAL' : '> DRAFT — NOT REVIEWED',
    '> Synthetic chosen factors and independently supplied response values only. This is not AS 1170 compliance, capacity verification, a CSI integration or structural approval.',
    '> Only signed linear-static response superposition in kN is supported. Envelope, nonlinear and nested-combination checks are not implemented.',
    '> Source records are user-supplied and not authenticated. Separate evidence IDs do not prove real-world independence. SHA-256 plus replay detects inconsistent records, not maliciously re-signed data; reviewer identity is self-entered.', '',
    `Project: ${safe(snapshot.input.project.name)} / Revision: ${safe(snapshot.input.project.revision)}`,
    `Run: ${safe(snapshot.id)} / Created: ${safe(snapshot.createdAt)}`,
    `Version: ${safe(snapshot.version)}`,
    `Input SHA-256: ${snapshot.inputHash}`,
    `Declared analysis: ${safe(snapshot.input.analysisType)} / Declared unit: ${safe(snapshot.input.unit)} / Synthetic: ${snapshot.input.synthetic}`,
    '', '## Technical results', `Overall: ${snapshot.status}`,
    `PASS ${snapshot.summary.PASS} / FAIL ${snapshot.summary.FAIL} / NOT VERIFIED ${snapshot.summary['NOT VERIFIED']}`,
    'Rule: expected = sum(factor × independent base response). Fixed demo tolerance = max(1 kN, 1% × abs(expected)); endpoints included.', '',
  ];
  for (const result of snapshot.results) {
    lines.push(`### ${safe(result.id)} — ${result.status}`, safe(result.summary), '', '| Expected | Reported | Unit | Tolerance | Reason |', '| --- | --- | --- | --- | --- |');
    for (const detail of result.details) lines.push(`| ${safe(detail.expected)} | ${safe(detail.actual)} | ${safe(detail.unit)} | ${safe(detail.tolerance)} | ${safe(detail.reason)} |`, '', `Formula: ${safe(detail.formula)}`, `Input location: ${safe(detail.location)}`, `Evidence IDs: ${safe(detail.evidenceRefs.join(', '))}`, '');
  }
  lines.push('## Supplied source records', '');
  for (const record of snapshot.input.evidence) lines.push(`### ${safe(record.id)} — ${safe(record.title)}`, `Locator: ${safe(record.locator)}`, `Content: ${safe(record.content)}`, '');
  if (!snapshot.input.evidence.length) lines.push('No source records supplied.', '');
  lines.push('## Recorded human reviews', 'Technical outcomes remain the replayed checker outcomes; a note does not resolve a failed check.', '');
  for (const review of snapshot.reviews) lines.push(`- ${safe(review.at)} / ${safe(review.reviewer)} / ${safe(review.disposition)}: ${safe(review.note)}`);
  if (!snapshot.reviews.length) lines.push('No human review recorded.');
  const serialized = JSON.stringify(snapshot.input, null, 2);
  const longestTicks = Math.max(0, ...(serialized.match(/`+/g) || []).map(ticks => ticks.length));
  const fence = '`'.repeat(Math.max(3, longestTicks + 1));
  lines.push('', '## Input snapshot', '', `${fence}json`, serialized, fence, '');
  return lines.join('\n');
}
