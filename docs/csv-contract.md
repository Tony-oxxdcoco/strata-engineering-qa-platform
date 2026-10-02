# Controlled CSV input contract

This is a Strata synthetic demonstration format, **not a native ETABS or SAFE export**. It feeds the same schema `1.0` and deterministic checks as the JSON examples. It does not call a solver, infer missing fields, generate reaction results or verify the authenticity of a source document.

## UI interface

```js
import { parseControlledCsv, controlledCsvTemplate, ControlledCsvError } from './csv.js';

// The caller checks the selected File size before reading, then passes its text.
const input = parseControlledCsv(await file.text(), { filename: file.name });
// Pass input to the existing createRun(input) / runChecks(input).
const templateText = controlledCsvTemplate(); // UTF-8, CRLF, downloadable text/csv
```

`parseControlledCsv` returns a validated input object, including `importMetadata`. It throws `ControlledCsvError` with a readable `message`, one-based physical `row`, one-based CSV field `column`, `columnName`, and `code`. Codes are `CSV_INVALID`, `CSV_SYNTAX`, `CSV_HEADER`, `CSV_VALUE`, `CSV_LIMIT`, `CSV_DUPLICATE` and `CSV_MISSING_RECORD`. A missing record is reported at the end of the file. Render messages and imported fields as text, never HTML.

The module has no network or storage side effects and uses no third-party packages. It imports the existing engine validator and sample generator. Import provenance becomes part of the input snapshot when the caller creates a run; the existing run hash therefore includes it.

## Header and records

All eleven column names must appear exactly once. Their order may change. Names and units are case-sensitive; unexpected columns and nonempty inapplicable cells are errors.

```csv
record_type,id,floor_id,case_id,support_id,value,unit,evidence_ref,title,locator,content
```

| record_type | Required cells | Meaning |
| --- | --- | --- |
| metadata | id, value | Exactly `schemaVersion,1.0` and `synthetic,true`. CSV imports support synthetic examples only. |
| project | id, value | `name` is required. `revision`, `description`, `software` are optional and preserved when supplied. |
| scope | id, value | Required IDs: `basis`, `selfWeight`, `reactionPositive`. Values are retained for the engine to assess. |
| units | id, unit | Required IDs: `area`, `surfaceLoad`, `force`. Declared source units must be supported. |
| floor | id, value, unit, evidence_ref | `value` is floor area; strictly positive. |
| requirement | id, floor_id, case_id, value, unit, evidence_ref | `value` is independently supplied required surface load `q`. |
| assignment | id, floor_id, case_id, value, unit, evidence_ref | `value` is assigned total floor force. |
| support | id | Independently supplied support ID. |
| reaction | id, support_id, case_id, value, unit, evidence_ref | `value` is independently supplied vertical reaction `fz`. |
| evidence | id, title | `locator` and `content` contain supplied source information. Empty text is retained and fails the engine's evidence gate. |

Every row also needs `record_type`. A floor is required. Other engineering lists can be empty so the engine can report incomplete coverage. `value` is a finite nonnegative decimal number, with scientific notation allowed; no thousands separator, hex, `NaN`, infinity or conversion to zero through underflow. Conversion uses JavaScript finite-precision numbers. Identifiers and required text cells are limited to 2,000 characters.

The demonstrated engine scope is `basis=unfactored-static-gravity`, `selfWeight=excluded`, `reactionPositive=upward`. Other explicit scope values are retained and block relevant numerical verification. This import does not add support for load combinations or arbitrary load cases.

## Units and evidence

| Dimension | Accepted unit spellings | Engine unit / conversion |
| --- | --- | --- |
| Area | `m2`, `m²` | `m2`; unchanged |
| Force | `kN`, `N` | `kN`; divide N by 1,000 |
| Surface load | `kN/m2`, `kN/m²`, `kPa`, `N/m2`, `N/m²` | `kN/m2`; divide N/m2 by 1,000; others unchanged |

Each numeric row **must declare its own unit**, even when it matches the file's units record. Mixed supported units are allowed within a dimension. The units records document the source declaration; they never fill missing row units or override an explicit row unit. Unknown units reject the import. The output `units` object always uses engine units.

The existing engine expects evidence IDs `design-brief`, `model-export`, `reaction-export`, `support-schedule`, and `review-note`. Floors and requirements reference `design-brief`; assignments reference `model-export`; reactions reference `reaction-export`. Import preserves these supplied references. Missing evidence rows, empty evidence content and dangling references are not filled in: the engine reports `NOT VERIFIED` where required.

Duplicate requirement, assignment and reaction rows are retained, including duplicate record IDs and duplicate engineering keys, so `QA-001` can return `FAIL`. Duplicate floor, support or evidence IDs are ambiguous under the existing input schema and reject the import with the offending CSV row. No records are silently deduplicated.

## Source provenance

```js
input.importMetadata = {
  format: 'strata-controlled-csv',
  version: '1.0',
  filename: 'example.csv',
  declaredUnits: { area: 'm2', surfaceLoad: 'kPa', force: 'N' },
  rows: [{
    row: 23, // starting physical line; quoted multiline text counts its lines
    recordType: 'assignment',
    recordId: 'A1',
    target: 'assignments[0]',
    field: 'force',
    originalValue: '3000000',
    originalUnit: 'N',
    normalizedValue: 3000,
    normalizedUnit: 'kN'
  }]
};
```

Every imported data record has row/type/ID/target provenance. Numeric rows also preserve the original textual number and unit, plus the normalized number and unit. Metadata is a trace of this CSV conversion, not independently authenticated engineering evidence.

## CSV syntax and limits

The parser supports a leading UTF-8 BOM, CRLF/LF line endings, quoted commas, doubled quotes (`""`) and embedded line breaks inside quoted fields. Quoted text is preserved. A quote inside an unquoted cell, a non-delimiter after a closing quote, an unterminated quote or a row with the wrong number of columns rejects the file. Blank lines are ignored; they still count toward physical row locations.

The encoded text may contain at most **1,048,576 UTF-8 bytes**, at most **5,000 data records**, and at most **1,000 records in each engineering list**. Aggregate or calculated-value overflow also rejects the input. The downloadable `dist/examples/controlled-template.csv` is generated by `controlledCsvTemplate()` and round-trips the existing clean fixture without changing engineering values or evidence.
