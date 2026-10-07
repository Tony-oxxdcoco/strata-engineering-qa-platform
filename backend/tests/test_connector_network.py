"""Real loopback HTTP fault tests against our synthetic service, never CSI."""
import importlib.util
import json
from pathlib import Path
import threading

import httpx
import pytest

from strata.connector import export_snapshot

spec = importlib.util.spec_from_file_location("csi_mock", Path(__file__).resolve().parents[2] / "scripts/csi-mock-server.py")
mock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock)


@pytest.mark.parametrize("fault", mock.FAULTS)
def test_real_loopback_synthetic_faults(monkeypatch, fault):
    server = mock.make_server(fault)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("STRATA_ETABS_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("STRATA_ETABS_TIMEOUT_SECONDS", "0.1")
    try:
        if fault in {"normal", "repeat-response"}:
            first = export_snapshot("M-SYNTHETIC", "R-SYNTHETIC", "synthetic-gravity")
            assert json.loads(first["bytes"])["synthetic"] is True
            assert first["provenance"]["software_version"].startswith("SYNTHETIC")
            if fault == "repeat-response":
                assert export_snapshot("M-SYNTHETIC", "R-SYNTHETIC", "synthetic-gravity") == first
                assert len(server.requests) == 2
        else:
            with pytest.raises(ValueError):
                export_snapshot("M-SYNTHETIC", "R-SYNTHETIC", "synthetic-gravity")
        assert server.requests and all(r["read_only"] is True for r in server.requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("field,value", [("software_version", {}), ("software_version", ""),
    ("software_version", "version\nheader"), ("exported_at", "not a time"),
    ("exported_at", "2026-10-07T00:00:00"), ("exported_at", "2026-10-07T01:00:00+01:00")])
def test_provenance_requires_inspectable_string_and_utc(monkeypatch, field, value):
    monkeypatch.setenv("STRATA_ETABS_URL", "https://synthetic.invalid")
    payload = mock.payload()
    payload[field] = value
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(ValueError):
            export_snapshot("M-SYNTHETIC", "R-SYNTHETIC", "synthetic-gravity", client)


@pytest.mark.parametrize("value", ["no", "nan", "inf", "0", "61"])
def test_invalid_timeout_is_rejected_before_request(monkeypatch, value):
    monkeypatch.setenv("STRATA_ETABS_URL", "https://synthetic.invalid")
    monkeypatch.setenv("STRATA_ETABS_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="timeout"):
        export_snapshot("M-SYNTHETIC", "R-SYNTHETIC", "synthetic-gravity")


def test_false_content_type_and_nonfinite_snapshot_rejected(monkeypatch):
    monkeypatch.setenv("STRATA_ETABS_URL", "https://synthetic.invalid")
    for response in [httpx.Response(200, content=b"{}", headers={"content-type": "text/html"}),
                     httpx.Response(200, json={**mock.payload(), "snapshot": {"number": float("inf")}})]:
        with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client:
            with pytest.raises(ValueError):
                export_snapshot("M-SYNTHETIC", "R-SYNTHETIC", "synthetic-gravity", client)
