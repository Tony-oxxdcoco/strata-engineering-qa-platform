from test_api import system, run


def test_model_call_budget_is_durable_and_explicit_task_remains_available(system, monkeypatch):
    _, client, base, _, _ = system
    calls = []
    def route(question):
        calls.append(question)
        return {"method": "local-model", "task_id": "gravity-full"}
    monkeypatch.setattr("strata.workflow.model.route", route)
    assert client.post(base + "/model-policy", json={"daily_limit": 1}).status_code == 200
    assert run(system, use_model=True, question="Check gravity")["status"] == "PASS"
    assert client.get(base + "/runtime").json()["model_usage"]["warning"] == "LIMIT_REACHED"
    blocked = run(system, use_model=True, question="Check again")
    assert blocked["status"] == "NOT VERIFIED"
    assert "limit" in blocked["explanation"]
    assert len(calls) == 1
    assert run(system)["status"] == "PASS"
    assert client.get(base + "/runtime").json()["model_usage"]["calls"] == 1


def test_disabled_and_invalid_model_budgets(system, monkeypatch):
    _, client, base, _, _ = system
    for value in [True, -1, 10001, "1"]:
        assert client.post(base + "/model-policy", json={"daily_limit": value}).status_code == 422
    client.post(base + "/model-policy", json={"daily_limit": 0})
    monkeypatch.setattr("strata.workflow.model.route", lambda _: (_ for _ in ()).throw(AssertionError("Must not call disabled provider")))
    assert run(system, use_model=True)["status"] == "NOT VERIFIED"
    assert client.get(base + "/runtime").json()["model_usage"]["warning"] == "DISABLED"
