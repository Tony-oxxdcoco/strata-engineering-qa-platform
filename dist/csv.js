import { validateInput } from './engine.js';
import { getSample } from './samples.js';

export const CSV_COLUMNS = Object.freeze([
  'record_type', 'id', 'floor_id', 'case_id', 'support_id', 'value', 'unit',
  'evidence_ref', 'title', 'locator', 'content',
]);
export const CSV_MAX_BYTES = 1024 * 1024;
export const CSV_MAX_ROWS = 5000;

const UNIT_MAP = {
  area: { m2: 1, 'm²': 1 },
  force: { kN: 1, N: 0.001 },
  surfaceLoad: { 'kN/m2': 1, 'kN/m²': 1, kPa: 1, 'N/m2': 0.001, 'N/m²': 0.001 },
};
const CANONICAL_UNITS = { area: 'm2', surfaceLoad: 'kN/m2', force: 'kN' };
const NUMERIC_RECORDS = {
  floor: { list: 'floors', field: 'area', dimension: 'area', fields: ['evidence_ref'] },
  requirement: { list: 'requirements', field: 'q', dimension: 'surfaceLoad', fields: ['floor_id', 'case_id', 'evidence_ref'] },
  assignment: { list: 'assignments', field: 'force', dimension: 'force', fields: ['floor_id', 'case_id', 'evidence_ref'] },
  reaction: { list: 'reactions', field: 'fz', dimension: 'force', fields: ['support_id', 'case_id', 'evidence_ref'] },
};
const SCHEMA_NAMES = { floor_id: 'floorId', case_id: 'caseId', support_id: 'supportId', evidence_ref: 'evidenceRef' };
const owns = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

export class ControlledCsvError extends Error {
  constructor(message, { row = 1, column = 1, columnName = 'record_type', code = 'CSV_INVALID' } = {}) {
    super(`CSV 第 ${row} 行，第 ${column} 列（${columnName}）：${message}`);
    this.name = 'ControlledCsvError';
    this.row = row;
    this.column = column;
    this.columnName = columnName;
    this.code = code;
  }
}

// A state machine keeps quoted commas, escaped quotes and physical line numbers.
function readRows(text) {
  const rows = [];
  let cells = [], cell = '', quoted = false, closed = false;
  let line = 1, startLine = 1;
  const fail = message => {
    throw new ControlledCsvError(message, { row: line, column: cells.length + 1, columnName: rows[0]?.cells[cells.length] || CSV_COLUMNS[cells.length] || 'extra', code: 'CSV_SYNTAX' });
  };
  const finishCell = () => { cells.push(cell); cell = ''; closed = false; };
  const finishRow = () => {
    finishCell();
    if (!(cells.length === 1 && cells[0] === '')) rows.push({ cells, row: startLine });
    cells = [];
    if (rows.length > CSV_MAX_ROWS + 1) throw new ControlledCsvError(`最多允许 ${CSV_MAX_ROWS} 条数据记录。`, { row: startLine, code: 'CSV_LIMIT' });
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const newline = ch === '\r' || ch === '\n';
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; }
        else { quoted = false; closed = true; }
      } else {
        cell += ch;
        if (newline) {
          if (ch === '\r' && text[i + 1] === '\n') { cell += '\n'; i++; }
          line++;
        }
      }
    } else if (ch === ',') {
      finishCell();
    } else if (newline) {
      finishRow();
      if (ch === '\r' && text[i + 1] === '\n') i++;
      line++;
      startLine = line;
    } else if (closed) {
      fail('闭合引号后只能出现逗号或换行。');
    } else if (ch === '"') {
      if (cell !== '') fail('引号必须从字段开头开始；字段中的引号应写为两个双引号。');
      quoted = true;
    } else {
      cell += ch;
    }
  }
  if (quoted) fail('带引号的字段没有闭合。');
  if (cell !== '' || cells.length || closed) finishRow();
  return { rows, endLine: line };
}

/** Parse the explicitly synthetic Strata CSV contract; never infer engineering data. */
export function parseControlledCsv(text, { filename = 'import.csv' } = {}) {
  if (typeof text !== 'string') throw new ControlledCsvError('输入必须为 CSV 文本。');
  if (new TextEncoder().encode(text).byteLength > CSV_MAX_BYTES) throw new ControlledCsvError('文件超过 1 MiB 上限。', { code: 'CSV_LIMIT' });
  if (typeof filename !== 'string' || !filename.trim() || filename.length > 2000) throw new ControlledCsvError('filename 必须为非空文件名，且不超过 2000 字符。');
  const { rows, endLine } = readRows(text.replace(/^\uFEFF/, ''));
  if (!rows.length) throw new ControlledCsvError('缺少 CSV 表头。');
  const header = rows.shift();
  const columns = new Map();
  for (const [index, name] of header.cells.entries()) {
    const location = { row: header.row, column: index + 1, columnName: name || 'header', code: 'CSV_HEADER' };
    if (columns.has(name)) throw new ControlledCsvError(`重复的列名 ${name}。`, location);
    if (!CSV_COLUMNS.includes(name)) throw new ControlledCsvError(`不支持的列名 ${name || '(空)'}。`, location);
    columns.set(name, index);
  }
  for (const name of CSV_COLUMNS) if (!columns.has(name)) throw new ControlledCsvError(`缺少列 ${name}。`, { row: header.row, column: header.cells.length + 1, columnName: name, code: 'CSV_HEADER' });

  const result = {
    project: {}, units: {}, scope: {}, floors: [], requirements: [], assignments: [], supports: [], reactions: [], evidence: [],
    importMetadata: { format: 'strata-controlled-csv', version: '1.0', filename, declaredUnits: {}, rows: [] },
  };
  const seen = new Map();
  const sourceByTarget = new Map();
  const error = (row, name, message, code = 'CSV_VALUE') => {
    throw new ControlledCsvError(message, { row, column: (columns.get(name) ?? 0) + 1, columnName: name, code });
  };
  const unique = (type, id, row) => {
    const key = `${type}:${id}`;
    if (seen.has(key)) error(row, 'id', `重复的 ${type} / ${id}；首次出现于第 ${seen.get(key)} 行。`, 'CSV_DUPLICATE');
    seen.set(key, row);
  };
  const factorFor = (dimension, unit, row) => {
    if (!owns(UNIT_MAP[dimension], unit)) error(row, 'unit', `${dimension} 不支持单位 ${unit || '(空)'}。`);
    return UNIT_MAP[dimension][unit];
  };
  for (const source of rows) {
    if (source.cells.length !== CSV_COLUMNS.length) {
      const column = Math.min(source.cells.length, CSV_COLUMNS.length) + 1;
      throw new ControlledCsvError(`本行需要 ${CSV_COLUMNS.length} 列，实际为 ${source.cells.length} 列。`, { row: source.row, column, columnName: header.cells[column - 1] || 'extra', code: 'CSV_SYNTAX' });
    }
    const row = Object.fromEntries([...columns].map(([name, index]) => [name, source.cells[index]]));
    const required = name => {
      const value = row[name];
      if (!value.trim()) error(source.row, name, '必填字段不能为空。');
      if (value.length > 2000) error(source.row, name, '字段超过 2000 字符。');
      return value;
    };
    const type = required('record_type');
    const id = required('id');
    const allow = fields => {
      const allowed = new Set(['record_type', 'id', ...fields]);
      for (const name of CSV_COLUMNS) if (!allowed.has(name) && row[name] !== '') error(source.row, name, `${type} 记录不接受此字段；请留空。`);
    };
    let target;
    let numeric;
    if (owns(NUMERIC_RECORDS, type)) {
      const spec = NUMERIC_RECORDS[type];
      allow(['value', 'unit', ...spec.fields]);
      const raw = required('value');
      const valueText = raw.trim();
      if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(valueText)) error(source.row, 'value', '需要十进制有限数值；不接受空值、千位逗号、NaN 或 Infinity。');
      const original = Number(valueText);
      if (!Number.isFinite(original) || original < 0 || (spec.field === 'area' && original <= 0)) error(source.row, 'value', spec.field === 'area' ? '面积必须为有限正数。' : '数值必须为有限非负数。');
      if (original === 0 && /[1-9]/.test(valueText.split(/[eE]/)[0])) error(source.row, 'value', '数值过小，转换会丢失为零。');
      const unit = required('unit');
      const normalized = original * factorFor(spec.dimension, unit, source.row);
      if (!Number.isFinite(normalized) || (original !== 0 && normalized === 0)) error(source.row, 'value', '单位换算产生数值溢出或下溢。');
      const record = { id, [spec.field]: normalized };
      for (const name of spec.fields) record[SCHEMA_NAMES[name]] = required(name);
      if (type === 'floor') unique(type, id, source.row);
      target = `${spec.list}[${result[spec.list].length}]`;
      result[spec.list].push(record);
      if (result[spec.list].length > 1000) error(source.row, 'record_type', `${spec.list} 最多 1000 项。`, 'CSV_LIMIT');
      numeric = { field: spec.field, originalValue: raw, originalUnit: unit, normalizedValue: normalized, normalizedUnit: CANONICAL_UNITS[spec.dimension] };
    } else if (type === 'metadata') {
      allow(['value']);
      unique(type, id, source.row);
      const value = required('value');
      if (id === 'schemaVersion') {
        if (value !== '1.0') error(source.row, 'value', 'schemaVersion 必须为 1.0。');
        result.schemaVersion = value;
      } else if (id === 'synthetic') {
        if (value !== 'true') error(source.row, 'value', '受控 CSV 演示必须明确声明 synthetic 为 true；不接受真实工程数据标记。');
        result.synthetic = true;
      } else error(source.row, 'id', `不支持 metadata 字段 ${id}。`);
      target = id;
    } else if (type === 'project' || type === 'scope') {
      allow(['value']);
      const keys = type === 'project' ? ['name', 'revision', 'description', 'software'] : ['basis', 'selfWeight', 'reactionPositive'];
      if (!keys.includes(id)) error(source.row, 'id', `不支持 ${type} 字段 ${id}。`);
      unique(type, id, source.row);
      result[type][id] = required('value');
      target = `${type}.${id}`;
    } else if (type === 'units') {
      allow(['unit']);
      if (!owns(UNIT_MAP, id)) error(source.row, 'id', `不支持单位类别 ${id}。`);
      unique(type, id, source.row);
      const unit = required('unit');
      factorFor(id, unit, source.row);
      result.units[id] = CANONICAL_UNITS[id];
      result.importMetadata.declaredUnits[id] = unit;
      target = `units.${id}`;
    } else if (type === 'support') {
      allow([]);
      unique(type, id, source.row);
      target = `supports[${result.supports.length}]`;
      result.supports.push(id);
      if (result.supports.length > 1000) error(source.row, 'record_type', 'supports 最多 1000 项。', 'CSV_LIMIT');
    } else if (type === 'evidence') {
      allow(['title', 'locator', 'content']);
      unique(type, id, source.row);
      target = `evidence[${result.evidence.length}]`;
      result.evidence.push({ id, title: required('title'), locator: row.locator, content: row.content });
      if (result.evidence.length > 1000) error(source.row, 'record_type', 'evidence 最多 1000 项。', 'CSV_LIMIT');
    } else error(source.row, 'record_type', `不支持记录类型 ${type}。`);
    const provenance = { row: source.row, recordType: type, recordId: id, target, ...numeric };
    result.importMetadata.rows.push(provenance);
    sourceByTarget.set(target, provenance);
  }

  for (const [type, id] of [['metadata', 'schemaVersion'], ['metadata', 'synthetic'], ['project', 'name'], ...['basis', 'selfWeight', 'reactionPositive'].map(id => ['scope', id]), ...Object.keys(CANONICAL_UNITS).map(id => ['units', id])]) {
    if (!seen.has(`${type}:${id}`)) error(endLine, 'id', `缺少必需记录 ${type} / ${id}。`, 'CSV_MISSING_RECORD');
  }
  if (!result.floors.length) error(endLine, 'record_type', '至少需要一条 floor 记录。', 'CSV_MISSING_RECORD');
  // Surface aggregate overflow at the input row responsible, before schema validation.
  const floors = new Map(result.floors.map(f => [f.id, f.area]));
  for (const list of ['requirements', 'assignments', 'reactions']) {
    let total = 0;
    result[list].forEach((record, index) => {
      const value = list === 'requirements' ? (floors.has(record.floorId) ? floors.get(record.floorId) * record.q : 0) : list === 'assignments' ? record.force : record.fz;
      total += value;
      if (!Number.isFinite(value) || !Number.isFinite(total)) error(sourceByTarget.get(`${list}[${index}]`).row, 'value', '工程数值乘积或累计值溢出，无法可靠核验。');
    });
  }
  return validateInput(result);
}

/** Downloadable controlled example, independent from any native ETABS export format. */
export function controlledCsvTemplate() {
  const sample = getSample('clean');
  const rows = [];
  const add = row => rows.push(CSV_COLUMNS.map(name => String(row[name] ?? '')));
  add({ record_type: 'metadata', id: 'schemaVersion', value: sample.schemaVersion });
  add({ record_type: 'metadata', id: 'synthetic', value: sample.synthetic });
  for (const [id, value] of Object.entries(sample.project)) add({ record_type: 'project', id, value });
  for (const [id, value] of Object.entries(sample.scope)) add({ record_type: 'scope', id, value });
  for (const [id, unit] of Object.entries(sample.units)) add({ record_type: 'units', id, unit });
  for (const [type, spec] of Object.entries(NUMERIC_RECORDS)) for (const record of sample[spec.list]) {
    const row = { record_type: type, id: record.id, value: record[spec.field], unit: sample.units[spec.dimension] };
    for (const name of spec.fields) row[name] = record[SCHEMA_NAMES[name]];
    add(row);
  }
  for (const id of sample.supports) add({ record_type: 'support', id });
  for (const record of sample.evidence) add({ record_type: 'evidence', ...record });
  const escape = value => /[,"\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
  return [CSV_COLUMNS, ...rows].map(row => row.map(escape).join(',')).join('\r\n') + '\r\n';
}
