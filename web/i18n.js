import en from './locales/en.js';
import zhCN from './locales/zh-CN.js';

// This module translates application-owned text only. Callers must leave source
// excerpts, identifiers, user names, numbers, units and raw audit records alone.
export const LANGUAGE_KEY = 'strata.workbench.language';
export const languages = Object.freeze(['en', 'zh-CN']);
export const catalogues = Object.freeze({en, 'zh-CN': zhCN});
const missing = new Set();
let language = 'en';
try {
  const saved = globalThis.localStorage?.getItem(LANGUAGE_KEY);
  if (languages.includes(saved)) language = saved;
} catch { /* A restricted browser still supports an in-memory preference. */ }

function applyDocumentLanguage() {
  if (globalThis.document?.documentElement) document.documentElement.lang = language;
}
applyDocumentLanguage();

export function getLanguage() { return language; }
export function setLanguage(next) {
  if (!languages.includes(next)) throw new TypeError(`Unsupported UI language: ${next}`);
  const changed = next !== language;
  language = next;
  try { globalThis.localStorage?.setItem(LANGUAGE_KEY, next); } catch { /* Memory fallback. */ }
  applyDocumentLanguage();
  return changed;
}

export function t(key, variables = {}) {
  if (!Object.hasOwn(en, key)) missing.add(key);
  const template = catalogues[language][key] ?? en[key] ?? String(key);
  // Interpolation is literal and never evaluates HTML or code. Callers escape
  // the completed output when placing it into an HTML template.
  return template.replace(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g, (match, name) =>
    Object.hasOwn(variables, name) ? String(variables[name]) : match);
}

// For source-literal UI labels. Unknown text remains byte-for-byte unchanged.
// Prefer t() for new UI strings, so missing-key checks identify omissions.
export function ui(text) {
  const value = String(text ?? '');
  return Object.hasOwn(en, value) ? t(value) : value;
}
export function missingKeys() { return [...missing].sort(); }
export function clearMissingKeys() { missing.clear(); }

const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function label(key, variables) {
  if (!Object.hasOwn(en, key)) return escape(key);
  const attrs = variables ? ` data-i18n-vars="${escape(JSON.stringify(variables))}"` : '';
  return `<span data-i18n="${escape(key)}"${attrs}>${escape(t(key, variables))}</span>`;
}
export function systemLabel(value) {
  return `<span data-i18n-system="${escape(value)}">${escape(translateSystemText(value))}</span>`;
}
export function translateMarked(root = globalThis.document) {
  if (!root?.querySelectorAll) return;
  for (const node of root.querySelectorAll('[data-i18n]')) {
    let variables;
    try { variables = JSON.parse(node.getAttribute('data-i18n-vars') || '{}'); } catch { variables = {}; }
    node.textContent = t(node.getAttribute('data-i18n'), variables);
  }
  for (const node of root.querySelectorAll('[data-i18n-system]')) node.textContent = translateSystemText(node.getAttribute('data-i18n-system'));
  for (const node of root.querySelectorAll('[data-i18n-status]')) node.textContent = displayStatus(node.getAttribute('data-i18n-status'));
  for (const attribute of ['placeholder', 'aria-label', 'title', 'alt']) {
    for (const node of root.querySelectorAll(`[data-i18n-${attribute}]`)) node.setAttribute(attribute, t(node.getAttribute(`data-i18n-${attribute}`)));
  }
  for (const node of root.querySelectorAll('[data-language]')) node.setAttribute('aria-pressed', String(node.getAttribute('data-language') === language));
  for (const node of root.querySelectorAll('[data-i18n-validity]')) node.setCustomValidity(t(node.getAttribute('data-i18n-validity')));
  if (globalThis.document) document.title = t('page.title');
}

const statusKeys = Object.freeze({
  'PASS':'status.PASS', 'FAIL':'status.FAIL', 'NOT VERIFIED':'status.NOT VERIFIED',
  'QUEUED':'status.QUEUED', 'RUNNING':'status.RUNNING', 'WAITING':'status.WAITING',
  'COMPLETED':'status.COMPLETED', 'ERROR':'status.ERROR', 'CANCELLED':'status.CANCELLED',
  'CANCELLING':'status.CANCELLING', 'READY':'status.READY', 'STORED':'status.STORED',
  'NEEDS_MAPPING':'status.NEEDS_MAPPING', 'NEEDS_OCR':'status.NEEDS_OCR',
  'NEEDS_REVIEW':'status.NEEDS_REVIEW', 'FOUND':'status.FOUND', 'CONFLICT':'status.CONFLICT',
  'MISSING':'status.MISSING', 'STALE':'status.STALE', 'INVALID':'status.INVALID',
  'VALID':'status.VALID', 'CHANGED':'status.CHANGED', 'UNCHANGED':'status.UNCHANGED',
  'OPEN':'status.OPEN', 'ASSIGNED':'status.ASSIGNED', 'RESOLVED':'status.RESOLVED',
  'AWAITING_EVIDENCE':'status.AWAITING_EVIDENCE', 'APPROVED':'status.APPROVED',
  'UNREVIEWED':'status.UNREVIEWED', 'EVIDENCE_REQUESTED':'status.EVIDENCE_REQUESTED',
  'DRAFT':'status.DRAFT', 'RETIRED':'status.RETIRED', 'CONFIRMED':'status.CONFIRMED',
  'PENDING_REVIEW':'status.PENDING_REVIEW',
  'NOT REVIEWED':'status.NOT REVIEWED', 'NOT CONFIRMED':'status.NOT CONFIRMED',
  'REQUEST_EVIDENCE':'status.REQUEST_EVIDENCE', 'APPROVE':'status.APPROVE',
  'VIEWER':'role.viewer', 'ENGINEER':'role.engineer', 'REVIEWER':'role.reviewer',
  'ACTIVE':'Current', 'SYNTHETIC':'Synthetic', 'CLIENT':'Client',
  'OK':'status.OK', 'BLOCKED':'status.BLOCKED', 'PENDING':'Pending',
});
export function displayStatus(value) {
  const raw = String(value ?? '');
  const key = statusKeys[raw.toUpperCase()];
  if (!key) return ui(raw);
  // English preserves protocol values and original casing for roles/approvals.
  if (language === 'en' && !['SYNTHETIC', 'CLIENT', 'ACTIVE'].includes(raw.toUpperCase())) return raw;
  return t(key);
}

const taskLabels = Object.freeze({
  'gravity-full':'Complete gravity review', 'gravity-distribution':'Floor load distribution',
  'gravity-balance':'Independent reaction balance', 'load-combination':'Linear load combination',
  'combination-configuration':'Combination configuration', 'handoff':'Engineering handoff',
  'seismic-configuration':'Seismic setup', 'mass-source':'Mass source configuration',
  'additional-settings':'Additional settings',
});

// Exact allowlisted templates for system-generated diagnostics. Their captured
// data (paths, IDs, units, original values) is retained; arbitrary user text is
// never translated. Keep this list small and anchored as backend messages evolve.
const systemPatterns = [
  [/^JSON nesting exceeds (\d+) levels\.$/, match => t('JSON nesting exceeds {depth} levels.', {depth:match[1]})],
  [/^JSON 嵌套超过 (\d+) 层。$/, match => t('JSON nesting exceeds {depth} levels.', {depth:match[1]})],
  [/^(.+) must be a non-empty string of at most (\d+) characters$/, match => t('{field} must be a non-empty string of at most {maximum} characters', {field:match[1],maximum:match[2]})],
  [/^(.+) must not contain whitespace$/, match => t('{field} must not contain whitespace', {field:match[1]})],
  [/^(.+) must not contain control characters$/, match => t('{field} must not contain control characters', {field:match[1]})],
  [/^(.+) must contain valid Unicode$/, match => t('{field} must contain valid Unicode', {field:match[1]})],
  [/^(.+) must be a non-empty list of at most 256 identifiers$/, match => t('{field} must be a non-empty list of at most 256 identifiers', {field:match[1]})],
  [/^(.+) must not contain duplicates$/, match => t('{field} must not contain duplicates', {field:match[1]})],
  [/^(.+): missing or unsupported fields$/, match => t('{label}: missing or unsupported fields', {label:match[1]})],
  [/^Rule check IDs do not cover task (.+)$/, match => t('Rule check IDs do not cover task {task}', {task:match[1]})],
  [/^Invalid adapter (.+)$/, match => t('Invalid adapter {field}', {field:match[1]})],
  [/^Conflicting output path (.+)$/, match => t('Conflicting output path {path}', {path:match[1]})],
  [/^Output path already exists: (.+)$/, match => t('Output path already exists: {path}', {path:match[1]})],
  [/^(.+): adapter expects (\.[a-z0-9]+)$/, match => t('{filename}: adapter expects {extension}', {filename:match[1],extension:match[2]})],
  [/^(.+): CSV exceeds 1 MiB$/, match => t('{filename}: CSV exceeds 1 MiB', {filename:match[1]})],
  [/^(.+): missing, duplicate or oversized headers$/, match => t('{filename}: missing, duplicate or oversized headers', {filename:match[1]})],
  [/^(.+): too many rows$/, match => t('{filename}: too many rows', {filename:match[1]})],
  [/^(.+): duplicate JSON key (.+)$/, match => t('{filename}: duplicate JSON key {key}', {filename:match[1],key:match[2]})],
  [/^Duplicate (.+)\.$/, match => t('Duplicate {kind}.', {kind:match[1]})],
  [/^(.+) must be an array of at most (\d+) records\.$/, match => t('{field} must be an array of at most {maximum} records.', {field:match[1],maximum:match[2]})],
  [/^(.+) has invalid ID or numeric value\.$/, match => t('{field} has invalid ID or numeric value.', {field:match[1]})],
  [/^Invalid (.+) record\.$/, match => t('Invalid {kind} record.', {kind:match[1]})],
  [/^Missing or oversized (.+) list\.$/, match => t('Missing or oversized {name} list.', {name:match[1]})],
  [/^Malformed (.+) entry\.$/, match => t('Malformed {name} entry.', {name:match[1]})],
  [/^Missing rule fields: (.+)$/, match => t('Missing rule fields: {fields}', {fields:match[1]})],
  [/^(File|Snapshot|Rule|Run|Adapter|Evaluation|Case) not found$/, match => t('{resource} not found', {resource:ui(match[1])})],
  [/^Run polling stopped: (.*)$/s, match => t('Run polling stopped: {reason}', {reason:translateSystemText(match[1])})],
  [/^Package valid: (\d+) rules\. Approval remains local\.$/, match => t('Package valid: {count} rules. Approval remains local.', {count:match[1]})],
  [/^Request failed \((\d+)\)\.$/, match => t('Request failed ({status}).', {status:match[1]})],
  [/^The source file was saved, but no snapshot was created: (.*) You can inspect the saved file in Knowledge\.$/s, match => t('The source file was saved, but no snapshot was created: {reason} You can inspect the saved file in Knowledge.', {reason:translateSystemText(match[1])})],
  [/^(gravity-full|gravity-distribution|gravity-balance|load-combination|combination-configuration|handoff|seismic-configuration|mass-source|additional-settings): (PASS|FAIL|NOT VERIFIED)\.$/, match => `${ui(taskLabels[match[1]])}: ${displayStatus(match[2])}.`],
  [/^([A-Z0-9][A-Z0-9_-]*): (PASS|FAIL|NOT VERIFIED)\. (.*)$/s, match => `${match[1]}: ${displayStatus(match[2])}. ${translateSystemText(match[3])}`],
  [/^(Record uniqueness|Floor and load-case coverage|Floor load distribution|Load-case totals|Independent vertical reaction balance|Evidence completeness) (failed|could not be verified)\. Inspect the item values and original source details below\.$/, match => t(match[2] === 'failed' ? '{check} failed. Inspect the item values and original source details below.' : '{check} could not be verified. Inspect the item values and original source details below.', {check:ui(match[1])})],
  [/^Linear-static combination (.+)$/, match => t('Linear-static combination {id}', {id:match[1]})],
  [/^Conflicting approved versions for rule (.+)$/, match => t('Conflicting approved versions for rule {id}', {id:match[1]})],
  [/^Conflicting approved contents for rule (.+)$/, match => t('Conflicting approved contents for rule {id}', {id:match[1]})],
  [/^Missing approved evidence for required checks: (.+)$/, match => t('Missing approved evidence for required checks: {ids}', {ids:match[1]})],
  [/^Missing mapped path (.+)\.$/, match => t('Missing mapped path {path}.', {path:match[1]})],
  [/^Duplicate explicit identity; first occurrence at row (\d+); records were not merged$/, match => t('Duplicate explicit identity; first occurrence at row {row}; records were not merged', {row:match[1]})],
  [/^Missing terms: (\[[^\n]*\]); extra terms: (\[[^\n]*\]); factors outside tolerance: (\[[^\n]*\])\.$/, match => t('Missing terms: {missing}; extra terms: {extra}; factors outside tolerance: {wrong}.', {missing:match[1],extra:match[2],wrong:match[3]})],
  [/^(需补充|遗漏|额外) (.+)$/, match => t(`${match[1]} {id}`, {id:match[2]})],
  [/^(任务书重复|模型分配重复|反力重复|记录 ID 重复)：(.+)$/, match => t(`${match[1]}：{id}`, {id:match[2]})],
  [/^Missing: (\[[^\n]*\]); extra: (\[[^\n]*\]); extra allowed: (True|False)\.$/, match => t('Missing: {missing}; extra: {extra}; extra allowed: {allowed}.', {missing:match[1],extra:match[2],allowed:match[3]})],
  [/^有 (\d+) 类必需资料、(\d+) 条数值来源未验证。$/, match => t('Required material types unverified: {materials}; numerical sources unverified: {sources}.', {materials:match[1],sources:match[2]})],
];
export function translateSystemText(text) {
  const value = String(text ?? '');
  if (Object.hasOwn(en, value)) return t(value);
  // GUI validation may already have used ui() when it raised its error. Only
  // reverse exact catalogue messages, keeping the original source for switching.
  const original = Object.keys(zhCN).find(key => zhCN[key] === value);
  if (original) return t(original);
  // The parser stores its English message permanently. A Chinese envelope is
  // also recognized for callers that already displayed the message. Only the
  // diagnostic reason translates: pointer keys, lines and columns stay raw,
  // including keys containing newlines or text that resembles a UI label.
  const strict = value.match(/^Strict JSON error: ([\s\S]+?) at line (\d+), column (\d+), path ([\s\S]*)\.$/) ||
    value.match(/^严格 JSON 错误：([\s\S]+?)（第 (\d+) 行，第 (\d+) 列，路径 ([\s\S]*)）。$/);
  if (strict) return t('Strict JSON error: {reason} at line {line}, column {column}, path {path}.', {
    reason:translateSystemText(strict[1]), line:strict[2], column:strict[3], path:strict[4],
  });
  const mappingMessage = 'Explicit mapping failed; inspect file, table and field locations.';
  if (value.startsWith(mappingMessage + ': ')) {
    // This is the application's serialized MappingError envelope. The prefix
    // and final reason are authored; file/table/row/field locations stay intact.
    const entries = value.slice(mappingMessage.length + 2).split(/; (?=[^;]* \/ )/);
    const translated = entries.map(entry => {
      const cut = entry.lastIndexOf(' / ');
      return cut < 0 ? entry : entry.slice(0, cut + 3) + translateSystemText(entry.slice(cut + 3));
    });
    return t(mappingMessage) + ': ' + translated.join('; ');
  }
  if (value.includes('\n')) return value.split('\n').map(translateSystemText).join('\n');
  for (const [pattern, format] of systemPatterns) {
    const match = value.match(pattern);
    if (match) return format(match);
  }
  return value;
}
