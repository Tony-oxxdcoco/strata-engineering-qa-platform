import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { CSV_COLUMNS, CSV_MAX_BYTES, CSV_MAX_ROWS, ControlledCsvError, controlledCsvTemplate, parseControlledCsv } from '../dist/csv.js';
import { getSample } from '../dist/samples.js';
import { runChecks } from '../dist/engine.js';

const field = name => CSV_COLUMNS.indexOf(name);
// The clean fixture has no embedded newlines; its quoted comma is decoded here.
// Multiline test values are added to this matrix and encoded independently below.
const templateRows = () => controlledCsvTemplate().trimEnd().split('\r\n').map(line =>
  [...line.matchAll(/(?:^|,)(?:"((?:[^"]|"")*)"|([^,]*))/g)].map(match => match[1] === undefined ? match[2] : match[1].replaceAll('""', '"')));
const encode = rows => rows.map(row => row.map(value => {
  const text = String(value);
  return /[,"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}).join(',')).join('\r\n') + '\r\n';
const find = (rows, type, id) => rows.find(row => row[0] === type && row[1] === id);
const engineering = input => { const { importMetadata, ...data } = input; return data; };
const expectError = (csv, expected) => assert.throws(() => parseControlledCsv(csv), error => {
  assert.ok(error instanceof ControlledCsvError);
  for (const [key, value] of Object.entries(expected)) assert.equal(error[key], value, `${key}: ${error.message}`);
  assert.match(error.message, /CSV 第 \d+ 行，第 \d+ 列/);
  return true;
});

test('downloadable CSV round-trips all clean engineering fields and passes six rules', async () => {
  const parsed = parseControlledCsv(controlledCsvTemplate(), { filename: 'controlled-template.csv' });
  assert.deepEqual(engineering(parsed), getSample('clean'));
  assert.deepEqual(runChecks(parsed).summary, { PASS: 6, FAIL: 0, 'NOT VERIFIED': 0 });
  assert.equal(parsed.importMetadata.filename, 'controlled-template.csv');
  assert.equal(parsed.importMetadata.format, 'strata-controlled-csv');
  assert.equal(parsed.importMetadata.rows.length, templateRows().length - 1);
  assert.equal(await readFile(new URL('../dist/examples/controlled-template.csv', import.meta.url), 'utf8'), controlledCsvTemplate());
});

test('explicit N, N/m², kPa and m² inputs convert to existing canonical units with provenance', () => {
  const rows = templateRows();
  find(rows, 'units', 'force')[field('unit')] = 'N';
  find(rows, 'units', 'surfaceLoad')[field('unit')] = 'kPa';
  find(rows, 'units', 'area')[field('unit')] = 'm²';
  for (const row of rows.slice(1)) {
    if (['assignment', 'reaction', 'requirement'].includes(row[0])) {
      row[field('value')] = String(Number(row[field('value')]) * 1000);
      row[field('unit')] = row[0] === 'requirement' ? 'N/m²' : 'N';
    }
    if (row[0] === 'floor') row[field('unit')] = 'm²';
  }
  find(rows, 'requirement', 'B1')[field('value')] = '5';
  find(rows, 'requirement', 'B1')[field('unit')] = 'kPa';
  const parsed = parseControlledCsv(encode(rows));
  assert.deepEqual(engineering(parsed), getSample('clean'));
  assert.deepEqual(parsed.importMetadata.declaredUnits, { area: 'm²', surfaceLoad: 'kPa', force: 'N' });
  const row = rows.indexOf(find(rows, 'assignment', 'A1')) + 1;
  assert.deepEqual(parsed.importMetadata.rows.find(entry => entry.target === 'assignments[0]'), {
    row, recordType: 'assignment', recordId: 'A1', target: 'assignments[0]', field: 'force',
    originalValue: '3000000', originalUnit: 'N', normalizedValue: 3000, normalizedUnit: 'kN',
  });
});

test('unknown units, including Object prototype names, fail at the exact unit cell', () => {
  for (const unit of ['lb', 'Pa', 'KN', 'toString']) {
    const rows = templateRows(), target = find(rows, 'assignment', 'A1');
    target[field('unit')] = unit;
    expectError(encode(rows), { row: rows.indexOf(target) + 1, column: 7, columnName: 'unit' });
  }
});

test('missing and invalid numbers never become a zero or guessed value', () => {
  for (const value of ['', ' ', 'NaN', 'Infinity', '1e309', '-1', '0x10', '1,000', '1e-400']) {
    const rows = templateRows(), target = find(rows, 'assignment', 'A1');
    target[field('value')] = value;
    expectError(encode(rows), { row: rows.indexOf(target) + 1, column: 6, columnName: 'value' });
  }
});

test('empty row units and nonpositive areas reject; numeric zero remains valid for forces', () => {
  const rows = templateRows(), target = find(rows, 'floor', 'L01');
  target[field('value')] = '0';
  expectError(encode(rows), { row: rows.indexOf(target) + 1, columnName: 'value' });
  target[field('value')] = '600';
  target[field('unit')] = '';
  expectError(encode(rows), { row: rows.indexOf(target) + 1, columnName: 'unit' });
  target[field('unit')] = 'm2';
  find(rows, 'assignment', 'A1')[field('value')] = '0';
  assert.equal(parseControlledCsv(encode(rows)).assignments[0].force, 0);
});

test('BOM, CRLF and LF files preserve engineering data', () => {
  for (const csv of ['\uFEFF' + controlledCsvTemplate(), controlledCsvTemplate().replaceAll('\r\n', '\n')]) {
    assert.deepEqual(engineering(parseControlledCsv(csv)), getSample('clean'));
  }
});

test('quoted commas, doubled quotes and embedded CRLF preserve text and physical row provenance', () => {
  const rows = templateRows();
  const content = 'First, "quoted" source\r\nSecond line';
  find(rows, 'project', 'description')[field('value')] = content;
  const parsed = parseControlledCsv(encode(rows));
  assert.equal(parsed.project.description, content);
  const target = find(rows, 'assignment', 'A1');
  assert.equal(parsed.importMetadata.rows.find(entry => entry.target === 'assignments[0]').row, rows.indexOf(target) + 2);
  target[field('unit')] = 'unknown';
  expectError(encode(rows), { row: rows.indexOf(target) + 2, columnName: 'unit' });
});

test('unclosed quotes, quotes inside unquoted fields and characters after closing quotes reject', () => {
  const header = CSV_COLUMNS.join(',') + '\n';
  for (const suffix of ['metadata,"schemaVersion', 'metadata,schema"Version,', 'metadata,"schemaVersion"x,']) {
    expectError(header + suffix, { row: 2, column: 2, code: 'CSV_SYNTAX' });
  }
});

test('header duplicates, missing columns, unknown columns and malformed row lengths reject', () => {
  const rows = templateRows();
  rows[0][2] = 'id';
  expectError(encode(rows), { row: 1, column: 3, code: 'CSV_HEADER' });
  rows[0] = CSV_COLUMNS.slice(0, -1);
  expectError(encode(rows), { row: 1, columnName: 'content', code: 'CSV_HEADER' });
  rows[0] = [...CSV_COLUMNS, 'extra'];
  expectError(encode(rows), { row: 1, column: 12, code: 'CSV_HEADER' });
  rows[0] = [...CSV_COLUMNS];
  rows[1].pop();
  expectError(encode(rows), { row: 2, column: 11, columnName: 'content', code: 'CSV_SYNTAX' });
  rows[1].push('', '');
  expectError(encode(rows), { row: 2, column: 12, columnName: 'extra', code: 'CSV_SYNTAX' });
});

test('header column order may change and errors use the supplied order', () => {
  const rows = templateRows().map(row => [...row].reverse());
  assert.deepEqual(engineering(parseControlledCsv(encode(rows))), getSample('clean'));
  const target = rows.find(row => row.at(-1) === 'assignment');
  target[4] = 'lb';
  expectError(encode(rows), { row: rows.indexOf(target) + 1, column: 5, columnName: 'unit' });
});

test('explicit schema, synthetic marker, project, scope and units records are required', () => {
  for (const [type, id] of [['metadata', 'schemaVersion'], ['metadata', 'synthetic'], ['project', 'name'], ['scope', 'basis'], ['units', 'force']]) {
    const rows = templateRows().filter(row => !(row[0] === type && row[1] === id));
    expectError(encode(rows), { code: 'CSV_MISSING_RECORD', columnName: 'id' });
  }
  const rows = templateRows(), target = find(rows, 'metadata', 'synthetic');
  target[field('value')] = 'false';
  expectError(encode(rows), { row: rows.indexOf(target) + 1, columnName: 'value' });
});

test('duplicate engineering records are retained so QA-001 fails without silent deduplication', () => {
  for (const [type, id, list] of [['requirement', 'B1', 'requirements'], ['assignment', 'A1', 'assignments'], ['reaction', 'R1', 'reactions']]) {
    const rows = templateRows();
    rows.push([...find(rows, type, id)]);
    const parsed = parseControlledCsv(encode(rows));
    assert.equal(parsed[list].length, getSample('clean')[list].length + 1);
    assert.equal(runChecks(parsed).results.find(result => result.id === 'QA-001').status, 'FAIL');
    assert.equal(parsed.importMetadata.rows.at(-1).row, rows.length);
  }
});

test('ambiguous duplicate floor, support and evidence identifiers get located schema errors', () => {
  for (const [type, id] of [['floor', 'L01'], ['support', 'C1'], ['evidence', 'design-brief']]) {
    const rows = templateRows();
    rows.push([...find(rows, type, id)]);
    expectError(encode(rows), { row: rows.length, columnName: 'id', code: 'CSV_DUPLICATE' });
  }
});

test('absent or empty evidence is retained as missing rather than fabricated', () => {
  for (const emptyOnly of [false, true]) {
    let rows = templateRows();
    if (emptyOnly) find(rows, 'evidence', 'reaction-export')[field('content')] = '';
    else rows = rows.filter(row => !(row[0] === 'evidence' && row[1] === 'reaction-export'));
    const parsed = parseControlledCsv(encode(rows));
    assert.equal(runChecks(parsed).results.find(result => result.id === 'QA-005').status, 'NOT VERIFIED');
  }
});

test('changed baseline does not regenerate independent reaction results or expected values', () => {
  const rows = templateRows();
  find(rows, 'requirement', 'B1')[field('value')] = '7';
  const parsed = parseControlledCsv(encode(rows));
  assert.equal(parsed.requirements[0].q, 7);
  assert.equal(parsed.reactions[0].fz, 2000);
  assert.equal(parsed.assignments[0].force, 3000);
  assert.equal(runChecks(parsed).results.find(result => result.id === 'QA-005').status, 'FAIL');
});

test('unsupported scope reaches the engine as NOT VERIFIED', () => {
  const rows = templateRows();
  find(rows, 'scope', 'basis')[field('value')] = 'factored-combination';
  const parsed = parseControlledCsv(encode(rows));
  assert.equal(parsed.scope.basis, 'factored-combination');
  assert.equal(runChecks(parsed).results.find(result => result.id === 'QA-003').status, 'NOT VERIFIED');
});

test('multiplication and aggregate overflow identify the responsible engineering row', () => {
  const rows = templateRows();
  find(rows, 'floor', 'L01')[field('value')] = '6e307';
  expectError(encode(rows), { row: rows.indexOf(find(rows, 'requirement', 'B1')) + 1, columnName: 'value' });
});

test('byte, total-record and per-collection limits are bounded', () => {
  expectError('x'.repeat(CSV_MAX_BYTES + 1), { code: 'CSV_LIMIT' });
  expectError('界'.repeat(Math.floor(CSV_MAX_BYTES / 3) + 1), { code: 'CSV_LIMIT' });
  expectError(CSV_COLUMNS.join(',') + '\n' + 'support,C1,,,,,,,,,\n'.repeat(CSV_MAX_ROWS + 1), { code: 'CSV_LIMIT' });
  const rows = templateRows(), extra = find(rows, 'assignment', 'A1');
  rows.push(...Array.from({ length: 995 }, () => [...extra]));
  expectError(encode(rows), { code: 'CSV_LIMIT', columnName: 'record_type' });
});

test('unknown record types or populated inapplicable columns cannot silently disappear', () => {
  const rows = templateRows();
  find(rows, 'assignment', 'A1')[field('title')] = 'misplaced value';
  expectError(encode(rows), { columnName: 'title' });
  find(rows, 'assignment', 'A1')[0] = 'native-etabs';
  expectError(encode(rows), { columnName: 'record_type' });
});
