import {ENGINE_VERSION, RULE_VERSION, validateInput, runChecks} from './engine.js';
import {COMBINATION_VERSION, validateCombinationInput, runCombinationChecks, getCombinationSample} from './combinations.js';
import {KNOWLEDGE_VERSION, getDemoKnowledge, retrieveRules} from './knowledge.js';
import {getSample} from './samples.js';

export const AGENT_VERSION = 'controlled-workflow-1.0.0';
export const AGENT_CALL_BUDGET = 5;
export const AGENT_TOOLS = Object.freeze(['retrieve_engineering_rules', 'request_engineering_data', 'run_deterministic_check', 'verify_evidence', 'compose_response']);
export const AGENT_TASKS = Object.freeze([
  {id: 'gravity-full', title: '完整重力 QA', description: '执行六项既有合成重力数据核对。', ruleIds: ['QA-001', 'QA-002', 'QA-003', 'QA-004', 'QA-005', 'QA-006']},
  {id: 'gravity-distribution', title: '分层荷载分配', description: '仅返回 QA-003 分层分配与任务书的核对结果。', ruleIds: ['QA-003']},
  {id: 'gravity-balance', title: '独立反力平衡', description: '仅返回 QA-005 独立反力与任务书的核对结果。', ruleIds: ['QA-005']},
  {id: 'load-combination', title: '线性静力组合', description: '按合成因子核对独立基础响应与单独提供的组合响应。', ruleIds: ['COMB-001']},
].map(task => Object.freeze({...task, ruleIds: Object.freeze(task.ruleIds)})));

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nonempty = value => typeof value === 'string' && value.trim().length > 0;
const taskById = id => AGENT_TASKS.find(task => task.id === id);
const copy = value => JSON.parse(JSON.stringify(value));
function assertJSON(value, ancestors = new Set(), depth = 0) {
  if (depth > 32) throw Error('Excessive JSON nesting.');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (typeof value !== 'object' || ancestors.has(value)) throw Error('Expected finite, acyclic JSON data.');
  if (!Array.isArray(value) && ![Object.prototype, null].includes(Object.getPrototypeOf(value))) throw Error('Expected plain JSON data.');
  ancestors.add(value);
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      if (!Object.hasOwn(value, i)) throw Error('Sparse JSON arrays are not supported.');
      assertJSON(value[i], ancestors, depth + 1);
    }
  } else for (const key of Object.keys(value)) assertJSON(value[key], ancestors, depth + 1);
  ancestors.delete(value);
}
function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
async function hash(value) {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value)));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}
function same(actual, expected) {
  if (Object.is(actual, expected)) return true;
  if (Array.isArray(expected)) return Array.isArray(actual) && actual.length === expected.length && expected.every((item, i) => Object.hasOwn(actual, i) && same(actual[i], item));
  if (!object(actual) || !object(expected)) return false;
  const keys = Object.keys(expected);
  return Object.keys(actual).length === keys.length && keys.every(key => Object.hasOwn(actual, key) && same(actual[key], expected[key]));
}
function summarize(results) {
  if (!Array.isArray(results) || !results.length) throw Error('No deterministic checking results were returned.');
  const summary = {PASS: 0, FAIL: 0, 'NOT VERIFIED': 0};
  for (const result of results) {
    if (!object(result) || !Object.hasOwn(summary, result.status)) throw Error('Invalid deterministic status.');
    summary[result.status]++;
  }
  return {status: summary.FAIL ? 'FAIL' : summary['NOT VERIFIED'] ? 'NOT VERIFIED' : 'PASS', summary, results};
}
function blocked(reason) {
  return summarize([{
    id: 'AGENT-GATE', name: 'Controlled workflow prerequisites', status: 'NOT VERIFIED', summary: reason,
    details: [{label: 'Workflow gate', expected: null, actual: null, unit: null, formula: null, tolerance: null, reason, location: 'task / rule corpus / data provider', evidenceRefs: []}],
  }]);
}

/** Model output may select only a registered task. Findings, tool names and arguments are forbidden. */
export function validateModelTaskProposal(proposal) {
  if (!object(proposal) || Object.keys(proposal).length !== 1 || !Object.hasOwn(proposal, 'taskId') || !taskById(proposal.taskId)) {
    return freeze({accepted: false, taskId: null, reason: 'Only an allowlisted taskId is accepted. Model-selected tools, arguments, values, explanations or claimed findings are not adopted.'});
  }
  return freeze({accepted: true, taskId: proposal.taskId, reason: 'Registered task only; all data, tools and findings remain controlled by the workflow.'});
}

function explain(task, outcome, citations) {
  const lines = [
    `Task: ${task.title} (${task.id}).`,
    `Technical outcome: ${outcome.status}. PASS ${outcome.summary.PASS}; FAIL ${outcome.summary.FAIL}; NOT VERIFIED ${outcome.summary['NOT VERIFIED']}.`,
  ];
  for (const result of outcome.results) {
    lines.push(`${result.id}: ${result.status}. ${result.summary}`);
    for (const detail of result.details || []) {
      if (typeof detail.expected === 'number' || typeof detail.actual === 'number') lines.push(`${detail.label}: expected ${detail.expected ?? 'unavailable'}, actual ${detail.actual ?? 'unavailable'}${detail.unit ? ` ${detail.unit}` : ''}; tolerance ${detail.tolerance ?? 'unavailable'}.`);
    }
  }
  lines.push(citations.length ? `Retrieved synthetic rule citations: ${citations.map(citation => `${citation.ruleId}@${citation.version}`).join(', ')}.` : 'No applicable rule citation is available.');
  lines.push('This explanation is a fixed template generated from verified tool outputs. It is not an LLM response, a code-compliance conclusion or engineering approval.');
  return lines.join('\n');
}

export async function executeAgent(request = {}) {
  assertJSON(request);
  if (!object(request)) throw Error('Agent request must be a JSON object.');
  const extra = Object.keys(request).filter(key => !['taskId', 'input', 'corpus', 'dataMode'].includes(key));
  const taskId = request.taskId ?? 'unknown';
  const definition = taskById(taskId);
  const task = definition ? {id: definition.id, title: definition.title} : {id: String(taskId), title: 'Unsupported task'};
  const input = freeze(copy(request.input ?? null));
  const corpus = freeze(copy(request.corpus === undefined ? getDemoKnowledge() : request.corpus));
  const dataMode = request.dataMode ?? 'controlled-file';
  const [inputHash, corpusHash] = await Promise.all([hash(input), hash(corpus)]);
  const toolTrace = [];
  let calls = 0;
  let stopReason = extra.length ? `Unapproved request fields: ${extra.join(', ')}. Arbitrary tool calls, arguments and claimed findings are not accepted.` : !definition ? `Unsupported task ${String(taskId)}. Select a registered task.` : null;
  const sources = () => [`input:${inputHash}`, `corpus:${corpusHash}`];
  const recordSkip = (tool, inputs, reason) => {
    toolTrace.push({index: toolTrace.length + 1, tool, status: 'skipped', called: false, inputs: copy(inputs), outputs: {skipped: true, reason}, sources: [], errors: [reason], durationMs: 0});
  };
  const invoke = async (tool, inputs, sourceRefs, handler) => {
    if (!AGENT_TOOLS.includes(tool) || ++calls > AGENT_CALL_BUDGET) throw Error('Tool allowlist or fixed call budget exceeded.');
    const started = performance.now();
    try {
      const value = await handler();
      toolTrace.push({index: toolTrace.length + 1, tool, status: value.status === 'NOT VERIFIED' ? 'blocked' : 'ok', called: true, inputs: copy(inputs), outputs: copy(value), sources: [...sourceRefs], errors: value.status === 'NOT VERIFIED' && value.reason ? [value.reason] : [], durationMs: Math.max(0, Math.round((performance.now() - started) * 1000) / 1000)});
      return {ok: true, value};
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Tool failed.';
      toolTrace.push({index: toolTrace.length + 1, tool, status: 'error', called: true, inputs: copy(inputs), outputs: null, sources: [...sourceRefs], errors: [reason], durationMs: Math.max(0, Math.round((performance.now() - started) * 1000) / 1000)});
      return {ok: false, reason};
    }
  };
  // Step 1: no arbitrary query, scope, version or tool arguments supplied by a model.
  const retrieval = await invoke('retrieve_engineering_rules', {taskId: task.id, ruleIds: definition?.ruleIds || [], corpusHash}, [`corpus:${corpusHash}`], () => {
    if (stopReason) return {status: 'NOT VERIFIED', reason: stopReason, rules: [], citations: []};
    const result = retrieveRules({taskId, corpus, ruleIds: [...definition.ruleIds]});
    if (result.status !== 'FOUND') return result;
    const ids = result.rules.map(rule => rule.id).sort();
    if (!same(ids, [...definition.ruleIds].sort()) || !same(result.citations.map(citation => citation.ruleId).sort(), ids)) return {status: 'NOT VERIFIED', reason: 'Required registered rule coverage is incomplete or ambiguous.', rules: [], citations: []};
    return result;
  });
  const citations = retrieval.ok && retrieval.value.status === 'FOUND' ? copy(retrieval.value.citations) : [];
  if (!retrieval.ok || retrieval.value.status !== 'FOUND') stopReason = retrieval.reason || retrieval.value.reason || 'No applicable approved synthetic rule was retrieved.';
  // Step 2: the currently active data adapter is only the controlled input snapshot.
  const dataArguments = {dataMode, inputHash, taskId: task.id};
  if (stopReason) recordSkip('request_engineering_data', dataArguments, stopReason);
  else {
    const data = await invoke('request_engineering_data', dataArguments, [`input:${inputHash}`], () => {
      if (dataMode !== 'controlled-file') return {status: 'NOT VERIFIED', reason: `Data provider ${String(dataMode)} is unavailable. ETABS/SAFE API integration is not implemented; use controlled-file.`, provider: dataMode};
      if (!object(input) || input.synthetic !== true) return {status: 'NOT VERIFIED', reason: 'The controlled workflow requires explicitly synthetic input. No real engineering approval is performed.', provider: dataMode};
      if (taskId === 'load-combination') validateCombinationInput(input); else validateInput(input);
      return {status: 'VALID', provider: 'controlled-file', inputHash, schemaVersion: input.schemaVersion, project: copy(input.project), evidenceRecords: input.evidence.length};
    });
    if (!data.ok || data.value.status !== 'VALID') stopReason = data.reason || data.value.reason || 'Engineering input validation failed.';
  }
  // Step 3: only the selected, locally registered checker can execute.
  const checkArguments = {taskId: task.id, inputHash, ruleIds: definition?.ruleIds || [], engineVersion: taskId === 'load-combination' ? COMBINATION_VERSION : ENGINE_VERSION};
  let calculation = null;
  if (stopReason) recordSkip('run_deterministic_check', checkArguments, stopReason);
  else {
    const check = await invoke('run_deterministic_check', checkArguments, sources(), () => {
      if (taskId === 'load-combination') return runCombinationChecks(input);
      const all = runChecks(input);
      const selected = all.results.filter(result => definition.ruleIds.includes(result.id));
      if (selected.length !== definition.ruleIds.length) throw Error('Registered checker did not return every selected rule.');
      return {version: ENGINE_VERSION, ruleVersion: RULE_VERSION, ...summarize(selected)};
    });
    if (!check.ok) stopReason = check.reason;
    else calculation = check.value;
  }
  // Step 4: missing source records can downgrade a PASS; no model claim can upgrade a result.
  const evidenceCheck = await invoke('verify_evidence', {inputHash, corpusHash, resultIds: calculation?.results.map(result => result.id) || [], citationIds: citations.map(citation => citation.ruleId)}, sources(), () => {
    if (stopReason || !calculation) return {...blocked(stopReason || 'No deterministic result is available.'), reason: stopReason || 'No deterministic result is available.'};
    const byId = new Map(input.evidence.map(record => [record.id, record]));
    const results = calculation.results.map(result => {
      const next = copy(result);
      next.ruleIds = taskId === 'load-combination' ? ['COMB-001'] : [result.id];
      const missing = [...new Set((result.details || []).flatMap(detail => detail.evidenceRefs || []))].filter(ref => {
        const record = byId.get(ref);
        return !record || !nonempty(record.title) || !nonempty(record.locator) || !nonempty(record.content);
      });
      if (result.status === 'PASS' && missing.length) {
        next.status = 'NOT VERIFIED';
        next.summary = `Evidence gate: missing or incomplete source records ${missing.join(', ')}.`;
        next.details = next.details.map(detail => ({...detail, status: 'NOT VERIFIED', reason: next.summary}));
      }
      return next;
    });
    return summarize(results);
  });
  const outcome = evidenceCheck.ok ? evidenceCheck.value : blocked(evidenceCheck.reason);
  // Step 5: template interpretation only. No generated engineering values or free-form model output.
  const composition = await invoke('compose_response', {taskId: task.id, status: outcome.status, resultIds: outcome.results.map(result => result.id), citationIds: citations.map(citation => citation.ruleId)}, sources(), () => ({status: outcome.status, explanation: explain(task, outcome, citations), citations}));
  if (!composition.ok) throw Error('Controlled explanation could not be composed.');
  const run = {
    version: AGENT_VERSION,
    versions: {engine: ENGINE_VERSION, gravityRule: RULE_VERSION, combination: COMBINATION_VERSION, knowledge: KNOWLEDGE_VERSION},
    id: globalThis.crypto.randomUUID(), createdAt: new Date().toISOString(),
    taskId: task.id, task, dataMode, input, corpus, inputHash, corpusHash,
    status: outcome.status, results: outcome.results, summary: outcome.summary,
    citations, explanation: composition.value.explanation, toolTrace, callsUsed: calls, callBudget: AGENT_CALL_BUDGET,
    requestFields: extra,
    scope: 'Synthetic controlled local workflow; no LLM inference or ETABS/SAFE API access.',
  };
  run.runHash = await hash(run);
  return freeze(run);
}

const safe = value => String(value ?? '—').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replace(/[\\`*_\[\]{}#|]/g, '\\$&').replace(/[\r\n]+/g, ' ');
function fenceJSON(value) {
  const serialized = JSON.stringify(value, null, 2);
  const ticks = '`'.repeat(Math.max(3, 1 + Math.max(0, ...(serialized.match(/`+/g) || []).map(match => match.length))));
  return [`${ticks}json`, serialized, ticks];
}
export async function agentReport(run) {
  assertJSON(run);
  const saved = copy(run);
  if (!object(saved) || saved.version !== AGENT_VERSION) throw Error('Agent workflow version is stale; execute it again.');
  const {runHash, ...unsigned} = saved;
  if (typeof runHash !== 'string' || await hash(unsigned) !== runHash) throw Error('Agent run integrity hash mismatch.');
  if (!nonempty(saved.id) || !Number.isFinite(Date.parse(saved.createdAt))) throw Error('Invalid agent run identity or date.');
  if (await hash(saved.input) !== saved.inputHash || await hash(saved.corpus) !== saved.corpusHash) throw Error('Agent input or rule corpus hash mismatch.');
  const replayRequest = Object.assign(Object.create(null), {taskId: saved.taskId, input: saved.input, corpus: saved.corpus, dataMode: saved.dataMode});
  // Retain rejected request field names for deterministic replay, never their untrusted values.
  if (!Array.isArray(saved.requestFields) || saved.requestFields.some(key => typeof key !== 'string')) throw Error('Invalid request-field audit.');
  for (const key of saved.requestFields) replayRequest[key] = null;
  const replay = await executeAgent(replayRequest);
  for (const key of ['version', 'versions', 'taskId', 'task', 'dataMode', 'inputHash', 'corpusHash', 'status', 'results', 'summary', 'citations', 'explanation', 'callsUsed', 'callBudget', 'requestFields', 'scope']) if (!same(saved[key], replay[key])) throw Error(`Agent ${key} differs from deterministic replay.`);
  if (!Array.isArray(saved.toolTrace) || saved.toolTrace.some(step => !object(step) || typeof step.durationMs !== 'number' || !Number.isFinite(step.durationMs) || step.durationMs < 0)) throw Error('Invalid agent tool trace timing.');
  const traceSemantics = trace => trace.map(({durationMs, ...step}) => step);
  if (!same(traceSemantics(saved.toolTrace), traceSemantics(replay.toolTrace))) throw Error('Agent tool trace differs from deterministic replay.');
  const lines = [
    '# Controlled local QA workflow report', '',
    '> DRAFT — NOT ENGINEERING APPROVAL. This synthetic workflow does not call an LLM or ETABS/SAFE API. Explanations are templates of checked outputs; rule retrieval is a curated local implementation, not a production RAG service.',
    '> Hashes and replay check consistency, not source authenticity, reviewer identity, signatures or structural safety.', '',
    `Run: ${safe(saved.id)} / ${safe(saved.createdAt)}`,
    `Task: ${safe(saved.task.title)} (${safe(saved.taskId)}) / Provider: ${safe(saved.dataMode)}`,
    `Input SHA-256: ${saved.inputHash}`, `Rule corpus SHA-256: ${saved.corpusHash}`, `Run SHA-256: ${saved.runHash}`,
    `Versions: ${safe(JSON.stringify(saved.versions))}`, '',
    '## Technical outcome', `${saved.status}: PASS ${saved.summary.PASS} / FAIL ${saved.summary.FAIL} / NOT VERIFIED ${saved.summary['NOT VERIFIED']}`, '',
    '## Grounded template explanation', ...saved.explanation.split('\n').map(line => safe(line)), '',
    '## Checking details',
  ];
  for (const result of saved.results) {
    lines.push('', `### ${safe(result.id)} — ${result.status}`, safe(result.summary));
    for (const detail of result.details || []) lines.push(`- ${safe(detail.label)}: expected ${safe(detail.expected)}, actual ${safe(detail.actual)}, unit ${safe(detail.unit)}, tolerance ${safe(detail.tolerance)}.`, `  Formula: ${safe(detail.formula)}. Reason: ${safe(detail.reason || detail.status)}.`, `  Location: ${safe(detail.location)}. Sources: ${safe((detail.evidenceRefs || []).join(', '))}.`);
  }
  lines.push('', '## Retrieved rule citations', '');
  for (const citation of saved.citations) lines.push(`- ${safe(citation.ruleId)} @ ${safe(citation.version)} / ${safe(citation.authority)} / ${safe(citation.approval)}`, `  ${safe(citation.title)} — ${safe(citation.locator)} / Scope: ${safe(citation.scope)}`, `  Retrieved text: ${safe(citation.quote)}`);
  if (!saved.citations.length) lines.push('No applicable rule citations; no engineering PASS was inferred.');
  lines.push('', '## Supplied engineering evidence', '');
  for (const record of Array.isArray(saved.input?.evidence) ? saved.input.evidence : []) lines.push(`- ${safe(record.id)} — ${safe(record.title)} / ${safe(record.locator)}: ${safe(record.content)}`);
  lines.push('', '## Tool trace', `Executed calls: ${saved.callsUsed} / ${saved.callBudget}. Skipped steps are not tool calls.`, '');
  for (const step of saved.toolTrace) lines.push(`### ${step.index}. ${safe(step.tool)} — ${step.status}`, `Called: ${step.called}; elapsed: ${step.durationMs} ms.`, ...fenceJSON({inputs: step.inputs, outputs: step.outputs, sources: step.sources, errors: step.errors}), '');
  lines.push('## Input snapshot', '', ...fenceJSON(saved.input), '', '## Rule corpus snapshot', '', ...fenceJSON(saved.corpus), '');
  return lines.join('\n');
}

export async function runAgentValidation() {
  const corpus = getDemoKnowledge();
  const suite = [
    {id: 'AG-01', title: 'Clean gravity fixture', taskId: 'gravity-full', input: getSample('clean'), expected: 'PASS'},
    {id: 'AG-02', title: 'Gravity mismatch fixture', taskId: 'gravity-full', input: getSample('issues'), expected: 'FAIL'},
    {id: 'AG-03', title: 'Gravity evidence missing', taskId: 'gravity-full', input: getSample('missing'), expected: 'NOT VERIFIED'},
    {id: 'AG-04', title: 'Clean combination fixture', taskId: 'load-combination', input: getCombinationSample('clean'), expected: 'PASS'},
    {id: 'AG-05', title: 'Combination mismatch fixture', taskId: 'load-combination', input: getCombinationSample('mismatch'), expected: 'FAIL'},
    {id: 'AG-06', title: 'Combination base case missing', taskId: 'load-combination', input: getCombinationSample('missing'), expected: 'NOT VERIFIED'},
    {id: 'AG-07', title: 'Empty knowledge blocks calculation', taskId: 'gravity-full', input: getSample('clean'), corpus: {...corpus, rules: []}, expected: 'NOT VERIFIED', noCheck: true},
    {id: 'AG-08', title: 'ETABS API unavailable', taskId: 'gravity-full', input: getSample('clean'), dataMode: 'ETABS-api', expected: 'NOT VERIFIED', noCheck: true},
    {id: 'AG-09', title: 'Unknown model-selected task', taskId: 'invented-capacity-check', input: getSample('clean'), expected: 'NOT VERIFIED', noCheck: true},
  ];
  const cases = [];
  for (const item of suite) {
    const run = await executeAgent({taskId: item.taskId, input: item.input, corpus: item.corpus || corpus, dataMode: item.dataMode || 'controlled-file'});
    const noCheck = !item.noCheck || !run.toolTrace.find(step => step.tool === 'run_deterministic_check').called;
    const matched = item.expected === run.status && noCheck;
    cases.push({id: item.id, title: item.title, expected: item.expected, actual: run.status, matched, reason: !noCheck ? 'A blocked fixture unexpectedly invoked calculation.' : matched ? 'Handwritten fixture status matches the controlled workflow.' : `Expected ${item.expected}, received ${run.status}.`});
  }
  const proposal = validateModelTaskProposal({taskId: 'load-combination', status: 'PASS', findings: 'All engineering checks passed.'});
  const checked = await executeAgent({taskId: 'load-combination', input: getCombinationSample('mismatch'), corpus, dataMode: 'controlled-file'});
  const actual = !proposal.accepted && checked.status === 'FAIL' ? 'REJECTED; FAIL preserved' : 'UNSAFE MODEL CLAIM';
  cases.push({id: 'AG-10', title: 'Unsupported model findings cannot override a mismatch', expected: 'REJECTED; FAIL preserved', actual, matched: actual === 'REJECTED; FAIL preserved', reason: proposal.reason});
  const matched = cases.filter(result => result.matched).length;
  return freeze({generatedAt: new Date().toISOString(), summary: {total: cases.length, matched, mismatched: cases.length - matched}, cases});
}
