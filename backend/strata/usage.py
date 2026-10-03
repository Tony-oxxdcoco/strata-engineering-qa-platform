"""Durable per-project local-model call budget; no monetary-cost inference."""
from .storage import Resource, digest, now


def usage_view(store, session, project):
    day = now()[:10]
    key = "usage_" + digest([project.id, day])
    row = session.get(Resource, key)
    calls = row.data["calls"] if row else 0
    limit = project.data.get("model_daily_limit", 100)
    return {"day_utc": day, "calls": calls, "limit": limit, "remaining": max(0, limit - calls), "warning": "DISABLED" if limit == 0 else "LIMIT_REACHED" if calls >= limit else "NEAR_LIMIT" if calls >= .8 * limit else None, "billing": "Local inference; electricity and hardware cost not measured. No paid provider is configured."}


def reserve_call(store, project_id, run_id):
    with store.session.begin() as session:
        project = session.get(Resource, project_id)
        info = usage_view(store, session, project)
        if info["remaining"] == 0:
            raise ValueError("Project local-model daily call limit reached or disabled; use explicit task selection")
        key = "usage_" + digest([project_id, info["day_utc"]])
        row = session.get(Resource, key)
        data = {"day_utc": info["day_utc"], "calls": info["calls"] + 1}
        if row:
            store.change(session, row, data)
        else:
            store.add(session, "model_usage", project_id, data, key)
        store.audit(session, project_id, "worker", "model.call_reserved", run_id, data)
