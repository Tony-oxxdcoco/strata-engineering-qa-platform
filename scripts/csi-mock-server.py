#!/usr/bin/env python3
"""Loopback-only synthetic CSI contract service. This never calls CSI software."""
from __future__ import annotations

import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import time

CONTRACT = "strata-csi-export-1.0"
FAULTS = ("normal", "missing-field", "wrong-unit", "unsupported-version", "wrong-revision",
          "timeout", "disconnect", "duplicate-key", "bad-hash", "repeat-response")


def synthetic_snapshot():
    """Hand-written transport fixture, with no claimed engineering approval."""
    return {"schemaVersion": "1.0", "synthetic": True,
        "project": {"name": "SYNTHETIC CSI HTTP fixture — not a client model", "revision": "R-SYNTHETIC"},
        "units": {"area": "m2", "force": "kN", "surfaceLoad": "kN/m2"},
        "scope": {"basis": "unfactored-static-gravity", "selfWeight": "excluded", "reactionPositive": "upward"},
        "floors": [{"id": "L1", "area": 10, "evidenceRef": "fixture-source"}],
        "requirements": [{"id": "requirement-DL", "floorId": "L1", "caseId": "DL", "q": 2, "evidenceRef": "fixture-source"}],
        "assignments": [{"id": "assignment-DL", "floorId": "L1", "caseId": "DL", "force": 20, "evidenceRef": "fixture-source"}],
        "supports": ["S1"],
        "reactions": [{"id": "reaction-DL", "supportId": "S1", "caseId": "DL", "fz": 20, "evidenceRef": "fixture-source"}],
        "evidence": [{"id": "fixture-source", "title": "SYNTHETIC transport fixture", "locator": "csi-mock-server.py", "content": "Self-made HTTP boundary fixture; not engineering approval."}]}


def payload(fault="normal"):
    snapshot = synthetic_snapshot()
    if fault == "wrong-unit":
        snapshot["units"]["force"] = "N"
    if fault == "wrong-revision":
        snapshot["project"]["revision"] = "OTHER-SYNTHETIC"
    encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    value = {"contract": CONTRACT, "model_id": "M-SYNTHETIC", "revision": "R-SYNTHETIC",
        "profile": "synthetic-gravity", "read_only": True, "snapshot": snapshot,
        "snapshot_sha256": hashlib.sha256(encoded).hexdigest(),
        "exported_at": "2026-10-07T00:00:00Z", "software_version": "SYNTHETIC mock — not ETABS/SAFE"}
    if fault == "missing-field": del value["software_version"]
    if fault == "unsupported-version": value["contract"] = "strata-csi-export-UNSUPPORTED"
    if fault == "bad-hash": value["snapshot_sha256"] = "0" * 64
    return value


def make_server(fault="normal", delay_seconds=.3, port=0):
    if fault not in FAULTS:
        raise ValueError("Unsupported synthetic fault")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != "/v1/export":
                self.send_error(404)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("request size")
                request = json.loads(self.rfile.read(size))
                expected = {"contract": CONTRACT, "model_id": "M-SYNTHETIC", "revision": "R-SYNTHETIC",
                    "profile": "synthetic-gravity", "read_only": True}
                if request != expected or request.get("read_only") is not True:
                    raise ValueError("request identity")
            except (ValueError, TypeError):
                self.send_error(400, "Only the documented synthetic identity is supported")
                return
            self.server.requests.append(copy.deepcopy(request))
            if fault == "disconnect":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if fault == "timeout":
                time.sleep(delay_seconds)
            raw = json.dumps(payload(fault), ensure_ascii=False, separators=(",", ":")).encode()
            if fault == "duplicate-key":
                raw = b'{"contract":"duplicate",' + raw[1:]
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                # A deliberate timeout/disconnect fixture has no further output.
                if fault not in {"timeout", "disconnect"}:
                    raise
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.requests = []
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4188)
    parser.add_argument("--fault", choices=FAULTS, default="normal")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use a loopback port between 1024 and 65535")
    with make_server(args.fault, port=args.port) as server:
        print(json.dumps({"url": f"http://127.0.0.1:{args.port}", "material": "SYNTHETIC ONLY",
                          "model_id": "M-SYNTHETIC", "revision": "R-SYNTHETIC", "profile": "synthetic-gravity", "fault": args.fault}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
