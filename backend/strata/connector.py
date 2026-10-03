"""Read-only HTTP adapter boundary for a client-owned Windows/CSI service.

No outbound connection occurs without operator configuration. This does not
claim the remote service implements the CSI API or has passed interoperability.
"""
import hashlib
import json
import os
from urllib.parse import urlsplit

import httpx

from .data_tools import ingest

CONTRACT = "strata-csi-export-1.0"


def config():
    base = os.environ.get("STRATA_ETABS_URL", "").rstrip("/")
    if not base:
        return {"configured": False, "contract": CONTRACT, "reason": "A validated client-owned Windows connector has not been configured"}
    url = urlsplit(base)
    local = url.hostname in {"127.0.0.1", "localhost", "::1"}
    if url.scheme != "https" and not (local and url.scheme == "http") or not url.hostname or url.username or url.password or url.query or url.fragment or url.path:
        raise ValueError("Connector must use HTTPS, or loopback HTTP, with no URL credentials/path")
    return {"configured": True, "contract": CONTRACT, "base": base}


def export_snapshot(model_id, revision, profile, client=None):
    settings = config()
    if not settings["configured"]:
        raise ValueError(settings["reason"])
    for value in [model_id, revision, profile]:
        if not isinstance(value, str) or not 1 <= len(value) <= 160 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid connector model/revision/profile identifier")
    own = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
    headers = {"Accept": "application/json"}
    if os.environ.get("STRATA_ETABS_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["STRATA_ETABS_TOKEN"]
    try:
        with client.stream("POST", settings["base"] + "/v1/export", json={"contract": CONTRACT, "model_id": model_id, "revision": revision, "profile": profile, "read_only": True}, headers=headers) as response:
            if response.status_code != 200:
                raise ValueError("Connector unavailable or request rejected")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 10_000_000:
                    raise ValueError("Connector response exceeds 10 MB")
        def strict_pairs(pairs):
            data = {}
            for key, value in pairs:
                if key in data:
                    raise ValueError("Duplicate connector response field")
                data[key] = value
            return data
        payload = json.loads(raw, object_pairs_hook=strict_pairs)
        if not isinstance(payload, dict) or payload.get("contract") != CONTRACT or payload.get("model_id") != model_id or payload.get("revision") != revision or payload.get("profile") != profile or payload.get("read_only") is not True:
            raise ValueError("Connector identity/contract mismatch")
        if not isinstance(payload.get("snapshot"), dict) or not isinstance(payload.get("exported_at"), str) or not payload.get("software_version"):
            raise ValueError("Connector snapshot provenance is incomplete")
        encoded = json.dumps(payload["snapshot"], allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode()
        if payload.get("snapshot_sha256") != hashlib.sha256(encoded).hexdigest():
            raise ValueError("Connector snapshot hash mismatch")
        result = ingest("connector-export.json", encoded)
        if result["status"] != "READY" or result["snapshot"].get("project", {}).get("revision") != revision:
            raise ValueError("Connector export requires explicit supported mapping and matching revision")
        return {"bytes": encoded, "provenance": {k: payload[k] for k in ["contract", "model_id", "revision", "profile", "exported_at", "software_version", "snapshot_sha256"]}}
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeError, KeyError, TypeError) as error:
        raise ValueError("Connector failed or returned malformed data") from error
    finally:
        if own:
            client.close()
