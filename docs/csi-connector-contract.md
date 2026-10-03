# Client-owned CSI connector contract

STRATA calls an explicitly configured HTTP service; it does not control a user's desktop, install CSI or claim a live connection. `backend/strata/connector.py` is the implemented client. A Windows service maintained with the client's IT engineer must implement the following read-only export contract.

`POST /v1/export`

```json
{"contract":"strata-csi-export-1.0","model_id":"opaque-model-id","revision":"R1","profile":"approved-gravity-export","read_only":true}
```

Response contains the same identifiers plus `software_version`, UTC `exported_at`, `snapshot`, `snapshot_sha256`, and `read_only:true`. The snapshot is a supported canonical JSON engineering input. Its hash is SHA-256 of UTF-8 `JSON.stringify(snapshot)` with Unicode characters unescaped and no insignificant spaces; preserve numeric representation in the emitting service. There is no command/expression/model-write endpoint. Independent brief/support/reference evidence must come from its actual source, not be derived from the model under test.

The operator configures `STRATA_ETABS_URL` and optional `STRATA_ETABS_TOKEN` server-side. HTTPS is required except loopback development. Client requests cannot choose a URL. Redirects, wrong model/revision/profile, unsupported mappings, oversized responses, missing provenance and changed bytes are rejected. Tools capability reporting distinguishes configured from live-validated.

Authenticated engineers import via `POST /api/v1/projects/{id}/connector/import`. Valid exports become original stored files plus immutable snapshots. Rule validation and the ordinary QA workflow still apply. A configured connector does not authorize the legacy synthetic-only calculation profile for client data.

Live acceptance requires: client Windows host, actual CSI version/license, a harmless read-only model, known-good/known-bad exports, approved column/unit mapping, and comparison by the responsible engineer. Mock transport tests only validate this HTTP boundary. Native CSI adapter implementation and interoperability remain external gates until those resources are supplied.
