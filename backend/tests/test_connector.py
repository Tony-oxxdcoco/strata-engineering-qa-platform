import hashlib
import json

import httpx
import pytest

from strata.connector import CONTRACT, config, export_snapshot
from strata.workflow import node_tool


def test_disabled_connector_makes_no_request(monkeypatch):
    monkeypatch.delenv("STRATA_ETABS_URL", raising=False)
    assert config()["configured"] is False
    with pytest.raises(ValueError, match="not been configured"):
        export_snapshot("model", "R1", "gravity")


@pytest.mark.parametrize("url", ["http://example.org", "https://user:secret@example.org", "https://example.org/path", "https://example.org?token=a", "file:///tmp/example"])
def test_connector_config_rejects_unsafe_url(monkeypatch, url):
    monkeypatch.setenv("STRATA_ETABS_URL", url)
    with pytest.raises(ValueError):
        config()


@pytest.mark.parametrize("change", [None, "revision", "hash", "read_only", "redirect", "invalid_json", "duplicate"])
def test_export_contract_identity_hash_and_failures(monkeypatch, change):
    monkeypatch.setenv("STRATA_ETABS_URL", "https://client-connector.example")
    data = node_tool("seed")["gravity"]
    revision = data["project"]["revision"]
    content = json.dumps(data, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode()
    payload = {"contract": CONTRACT, "model_id": "M1", "revision": revision, "profile": "gravity", "read_only": True, "snapshot": data, "snapshot_sha256": hashlib.sha256(content).hexdigest(), "exported_at": "2026-10-03T00:00:00Z", "software_version": "test fixture, not CSI"}
    if change == "revision": payload["revision"] = "wrong"
    if change == "hash": payload["snapshot_sha256"] = "0" * 64
    if change == "read_only": payload["read_only"] = False
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        if change == "redirect": return httpx.Response(302, headers={"location": "https://other.example"})
        if change == "invalid_json": return httpx.Response(200, content=b"bad")
        if change == "duplicate": return httpx.Response(200, content=b'{"contract":"x","contract":"y"}')
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if change:
            with pytest.raises(ValueError): export_snapshot("M1", revision, "gravity", client)
        else:
            result = export_snapshot("M1", revision, "gravity", client)
            assert json.loads(result["bytes"]) == data
    assert len(seen) == 1
    assert seen[0]["read_only"] is True
