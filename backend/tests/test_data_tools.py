"""Boundary tests with only local in-memory documents and explicit synthetic rules."""
import copy
import csv
import datetime as dt
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strata.data_tools import (DataValidationError, MAX_FILE_BYTES, ingest,
    compare_snapshots, verify_handoff, verify_combination_configuration,
    verify_settings)

EXAMPLES = Path(__file__).resolve().parents[2] / "dist" / "examples"


def fixture(name="clean.json"):
    return json.loads((EXAMPLES / name).read_bytes())


def json_bytes(value):
    return json.dumps(value, allow_nan=False).encode()


def csv_rows():
    return list(csv.reader(io.StringIO((EXAMPLES / "controlled-template.csv").read_text())))


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerows(rows)
    return stream.getvalue().encode()


def workbook_bytes(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Settings"
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def pdf_bytes(texts, encrypted=False):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=100)
        if text is not None:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 20 60 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def manifest():
    return {"id": "handoff-1", "version": "1", "approved": True,
        "source_revision": "A", "target_revision": "B",
        "required_source_paths": ["/assignment/force"],
        "required_target_paths": ["/assignment/force"],
        "mappings": [{"id": "m1", "source_path": "/assignment/force", "target_path": "/assignment/force",
            "source_unit_path": "/units/force", "target_unit_path": "/units/force", "comparison_unit": "kN",
            "absolute_tolerance": 1, "relative_tolerance": 0.01}]}


def handoff_inputs(source_value=100, target_value=100000):
    return ({"project": {"revision": "A"}, "units": {"force": "kN"}, "assignment": {"force": source_value}},
            {"project": {"revision": "B"}, "units": {"force": "N"}, "assignment": {"force": target_value}})


def combination_inputs():
    data = fixture("combination-clean.json")
    data["configuration_complete"] = True
    rule = {"id": "config-1", "version": "1", "approved": True,
        "required_base_cases": ["SDL", "LIVE"],
        "required_combinations": [{"id": r["id"], "terms": copy.deepcopy(r["terms"])} for r in data["combinations"]],
        "allow_extra_base_cases": False, "allow_extra_combinations": False, "factor_tolerance": 0.0}
    return data, rule


def setting_rule(*settings):
    return {"id": "settings-1", "version": "1", "approved": True, "settings": list(settings)}


@pytest.mark.parametrize("name", ["clean.json", "combination-clean.json"])
def test_json_schema_and_hash_and_field_provenance(name):
    raw = (EXAMPLES / name).read_bytes()
    result = ingest(name, raw)
    assert result["status"] == "READY"
    assert result["snapshot"] == json.loads(raw)
    assert result["file"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert any(p["location"].get("json_pointer") == "/project/name" for p in result["provenance"])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("name,raw", [("../input.json", b"{}"), ("input.exe", b"{}"), ("input.json", b""),
    ("input.json", b"\xff"), ("input.json", b'{"value":NaN}'), ("input.json", b'{"value":1,"value":2}'),
    ("input.json", b'{"value":1e999}'), ("input.json", b'{"value":1e-999}'), ("input.json", b'{"value":"\\ud800"}'),
    ("input.json", b'{"\\ud800":1}'), ("input.json", b'\x00{}'), ("input.json", bytearray(b"{}")),
    ("input.json", b"x" * (MAX_FILE_BYTES + 1))], ids=[
    "path-traversal", "unsupported-extension", "empty-file", "invalid-utf8",
    "nan", "duplicate-key", "overflow", "underflow", "surrogate-value",
    "surrogate-key", "nul-byte", "non-bytes", "oversized-file"])
def test_invalid_files_rejected(name, raw):
    with pytest.raises(DataValidationError):
        ingest(name, raw)


@pytest.mark.parametrize("value", [True, None, "600", 0, -1])
def test_gravity_area_not_repaired(value):
    data = fixture()
    data["floors"][0]["area"] = value
    with pytest.raises(DataValidationError):
        ingest("input.json", json_bytes(data))


def test_finite_products_that_overflow_are_rejected():
    data = fixture()
    data["floors"][0]["area"] = 1e308
    data["requirements"][0]["q"] = 1e308
    with pytest.raises(DataValidationError, match="overflow"):
        ingest("input.json", json_bytes(data))


def test_non_engineering_json_is_only_a_source_document():
    raw = b'{"approved":true,"knowledge": "Untrusted upload"}'
    result = ingest("knowledge.json", raw)
    assert result["status"] == "NEEDS_MAPPING" and result["snapshot"] is None
    assert result["pages"][0]["text"] == raw.decode()
    with pytest.raises(DataValidationError):
        ingest("malformed-engineering.json", b'{"schemaVersion":"1.0"}')


@pytest.mark.parametrize("name", ["source.txt", "source.md"])
def test_utf8_source_documents_preserve_content(name):
    text = "# Source\n工程规则原文，不代表批准\n"
    result = ingest(name, text.encode())
    assert result["status"] == "READY" and result["snapshot"] is None
    assert result["pages"] == [{"page": 1, "text": text}]
    with pytest.raises(DataValidationError):
        ingest(name, b"\xff")


def test_csv_fixture_preserves_records_and_physical_line_and_original_units():
    rows = csv_rows()
    columns = {name: i for i, name in enumerate(rows[0])}
    assignment = next(row for row in rows if row[0] == "assignment")
    assignment[columns["value"]] = "3000000"
    assignment[columns["unit"]] = "N"
    evidence = next(row for row in rows if row[0] == "evidence")
    evidence[columns["content"]] = "First line\r\nSecond line"
    result = ingest("controlled.csv", csv_bytes(rows))
    assert result["status"] == "READY"
    assert result["snapshot"]["assignments"][0]["force"] == 3000
    provenance = next(p for p in result["provenance"] if p["recordType"] == "assignment")
    assert provenance["originalUnit"] == "N" and provenance["originalValue"] == "3000000"
    assert provenance["normalizedUnit"] == "kN"
    output_evidence = result["snapshot"]["evidence"]
    assert output_evidence[0]["content"] == "First line\r\nSecond line"
    evidence_rows = [p for p in result["provenance"] if p["recordType"] == "evidence"]
    assert evidence_rows[1]["row"] == evidence_rows[0]["row"] + 2


@pytest.mark.parametrize("mutation", ["duplicate-header", "unknown-row", "unknown-unit", "missing-number", "nan", "underflow", "unexpected-cell", "duplicate-floor"])
def test_csv_rejects_ambiguous_or_unsupported_data(mutation):
    rows = csv_rows()
    columns = {name: i for i, name in enumerate(rows[0])}
    row = next(row for row in rows if row[0] == "floor")
    if mutation == "duplicate-header": rows[0][-1] = rows[0][0]
    elif mutation == "unknown-row": row[0] = "native-etabs-table"
    elif mutation == "unknown-unit": row[columns["unit"]] = "feet"
    elif mutation == "missing-number": row[columns["value"]] = ""
    elif mutation == "nan": row[columns["value"]] = "NaN"
    elif mutation == "underflow": row[columns["value"]] = "1e-999"
    elif mutation == "unexpected-cell": row[columns["support_id"]] = "unexpected"
    elif mutation == "duplicate-floor": rows.append(copy.deepcopy(row))
    with pytest.raises(DataValidationError):
        ingest("invalid.csv", csv_bytes(rows))


def test_csv_duplicate_engineering_records_retained_and_bad_quotes_rejected():
    rows = csv_rows()
    row = next(row for row in rows if row[0] == "assignment")
    rows.append(copy.deepcopy(row))
    result = ingest("duplicates.csv", csv_bytes(rows))
    assert sum(a["id"] == row[1] for a in result["snapshot"]["assignments"]) == 2
    with pytest.raises(DataValidationError, match="Quote"):
        ingest("quotes.csv", csv_bytes(rows).replace(b"assignment", b'assign"ment', 1))


def test_xlsx_formula_blank_boolean_date_types_preserved_without_evaluation():
    raw = workbook_bytes([["id", "value", "formula", "flag", "date"], ["A", None, "=1+1", True, dt.datetime(2026, 10, 3)]])
    result = ingest("source.xlsx", raw)
    assert result["status"] == "NEEDS_MAPPING" and result["snapshot"] is None
    cells = result["tables"][0]["rows"][0]["cells"]
    assert [c["type"] for c in cells] == ["text", "blank", "formula", "boolean", "date"]
    assert cells[1]["value"] is None and cells[1]["coordinate"] == "B2"
    assert cells[2]["value"] == "=1+1"
    assert cells[4]["value"].startswith("2026-10-03")
    assert result["provenance"][2]["location"] == {"sheet": "Settings", "row": 2, "cell": "C2"}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("rows", [[["id", " id "], ["A", 2]], [["id", None, "value"], ["A", 1, 2]],
    [["id", 12], ["A", 2]], [["id", "value"], ["A", "#DIV/0!"]], [["id"], ["A", 1]]])
def test_xlsx_rejects_bad_headers_errors_and_unnamed_cells(rows):
    with pytest.raises(DataValidationError):
        ingest("invalid.xlsx", workbook_bytes(rows))


def test_pdf_page_provenance_text_and_scanned_page_gate():
    result = ingest("source.pdf", pdf_bytes(["Synthetic source page", None]))
    assert result["status"] == "NEEDS_OCR" and result["snapshot"] is None
    assert "Synthetic source page" in result["pages"][0]["text"]
    assert result["pages"][1] == {"page": 2, "text": "", "needs_ocr": True}
    assert result["provenance"][1]["location"] == {"page": 2}
    assert ingest("text.pdf", pdf_bytes(["Text only"]))["status"] == "NEEDS_MAPPING"


@pytest.mark.parametrize("raw", [b"not a PDF", b"%PDF-1.7\ninvalid"])
def test_malformed_pdf_rejected(raw):
    with pytest.raises(DataValidationError): ingest("invalid.pdf", raw)


def test_encrypted_pdf_rejected():
    with pytest.raises(DataValidationError, match="Encrypted"):
        ingest("encrypted.pdf", pdf_bytes([None], encrypted=True))


def test_version_diff_stable_entities_dependencies_and_no_input_mutation():
    before = fixture()
    after = copy.deepcopy(before)
    after["assignments"][0]["force"] += 5
    after["assignments"].reverse()
    original = copy.deepcopy(after)
    diff = compare_snapshots(before, after)
    assert diff["summary"] == {"added": 0, "removed": 0, "modified": 1}
    assert diff["changes"][0]["entity"] == "assignments:" + before["assignments"][0]["id"]
    assert diff["changes"][0]["path"].endswith("/force")
    assert "QA-004" in diff["impacts"]["checks"] and "QA-005" not in diff["impacts"]["checks"]
    assert not diff["impacts"]["unknown"] and after == original
    reordered = copy.deepcopy(before)
    reordered["assignments"].reverse()
    assert compare_snapshots(before, reordered)["status"] == "UNCHANGED"


def test_version_add_remove_unknown_and_duplicate_entities_conservative():
    before = fixture()
    after = copy.deepcopy(before)
    removed = after["assignments"].pop()
    after["assignments"].append({**removed, "id": "new-assignment"})
    after["unknown_setting"] = 1
    diff = compare_snapshots(before, after)
    assert diff["summary"] == {"added": 2, "removed": 1, "modified": 0}
    assert diff["impacts"]["unknown"] and "ALL_SUPPORTED_CHECKS" in diff["impacts"]["checks"]
    after = copy.deepcopy(before)
    after["assignments"].append(copy.deepcopy(after["assignments"][0]))
    assert compare_snapshots(before, after)["impacts"]["unknown"]


def test_version_diff_distinguishes_nested_boolean_and_numeric_values():
    result = compare_snapshots({"schemaVersion": "1.0", "nested": [True]}, {"schemaVersion": "1.0", "nested": [1]})
    assert result["status"] == "CHANGED" and result["impacts"]["unknown"]


def test_handoff_explicit_units_tolerance_and_zero():
    source, target = handoff_inputs()
    original = copy.deepcopy((source, target))
    result = verify_handoff(source, target, manifest())
    assert result["status"] == "PASS" and result["details"][0]["actual"] == 100
    target["assignment"]["force"] = 101000
    assert verify_handoff(source, target, manifest())["status"] == "PASS"
    target["assignment"]["force"] = 101001
    assert verify_handoff(source, target, manifest())["status"] == "FAIL"
    assert verify_handoff(*handoff_inputs(0, 0), manifest())["status"] == "PASS"
    assert source == original[0]


@pytest.mark.parametrize("mutation", ["unapproved", "empty-mapping", "required-missing", "duplicate", "revision", "negative-tolerance", "bool-tolerance", "undeclared-field"])
def test_handoff_manifest_gates_prevent_false_pass(mutation):
    source, target = handoff_inputs()
    rule = manifest()
    if mutation == "unapproved": rule["approved"] = False
    elif mutation == "empty-mapping": rule["mappings"] = []
    elif mutation == "required-missing": rule["required_source_paths"].append("/another")
    elif mutation == "duplicate": rule["mappings"].append(copy.deepcopy(rule["mappings"][0]))
    elif mutation == "revision": target["project"]["revision"] = "stale"
    elif mutation == "negative-tolerance": rule["mappings"][0]["absolute_tolerance"] = -1
    elif mutation == "bool-tolerance": rule["mappings"][0]["relative_tolerance"] = True
    elif mutation == "undeclared-field": rule["mappings"][0]["formula"] = "source*2"
    assert verify_handoff(source, target, rule)["status"] == "NOT VERIFIED"


@pytest.mark.parametrize("mutation", ["missing-value", "bool-value", "null-value", "unknown-unit", "incompatible-unit", "overflow", "underflow"])
def test_handoff_unknown_units_and_invalid_values_never_pass(mutation):
    source, target = handoff_inputs()
    rule = manifest()
    if mutation == "missing-value": target["assignment"].pop("force")
    elif mutation == "bool-value": target["assignment"]["force"] = True
    elif mutation == "null-value": target["assignment"]["force"] = None
    elif mutation == "unknown-unit": target["units"]["force"] = "lbf"
    elif mutation == "incompatible-unit": target["units"]["force"] = "m2"
    elif mutation == "overflow":
        source["assignment"]["force"] = 1e308
        rule["mappings"][0]["comparison_unit"] = "N"
    elif mutation == "underflow": target["assignment"]["force"] = 5e-324
    assert verify_handoff(source, target, rule)["status"] == "NOT VERIFIED"


def test_combination_configuration_independent_of_reported_response_and_pure():
    data, rule = combination_inputs()
    data["combinations"][0]["reportedValue"] = -9999
    original = copy.deepcopy((data, rule))
    assert verify_combination_configuration(data, rule)["status"] == "PASS"
    assert (data, rule) == original
    data["combinations"][0]["terms"][0]["factor"] = 1.25
    assert verify_combination_configuration(data, rule)["status"] == "FAIL"


@pytest.mark.parametrize("kind", ["baseCases", "combinations", "terms"])
def test_combination_missing_complete_vs_partial_export(kind):
    data, rule = combination_inputs()
    if kind == "terms": data["combinations"][0]["terms"].pop()
    else: data[kind].pop()
    assert verify_combination_configuration(data, rule)["status"] == "FAIL"
    data["configuration_complete"] = False
    assert verify_combination_configuration(data, rule)["status"] == "NOT VERIFIED"


@pytest.mark.parametrize("kind", ["baseCases", "combinations", "terms"])
def test_combination_duplicate_configuration_ids_fail(kind):
    data, rule = combination_inputs()
    rows = data["combinations"][0]["terms"] if kind == "terms" else data[kind]
    rows.append(copy.deepcopy(rows[0]))
    assert verify_combination_configuration(data, rule)["status"] == "FAIL"


def test_combination_rule_approval_completeness_extra_policy_and_namespace():
    data, rule = combination_inputs()
    data.pop("configuration_complete")
    assert verify_combination_configuration(data, rule)["status"] == "NOT VERIFIED"
    data["configuration_complete"] = True
    data["baseCases"].append({"id": "EXTRA"})
    assert verify_combination_configuration(data, rule)["status"] == "FAIL"
    rule["allow_extra_base_cases"] = True
    assert verify_combination_configuration(data, rule)["status"] == "PASS"
    data["baseCases"].append({"id": "C1"})
    assert verify_combination_configuration(data, rule)["status"] == "FAIL"
    rule["required_base_cases"].append("C1")
    assert verify_combination_configuration(data, rule)["status"] == "NOT VERIFIED"
    rule["approved"] = False
    assert verify_combination_configuration(data, rule)["status"] == "NOT VERIFIED"


def test_settings_all_operators_explicit_zero_and_json_pointer_escaping():
    data = {"configuration_complete": True, "settings": {"type": "manual", "scale": 0, "a/b": True}}
    rule = setting_rule({"path": "/settings/type", "operator": "in", "value": ["manual", "auto"]},
        {"path": "/settings/scale", "operator": "range", "min": 0, "max": 1},
        {"path": "/settings/a~1b", "operator": "eq", "value": True})
    original = copy.deepcopy((data, rule))
    result = verify_settings(data, rule)
    assert result["status"] == "PASS" and len(result["details"]) == 3
    assert (data, rule) == original
    data["settings"]["scale"] = 1.001
    assert verify_settings(data, rule)["status"] == "FAIL"


@pytest.mark.parametrize("setting", [{"path": "/missing", "operator": "eq", "value": 0},
    {"path": "/actual", "operator": "javascript", "value": 1},
    {"path": "/actual", "operator": "range", "min": True, "max": 2},
    {"path": "/actual", "operator": "range", "min": 3, "max": 2},
    {"path": "/actual", "operator": "eq", "value": None},
    {"path": "/actual", "operator": "in", "value": []},
    {"path": "/actual", "operator": "eq", "value": 1, "default": 1}])
def test_settings_missing_or_invalid_rule_never_pass(setting):
    assert verify_settings({"configuration_complete": True, "actual": 1}, setting_rule(setting))["status"] == "NOT VERIFIED"


@pytest.mark.parametrize("operator,value", [("eq", 1), ("in", [1])])
def test_settings_bool_is_not_a_numeric_match(operator, value):
    rule = setting_rule({"path": "/actual", "operator": operator, "value": value})
    assert verify_settings({"configuration_complete": True, "actual": True}, rule)["status"] == "FAIL"


def test_settings_bool_not_numeric_range_and_completeness_approval_required():
    rule = setting_rule({"path": "/actual", "operator": "range", "min": 0, "max": 1})
    assert verify_settings({"configuration_complete": True, "actual": True}, rule)["status"] == "NOT VERIFIED"
    assert verify_settings({"actual": 1}, rule)["status"] == "NOT VERIFIED"
    assert verify_settings({"configuration_complete": True, "actual": None}, rule)["status"] == "NOT VERIFIED"
    rule["approved"] = False
    assert verify_settings({"configuration_complete": True, "actual": 1}, rule)["status"] == "NOT VERIFIED"
