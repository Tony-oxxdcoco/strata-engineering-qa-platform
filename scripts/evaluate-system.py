#!/usr/bin/env python3
"""Fixed controlled acceptance through the authenticated server, not UI mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient
from strata.app import create_app
from strata.storage import now
from strata.workflow import TOOL_FINGERPRINT, node_tool

CASES = [
    ("S01", 0, "gravity-full", None, "PASS"),
    ("S02", 1, "gravity-full", None, "FAIL"),
    ("S03", 2, "gravity-full", None, "NOT VERIFIED"),
    ("S04", 3, "gravity-full", None, "FAIL"),
    ("S05", 4, "load-combination", None, "PASS"),
    ("S06", 5, "load-combination", None, "FAIL"),
    ("S07", 6, "load-combination", None, "NOT VERIFIED"),
    ("S08", 7, "load-combination", None, "NOT VERIFIED"),
    ("S09", 8, "combination-configuration", None, "PASS"),
    ("S10", 9, "combination-configuration", None, "FAIL"),
    ("S11", 10, "combination-configuration", None, "NOT VERIFIED"),
    ("S12", 11, "handoff", 12, "PASS"),
    ("S13", 11, "handoff", 13, "FAIL"),
    ("S14", 14, "seismic-configuration", None, "PASS"),
    ("S15", 15, "seismic-configuration", None, "FAIL"),
    ("S16", 16, "mass-source", None, "PASS"),
    ("S17", 17, "mass-source", None, "NOT VERIFIED"),
    ("S18", 18, "additional-settings", None, "PASS"),
]


def evaluate():
    results = []
    with tempfile.TemporaryDirectory(prefix="strata-evaluation-") as directory:
        app = create_app(directory, testing=True, worker=False)
        with TestClient(app) as client:
            auth = client.post("/api/v1/auth/bootstrap", json={"username": "acceptance", "password": "controlled-test-account"}).json()
            client.headers["Authorization"] = "Bearer " + auth["token"]
            project = client.post("/api/v1/projects", json={"name": "Isolated controlled acceptance"}).json()["project"]
            base = "/api/v1/projects/" + project["id"]
            snapshots = client.post(base + "/seed").json()["snapshots"]
            for case_id, index, task, target, expected in CASES:
                body = {"snapshot_id": snapshots[index]["id"], "task_id": task}
                if target is not None: body["compare_to"] = snapshots[target]["id"]
                started = time.perf_counter()
                row = client.post(base + "/runs", json=body).json()["run"]
                app.state.runner.process(row["id"])
                result = client.get(base + "/runs/" + row["id"]).json()["run"]
                numeric = None
                if case_id == "S05":
                    observed = [r["details"][0]["expected"] for r in result["results"]]
                    numeric = {"expected": [195, 50], "actual": observed, "matched": observed == [195, 50]}
                match = result["status"] == expected and result["state"] == ("WAITING" if expected == "NOT VERIFIED" else "COMPLETED") and (numeric is None or numeric["matched"])
                results.append({"id": case_id, "title": snapshots[index]["title"], "task": task, "expected": expected, "actual": result["status"], "state": result["state"], "matched": match, "numeric_oracle": numeric, "input_hash": snapshots[index]["input_hash"], "latency_ms": round((time.perf_counter()-started)*1000, 3), "calculation_ms": result.get("calculation_ms"), "citation_count": len(result["citations"]), "explanation": result.get("explanation")})
            # Identical full runs: report both total API/workflow cost and the
            # numerical-tool portion. This is not reviewer-time measurement.
            uncached, cached = [], []
            for repetition in range(30):
                for reuse, bucket in [(False, uncached), (True, cached)]:
                    if not reuse:
                        from sqlalchemy import delete
                        from strata.storage import Resource
                        with app.state.store.session.begin() as session:
                            session.execute(delete(Resource).where(Resource.kind == "cache"))
                    started = time.perf_counter()
                    row = client.post(base + "/runs", json={"snapshot_id": snapshots[0]["id"], "task_id": "gravity-full"}).json()["run"]
                    app.state.runner.process(row["id"])
                    result = client.get(base + "/runs/" + row["id"]).json()["run"]
                    assert result["status"] == "PASS" and result["cache_hit"] is reuse
                    bucket.append({"total_ms": (time.perf_counter()-started)*1000, "calculation_ms": result["calculation_ms"]})
    expected_negative = sum(r["expected"] != "PASS" for r in results)
    predicted_positive = sum(r["actual"] == "PASS" for r in results)
    false_pass = sum(r["expected"] != "PASS" and r["actual"] == "PASS" for r in results)
    return {"generated_at": now(), "scope": "Hand-authored synthetic software acceptance only; no real client engineering accuracy or CSI interoperability claim.", "tool_fingerprint": TOOL_FINGERPRINT, "fixture_sha256": hashlib.sha256(json.dumps(CASES).encode()).hexdigest(), "platform": platform.platform(), "summary": {"total": len(results), "matched": sum(r["matched"] for r in results), "false_pass": false_pass, "false_pass_denominator_expected_nonpass": expected_negative, "false_pass_denominator_actual_pass": predicted_positive, "expected_not_verified": sum(r["expected"] == "NOT VERIFIED" for r in results), "actual_not_verified": sum(r["actual"] == "NOT VERIFIED" for r in results), "software_errors": sum(r["state"] == "ERROR" for r in results)}, "cases": results, "cache_experiment": {"sample_pairs": 30, "concurrency": 1, "python": platform.python_version(), "cpu_architecture": platform.machine(), "scope": "30 paired repeated gravity runs on this machine; identical input/rules; no model call; not production SLA or human time saving", "uncached": uncached, "cached": cached, "p95_total_ms": {"uncached": round(sorted(r["total_ms"] for r in uncached)[28],3), "cached": round(sorted(r["total_ms"] for r in cached)[28],3)}, "median_total_ms": {"uncached": round(statistics.median(r["total_ms"] for r in uncached),3), "cached": round(statistics.median(r["total_ms"] for r in cached),3)}}, "preserved_baseline": node_tool("validation")}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "docs/system-evaluation-2026-10-03.json")
    args=parser.parse_args()
    result=evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"artifact":str(args.output),"summary":result["summary"],"cache":result["cache_experiment"]["median_total_ms"]}))
    raise SystemExit(0 if result["summary"]["matched"] == result["summary"]["total"] else 1)
