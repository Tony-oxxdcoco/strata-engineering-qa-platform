from test_api import system, run


def issues(client, base):
    return client.get(base + "/dashboard").json()["issues"]


def corrected(system, original):
    app, client, base, _, seed = system
    snapshot = seed["snapshots"][0]["id"]
    assert client.post(base + "/snapshots/" + snapshot + "/activate").status_code == 200
    response = client.post(base + "/runs/" + original["id"] + "/resume", json={"snapshot_id": snapshot})
    assert response.status_code == 200, response.text
    rid = response.json()["run"]["id"]
    app.state.runner.process(rid)
    return client.get(base + "/runs/" + rid).json()["run"]


def test_findings_require_linked_verified_resolution(system):
    _, client, base, _, _ = system
    original = run(system, 1)
    records = issues(client, base)
    assert len(records) == sum(r["status"] != "PASS" for r in original["results"])
    assert records and all(i["state"] == "OPEN" for i in records)
    issue_path = base + "/issues/" + records[0]["id"]
    actor = client.get("/api/v1/auth/me").json()["id"]
    assert client.post(issue_path, json={"action": "assign", "assignee": actor, "note": "Reviewer owns correction"}).status_code == 200
    assert client.post(issue_path, json={"action": "request_evidence", "note": "Supply corrected export"}).status_code == 200
    assert client.post(issue_path, json={"action": "resolve", "note": "Looks good"}).status_code != 200
    unlinked = run(system)
    assert client.post(issue_path, json={"action": "resolve", "resolution_run_id": unlinked["id"], "note": "Unrelated PASS"}).status_code == 409
    successor = corrected(system, original)
    assert successor["status"] == "PASS"
    review_path = base + "/runs/" + successor["id"] + "/review"
    decision = {"action": "approve", "note": "Compared correction with original findings"}
    assert client.post(review_path, json=decision).status_code == 409
    for record in records:
        response = client.post(base + "/issues/" + record["id"], json={"action": "resolve", "resolution_run_id": successor["id"], "note": "Corrected field passes in linked successor"})
        assert response.status_code == 200, response.text
    assert client.post(review_path, json=decision).status_code == 200
    assert client.get(base + "/runs/" + original["id"]).json()["run"]["status"] == "FAIL"
    assert all(i["state"] == "RESOLVED" for i in issues(client, base))
    assert client.post(issue_path, json={"action": "request_evidence", "note": "Rewrite history"}).status_code == 409


def test_stale_successor_and_engineer_cannot_close_issue(system):
    _, client, base, _, seed = system
    original = run(system, 2)
    issue = issues(client, base)[0]
    successor = corrected(system, original)
    client.post(base + "/snapshots/" + seed["snapshots"][1]["id"] + "/activate")
    payload = {"action": "resolve", "resolution_run_id": successor["id"], "note": "Must remain current"}
    path = base + "/issues/" + issue["id"]
    assert client.post(path, json=payload).status_code == 409
    account = client.post("/api/v1/users", json={"username": "issue-engineer", "password": "long-test-password"}).json()["user"]
    client.post(base + "/members", json={"user_id": account["id"], "role": "engineer"})
    login = client.post("/api/v1/auth/login", json={"username": "issue-engineer", "password": "long-test-password"})
    client.headers["Authorization"] = "Bearer " + login.json()["token"]
    assert client.post(path, json=payload).status_code == 403
    assert client.post(path, json={"action": "assign", "assignee": "outside-project", "note": "Invalid member"}).status_code == 422
    assert client.post(path, json={"action": "request_evidence", "note": "Need revised record"}).status_code == 200
