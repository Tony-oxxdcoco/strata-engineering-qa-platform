import { RULES, RULE_VERSION } from './engine.js';
import { COMBINATION_VERSION } from './combinations.js';

export const KNOWLEDGE_VERSION = 'knowledge-demo-1.0.0';
export const GRAVITY_KNOWLEDGE_SCOPE = 'gravity-unfactored-static-excluding-self-weight';
export const COMBINATION_KNOWLEDGE_SCOPE = 'linear-static-combination-response';
const GRAVITY_RULE_IDS = ['QA-001', 'QA-002', 'QA-003', 'QA-004', 'QA-005', 'QA-006'];
const taskDefinitions = [
  { id: 'gravity-full', ruleIds: GRAVITY_RULE_IDS, checkIds: GRAVITY_RULE_IDS, scope: GRAVITY_KNOWLEDGE_SCOPE, version: RULE_VERSION },
  { id: 'gravity-distribution', ruleIds: ['QA-003'], checkIds: ['QA-003'], scope: GRAVITY_KNOWLEDGE_SCOPE, version: RULE_VERSION },
  { id: 'gravity-balance', ruleIds: ['QA-005'], checkIds: ['QA-005'], scope: GRAVITY_KNOWLEDGE_SCOPE, version: RULE_VERSION },
  { id: 'load-combination', ruleIds: ['COMB-001'], checkIds: ['C1', 'C2'], scope: COMBINATION_KNOWLEDGE_SCOPE, version: COMBINATION_VERSION },
];
export const KNOWLEDGE_TASKS = Object.freeze(taskDefinitions.map(task => Object.freeze({
  ...task, ruleIds: Object.freeze([...task.ruleIds]), checkIds: Object.freeze([...task.checkIds]),
})));
const TASKS = new Map(KNOWLEDGE_TASKS.map(task => [task.id, task]));
const englishTitles = {
  'QA-001': 'Record uniqueness', 'QA-002': 'Floor and load-case coverage',
  'QA-003': 'Floor load distribution', 'QA-004': 'Load-case totals',
  'QA-005': 'Independent vertical reaction balance', 'QA-006': 'Evidence completeness',
};
const curatedRules = RULES.map(rule => ({
  id: rule.id,
  version: RULE_VERSION,
  authority: 'SYNTHETIC',
  approval: 'demo-approved',
  status: 'active',
  scope: GRAVITY_KNOWLEDGE_SCOPE,
  source: {
    title: `Synthetic QA manual: ${englishTitles[rule.id]} / ${rule.name}`,
    locator: rule.source,
    text: `${rule.description}\nFormula: ${rule.formula}.\nRequired evidence: ${rule.requires}.\nScope: unfactored static gravity, SDL and LIVE only, self-weight excluded, upward reaction positive. Numerical comparisons use the fixed demonstration tolerance max(1 kN, 1% of the absolute expected value). These are synthetic demonstration rules, not an Australian Standard or structural design approval.`,
  },
  checkIds: [rule.id],
  taskIds: KNOWLEDGE_TASKS.filter(task => task.ruleIds.includes(rule.id)).map(task => task.id),
}));
curatedRules.push({
  id: 'COMB-001',
  version: COMBINATION_VERSION,
  authority: 'SYNTHETIC',
  approval: 'demo-approved',
  status: 'active',
  scope: COMBINATION_KNOWLEDGE_SCOPE,
  source: {
    title: 'Synthetic linear-static combination response reconciliation',
    locator: 'Synthetic combination fixture / checking method §1',
    text: 'For linear-static responses in kN, calculate the expected response as the sum of each supplied factor multiplied by its independently supplied base-case response. Compare the separately supplied reported response with expected ± max(1 kN, 1% of abs(expected)); endpoints are included. Missing base cases, missing separate source evidence, empty terms, unsupported analysis or arithmetic failure produce NOT VERIFIED. The shipped examples are C1 = 1.2 SDL + 1.5 LIVE and C2 = SDL - LIVE. These chosen factors are synthetic examples, not an AS 1170 rule. The same calculation method may check other explicitly supplied combination IDs within the tool contract; this does not approve their factors or establish structural safety.',
  },
  checkIds: ['C1', 'C2'],
  taskIds: ['load-combination'],
});
const CURATED = new Map(curatedRules.map(rule => [rule.id, rule]));
const cloneRule = rule => ({ ...rule, source: { ...rule.source }, checkIds: [...rule.checkIds], taskIds: [...rule.taskIds] });

export function getDemoKnowledge() {
  return {
    schemaVersion: 'knowledge-1.0', synthetic: true, authority: 'SYNTHETIC',
    purpose: 'controlled-demo', version: KNOWLEDGE_VERSION,
    rules: curatedRules.map(cloneRule),
  };
}

function plain(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value));
}
function exactKeys(value, keys, path) {
  if (!plain(value)) throw Error(`${path}: expected a plain object.`);
  for (const key of keys) if (!Object.hasOwn(value, key)) throw Error(`${path}: missing ${key}.`);
  for (const key of Object.keys(value)) if (!keys.includes(key)) throw Error(`${path}: unsupported field ${key}.`);
}
function sameStringSet(actual, expected) {
  return Array.isArray(actual) && actual.length === expected.length
    && new Set(actual).size === actual.length
    && Array.from({ length: actual.length }, (_, index) => index)
      .every(index => Object.hasOwn(actual, index) && typeof actual[index] === 'string' && expected.includes(actual[index]));
}

/** Validate against shipped demo definitions. A caller-supplied approval label is not trust. */
export function validateKnowledgeCorpus(corpus) {
  exactKeys(corpus, ['schemaVersion', 'synthetic', 'authority', 'purpose', 'version', 'rules'], 'corpus');
  if (corpus.schemaVersion !== 'knowledge-1.0' || corpus.version !== KNOWLEDGE_VERSION) throw Error('Unsupported knowledge schema or corpus version.');
  if (corpus.synthetic !== true || corpus.authority !== 'SYNTHETIC' || corpus.purpose !== 'controlled-demo') throw Error('Knowledge must be explicitly marked as the synthetic controlled demonstration corpus.');
  if (!Array.isArray(corpus.rules) || corpus.rules.length > 100) throw Error('corpus.rules must be an array with at most 100 entries.');
  for (let index = 0; index < corpus.rules.length; index++) if (!Object.hasOwn(corpus.rules, index)) throw Error(`rules[${index}]: sparse arrays are unsupported.`);
  const seen = new Set(), activeChecks = new Set();
  const rules = corpus.rules.map((rule, index) => {
    const path = `rules[${index}]`;
    exactKeys(rule, ['id', 'version', 'authority', 'approval', 'status', 'scope', 'source', 'checkIds', 'taskIds'], path);
    const approved = CURATED.get(rule.id);
    if (!approved) throw Error(`${path}: unknown rule ID; imported text cannot approve a new check.`);
    if (seen.has(rule.id)) throw Error(`${path}: ambiguous duplicate rule ${rule.id}; no version is selected automatically.`);
    seen.add(rule.id);
    if (rule.authority !== 'SYNTHETIC' || rule.approval !== 'demo-approved') throw Error(`${path}: only curated demo approval is supported; this is not customer approval.`);
    if (rule.version !== approved.version || rule.scope !== approved.scope) throw Error(`${path}: rule version or scope does not match the supported definition.`);
    if (!['active', 'retired'].includes(rule.status)) throw Error(`${path}: status must be active or retired.`);
    if (!sameStringSet(rule.checkIds, approved.checkIds) || !sameStringSet(rule.taskIds, approved.taskIds)) throw Error(`${path}: task/check applicability differs from the curated definition.`);
    exactKeys(rule.source, ['title', 'locator', 'text'], `${path}.source`);
    for (const field of ['title', 'locator', 'text']) {
      if (rule.source[field] !== approved.source[field]) throw Error(`${path}.source.${field}: missing or altered source cannot be promoted by a demo-approved label.`);
    }
    if (rule.status === 'active') for (const task of rule.taskIds) for (const check of rule.checkIds) {
      const key = JSON.stringify([task, rule.version, rule.scope, check]);
      if (activeChecks.has(key)) throw Error(`${path}: conflicting active rules for ${task} / ${check}.`);
      activeChecks.add(key);
    }
    // Return canonical copies, retaining only an explicitly requested retirement.
    return { ...cloneRule(approved), status: rule.status };
  });
  return { schemaVersion: corpus.schemaVersion, synthetic: true, authority: 'SYNTHETIC', purpose: 'controlled-demo', version: corpus.version, rules };
}

const notVerified = reason => ({ status: 'NOT VERIFIED', reason, rules: [], citations: [] });
const citation = rule => ({
  ruleId: rule.id, version: rule.version, authority: rule.authority, approval: rule.approval,
  scope: rule.scope, title: rule.source.title, locator: rule.source.locator, quote: rule.source.text,
});
const found = (rules, reason) => ({ status: 'FOUND', reason, rules: rules.map(cloneRule), citations: rules.map(citation) });
function validateOptions({ taskId, ruleIds, version, scope, query }, requireTask) {
  if ((requireTask || taskId !== undefined) && !TASKS.has(taskId)) throw Error(`Unsupported task: ${String(taskId)}.`);
  if (ruleIds !== undefined && (!Array.isArray(ruleIds) || ruleIds.length > 100 || new Set(ruleIds).size !== ruleIds.length || ruleIds.some(id => typeof id !== 'string' || !CURATED.has(id)))) throw Error('ruleIds must contain unique, known rule IDs.');
  for (const [key, value] of [['version', version], ['scope', scope]]) if (value !== undefined && (typeof value !== 'string' || !value || value.length > 200)) throw Error(`${key} must be an explicit nonempty string.`);
  if (query !== undefined && (typeof query !== 'string' || query.length > 500)) throw Error('query must be text of at most 500 characters.');
}
function filteredRules(corpus, { taskId, ruleIds, version, scope }) {
  return corpus.rules.filter(rule => rule.status === 'active'
    && (taskId === undefined || rule.taskIds.includes(taskId))
    && (ruleIds === undefined || ruleIds.includes(rule.id))
    && (version === undefined || rule.version === version)
    && (scope === undefined || rule.scope === scope));
}
const terms = query => [...new Set((query || '').toLowerCase().match(/[\p{L}\p{N}_-]+/gu) || [])];
function lexicalScore(rule, tokens) {
  const fields = [[`${rule.id} ${rule.checkIds.join(' ')}`, 8], [rule.source.title, 4], [rule.source.locator, 2], [rule.source.text, 1]];
  return tokens.reduce((total, token) => total + fields.reduce((score, [text, weight]) => score + (text.toLowerCase().includes(token) ? weight : 0), 0), 0);
}
function ranked(rules, tokens) {
  return rules.map(rule => ({ rule, score: lexicalScore(rule, tokens) }))
    .sort((a, b) => b.score - a.score || a.rule.id.localeCompare(b.rule.id));
}

/** Complete task-rule retrieval. Lexical ranking affects display order, never coverage. */
export function retrieveRules(options = {}) {
  try {
    if (!plain(options)) throw Error('Retrieval options must be an object.');
    const { taskId, corpus = getDemoKnowledge(), ruleIds, version, scope, query = '' } = options;
    const filters = { taskId, ruleIds, version, scope, query };
    validateOptions(filters, true);
    const valid = validateKnowledgeCorpus(corpus);
    const rules = filteredRules(valid, filters);
    const required = TASKS.get(taskId).ruleIds;
    const missing = required.filter(id => !rules.some(rule => rule.id === id));
    if (missing.length) return notVerified(`Missing, retired or filtered required rules for ${taskId}: ${missing.join(', ')}.`);
    return found(ranked(rules, terms(query)).map(item => item.rule), `Retrieved ${rules.length} curated synthetic rule(s) for ${taskId}. Retrieval is not an engineering verdict.`);
  } catch (error) {
    return notVerified(`Rule retrieval blocked: ${error instanceof Error ? error.message : 'invalid knowledge input'}`);
  }
}

/** Small lexical full-text search for browsing; never an execution authorization. */
export function searchRules(options = {}) {
  try {
    if (!plain(options)) throw Error('Search options must be an object.');
    const { query, corpus = getDemoKnowledge(), taskId, ruleIds, version, scope, limit = 10 } = options;
    const filters = { taskId, ruleIds, version, scope, query };
    validateOptions(filters, false);
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw Error('limit must be an integer from 1 to 100.');
    const tokens = terms(query);
    if (!tokens.length) return notVerified('Enter a nonempty lexical search query.');
    const valid = validateKnowledgeCorpus(corpus);
    const matches = ranked(filteredRules(valid, filters), tokens).filter(item => item.score > 0).slice(0, limit);
    if (!matches.length) return notVerified('No active curated rule matches the exact filters and lexical query.');
    return found(matches.map(item => item.rule), `Found ${matches.length} lexical match(es). Use complete task retrieval before executing a check.`);
  } catch (error) {
    return notVerified(`Rule search blocked: ${error instanceof Error ? error.message : 'invalid knowledge input'}`);
  }
}
