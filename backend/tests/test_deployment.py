import pytest
from fastapi.testclient import TestClient

from strata.app import create_app


def test_public_https_origin_works_without_trusting_arbitrary_proxy_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATA_ALLOWED_HOSTS", "qa.customer.example")
    monkeypatch.setenv("STRATA_PUBLIC_ORIGIN", "https://qa.customer.example")
    with TestClient(create_app(tmp_path, testing=True, worker=False)) as client:
        response = client.post("/api/v1/auth/bootstrap", headers={"Host": "qa.customer.example", "Origin": "https://qa.customer.example"}, json={"username": "owner", "password": "long-local-password"})
        assert response.status_code == 200
        assert client.post("/api/v1/auth/login", headers={"Host": "qa.customer.example", "Origin": "https://attacker.example"}, json={"username": "owner", "password": "long-local-password"}).status_code == 403


def test_remote_bootstrap_requires_operator_token(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATA_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("STRATA_SETUP_TOKEN", "temporary-operator-setup-token")
    with TestClient(create_app(tmp_path, testing=False, worker=False)) as client:
        body = {"username": "owner", "password": "long-local-password"}
        assert client.post("/api/v1/auth/bootstrap", json=body).status_code == 403
        assert client.post("/api/v1/auth/bootstrap", headers={"X-Setup-Token": "temporary-operator-setup-token"}, json=body).status_code == 200
        assert client.post("/api/v1/auth/bootstrap", headers={"X-Setup-Token": "temporary-operator-setup-token"}, json=body).status_code == 409


def test_password_change_revokes_sessions(tmp_path):
    with TestClient(create_app(tmp_path, testing=True, worker=False)) as client:
        response = client.post("/api/v1/auth/bootstrap", json={"username": "owner", "password": "long-local-password"})
        client.headers["Authorization"] = "Bearer " + response.json()["token"]
        assert client.post("/api/v1/auth/password", json={"current_password": "long-local-password", "new_password": "updated-local-password"}).status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "long-local-password"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "updated-local-password"}).status_code == 200


def test_chunked_body_is_bounded_without_content_length(tmp_path):
    with TestClient(create_app(tmp_path, testing=True, worker=False)) as client:
        response = client.post("/api/v1/auth/bootstrap", content=(b"x" * 1_000_000 for _ in range(15)), headers={"Content-Type": "application/json"})
        assert response.status_code == 413


@pytest.mark.parametrize("origin", ["http://not-tls.example", "https://host/path", "https://user:password@host", "https://host?secret=a"])
def test_invalid_public_origin_rejected(tmp_path, monkeypatch, origin):
    monkeypatch.setenv("STRATA_PUBLIC_ORIGIN", origin)
    with pytest.raises(ValueError): create_app(tmp_path, testing=True, worker=False)
