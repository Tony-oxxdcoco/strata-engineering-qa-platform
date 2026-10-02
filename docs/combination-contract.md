# Synthetic linear-static combination contract

This independent Sprint 1 module implements W18ICAKE-8's basic controlled-case check. It compares a separately supplied combination response against a linear sum of independently supplied base-case responses. It does **not** verify structural capacity, design adequacy, AS 1170 factors, complete load-combination coverage, or any real client model. It does not connect to ETABS/SAFE or an LLM. The existing gravity-check engine and its history are separate.

## Input

```json
{
  "schemaVersion": "combination-1.0",
  "synthetic": true,
  "project": {"name": "Synthetic linear response fixture", "revision": "COMB-R01"},
  "analysisType": "linear-static",
  "unit": "kN",
  "baseCases": [
    {"id": "SDL", "value": 100, "evidenceRef": "reference-responses"},
    {"id": "LIVE", "value": 50, "evidenceRef": "reference-responses"}
  ],
  "combinations": [
    {
      "id": "C1",
      "terms": [{"caseId": "SDL", "factor": 1.2}, {"caseId": "LIVE", "factor": 1.5}],
      "reportedValue": 195,
      "evidenceRef": "reported-combinations"
    }
  ],
  "evidence": [
    {"id": "reference-responses", "title": "Independent synthetic reference", "locator": "Fixture reference sheet", "content": "SDL = 100 kN; LIVE = 50 kN."},
    {"id": "reported-combinations", "title": "Separate synthetic export", "locator": "Fixture export, C1", "content": "C1 = 195 kN; synthetic factors 1.2 and 1.5."}
  ]
}
```

All response values must represent the same scalar response component, location, sign convention, revision and unit. That engineering alignment is a fixture-author responsibility; this schema cannot authenticate it. Signed values and signed or zero factors are allowed for linear-static responses. The chosen example factors are synthetic, not a claimed standard requirement.

Arrays are limited to 1000 entries each. IDs must be nonempty, trimmed strings of at most 160 characters. Project name/revision and analysis/unit declarations are required. Values and factors must be finite JSON numbers: numeric strings, null, NaN and infinity are rejected. Base and combination ID namespaces must be distinct. Duplicate base, combination or evidence IDs and repeated case IDs within a combination are rejected; nothing is silently de-duplicated. JSON data must not contain cycles, undefined properties or sparse arrays.

Referenced evidence requires a nonempty title, locator and content. A reported response must not use the same evidence ID as its base references. This enforces declared separation, **not authenticity or real-world independence**. Evidence prose is displayed and preserved; it is not parsed to regenerate the reported values. The caller supplies base values, factors and reported values independently. Missing reference IDs/records or blank evidence yield NOT VERIFIED for the affected combination. Invalid containers and invalid numeric fields throw an input-validation error before any checking result is produced.

## Calculation and status

For each combination:

```text
expected = Σ(factor × independent base response)
tolerance = max(1 kN, 0.01 × abs(expected))
PASS iff expected − tolerance ≤ reportedValue ≤ expected + tolerance
```

The closed interval includes both tolerance endpoints; no user-supplied tolerance overrides this fixed rule. Summation uses compensation to retain small signed contributions during cancellation. Non-finite products, intermediate sums, corrections or comparison differences produce NOT VERIFIED. Underflow of a nonzero product to zero also produces NOT VERIFIED. Overflowing intermediate sums are blocked even if later terms could cancel them. These are bounded floating-point demo calculations, not arbitrary-precision engineering arithmetic.

- **PASS:** complete, unambiguous, evidenced synthetic linear-static input and a reported value within tolerance.
- **FAIL:** those prerequisites hold, but the independently supplied reported value lies outside tolerance.
- **NOT VERIFIED:** a prerequisite is missing, scope/unit/analysis is unsupported, no terms exist, or arithmetic cannot be evaluated reliably. Unknown and nested combination references are not evaluated. Even a zero-factor term requires its declared base case and evidence.

Nonlinear, envelope and nested-combination checking are not implemented. `synthetic: false`, unsupported units and unsupported analysis types produce NOT VERIFIED; there is no silent conversion or fallback. No combinations produce an explicit `COMB-INPUT` NOT VERIFIED result instead of a vacuous PASS. Aggregate precedence is FAIL, then NOT VERIFIED, then PASS, preserving a confirmed mismatch even if another combination could not be checked.

## Exports

- `COMBINATION_VERSION`: implementation/rule version for replay checks.
- `COMBINATION_SCENARIOS`: `{id,title,note}` records with IDs `clean`, `mismatch`, `missing`, `unsupported`.
- `getCombinationSample(id = 'clean')`: fresh sample input; rejects an unknown ID.
- `validateCombinationInput(input)`: returns the original input after structural validation; does not mutate it. Throws on malformed or ambiguous inputs as described above.
- `runCombinationChecks(input)`: `{version,status,summary:{PASS,FAIL,'NOT VERIFIED'},results}`. Each supplied combination gets one result `{id,name,status,summary,details}` with one detail `{label,expected,actual,unit,formula,tolerance,reason,location,evidenceRefs}`. Unavailable expected values/tolerances are `null`. Formula text includes symbolic terms and substituted numeric terms. Details preserve the declared input unit even when unsupported, so a raw response in N is never relabelled as kN. Unsupported units produce NOT VERIFIED with no expected value or tolerance.
- `await createCombinationRun(input)`: validates, takes an independent JSON snapshot, computes findings and returns them with `{id,createdAt,inputHash,input,reviews:[]}`. `inputHash` is SHA-256 of `JSON.stringify(inputSnapshot)`; key order is significant and JSON normalises negative zero to zero. Browser Web Crypto or Node.js 20+ is required.
- `await combinationReport(run)`: snapshots once, replays every technical field, verifies the input hash and checks review metadata before generating Markdown. Any inconsistent input, result or version is rejected. The report includes all formulas, source records, the complete input snapshot, human notes and synthetic limitations. Await it before downloading. Existing gravity runs are not accepted.

The app may append review records `{at,reviewer,note,disposition}`. `at` must parse as a date; reviewer and note must be nonempty text. Disposition is `reviewed` or `request_evidence`. Reviews never modify technical results. An unreviewed report is labelled DRAFT; a reviewed report is explicitly not engineering approval. Hash/replay checks detect inconsistent stored data; they are not digital signatures, authenticated reviewer identities or tamper-proof shared audit storage.

## Independent sample truth and validation

The four files `dist/examples/combination-*.json` contain separately written input values, not results generated by the checker:

| Scenario | Hand calculation | Supplied reported values | Expected statuses |
| --- | --- | --- | --- |
| clean | C1: 1.2 × 100 + 1.5 × 50 = 120 + 75 = 195; C2: 100 − 50 = 50 | 195, 50 | PASS, PASS |
| mismatch | Same independent reference values and factors | 210, 50 | FAIL, PASS |
| missing | LIVE base record missing | 195, 50 | NOT VERIFIED, NOT VERIFIED |
| unsupported | Declared nonlinear analysis; linear sum is inapplicable | 195, 50 | NOT VERIFIED, NOT VERIFIED |

`node --test tests/combinations.test.mjs` checks these hand-derived outcomes, signed responses, cancellation, zero/tolerance boundaries, source separation, missing/duplicate/invalid data, overflow/underflow and replay-protected reports. These checks are software fixture tests. They do not establish engineering accuracy on client models or client acceptance.
