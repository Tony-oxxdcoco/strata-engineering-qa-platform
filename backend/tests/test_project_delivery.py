import io
import json
import zipfile
from test_api import system


def test_project_export_has_original_bytes_but_no_auth_secrets(system):
    _, client, base, project, _ = system
    response = client.get(base + "/export")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert bundle.testzip() is None
        data = json.loads(bundle.read("project.json"))
        assert data["project"]["id"] == project["id"]
        assert data["audit"]["valid"]
        assert not any(name.startswith(".runtime") for name in bundle.namelist())
        assert b"long-test-password" not in bundle.read("project.json")
        assert any(name.startswith("sources/") for name in bundle.namelist())


def test_membership_revocation_applies_to_existing_session(system):
    _, client, base, _, _ = system
    owner = client.headers["Authorization"]
    account = client.post("/api/v1/users", json={"username": "revoked-viewer", "password": "long-test-password"}).json()["user"]
    client.post(base + "/members", json={"user_id": account["id"], "role": "viewer"})
    token = client.post("/api/v1/auth/login", json={"username": "revoked-viewer", "password": "long-test-password"}).json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    assert client.get(base + "/dashboard").status_code == 200
    assert client.get(base + "/export").status_code == 403
    client.headers["Authorization"] = owner
    assert client.delete(base + "/members/" + account["id"]).status_code == 200
    client.headers["Authorization"] = "Bearer " + token
    assert client.get(base + "/dashboard").status_code == 404
