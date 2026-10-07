"""Actual request media variants and untrusted text in exported reports."""
import pytest

from test_api import system, run


@pytest.mark.parametrize("media", [None, "Application/JSON", "application/json ; charset=utf-8", "application/problem+json"])
def test_all_accepted_json_media_reject_duplicate_request_keys(system, media):
    _, client, _, _, _ = system
    response = client.post("/api/v1/projects", content=b'{"name":"SYNTHETIC first","name":"SYNTHETIC duplicate"}',
                           headers={} if media is None else {"Content-Type": media})
    assert response.status_code == 422, response.text
    assert all(p["name"] != "SYNTHETIC duplicate" for p in client.get("/api/v1/projects").json()["items"])


def test_report_escapes_review_text_but_json_preserves_original(system):
    _, client, base, _, _ = system
    result = run(system)
    text = '<script>alert("synthetic")</script><img src=x onerror="alert(1)">'
    response = client.post(base + "/runs/" + result["id"] + "/review", json={"action": "approve", "note": text})
    assert response.status_code == 200
    report = client.get(base + "/runs/" + result["id"] + "/report")
    assert report.status_code == 200
    assert "<script>" not in report.text and "<img src=x" not in report.text
    assert "&lt;script&gt;" in report.text and "&lt;img src=x" in report.text
    raw = client.get(base + "/runs/" + result["id"] + "/report?format=json").json()
    assert raw["run"]["reviews"][0]["note"] == text


def test_ocr_images_allow_local_blob_without_relaxing_scripts(tmp_path):
    from fastapi.testclient import TestClient
    from strata.app import create_app
    with TestClient(create_app(tmp_path,testing=True,worker=False)) as client:
        policy=client.get('/').headers['Content-Security-Policy']
        assert "img-src 'self' data: blob:" in policy
        assert "script-src 'self';" in policy
        assert "script-src 'self' blob:" not in policy
        assert "object-src" not in policy or "object-src 'none'" in policy
