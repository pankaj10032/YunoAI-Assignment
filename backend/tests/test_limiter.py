from datetime import datetime, timedelta, timezone

from app.models.models import QuotaCounter

from .conftest import create_agent


def test_agent_quota_limit_blocks_and_recovers(client, db, monkeypatch):
    agent = create_agent(client)
    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: "ok",
    )
    monkeypatch.setattr("app.middleware.limiter._estimate_tokens", lambda request: 1)

    class FakeDateTime:
        offset = 0

        @classmethod
        def now(cls, tz=None):
            return datetime.now(timezone.utc) + timedelta(seconds=cls.offset)

    monkeypatch.setattr("app.middleware.limiter.datetime", FakeDateTime)

    headers = {"x-max-req-per-min": "2", "x-max-concurrent": "1", "x-max-tokens-per-hr": "20"}
    statuses = [
        client.post(f"/api/agents/{agent['id']}/execute", json={"task_description": f"task {i}"}, headers=headers).status_code
        for i in range(3)
    ]

    assert statuses[:2] == [202, 202]
    assert statuses[2] == 429
    assert client.post(
        f"/api/agents/{agent['id']}/execute",
        json={"task_description": "after window"},
        headers=headers,
    ).status_code == 429

    FakeDateTime.offset = 61
    response = client.post(
        f"/api/agents/{agent['id']}/execute",
        json={"task_description": "after reset"},
        headers=headers,
    )
    assert response.status_code == 202

    quota = db.query(QuotaCounter).filter(QuotaCounter.entity_id == f"agent:{agent['id']}").one()
    assert quota.requests_count == 1
    assert quota.concurrent_count == 0

    status_response = client.get("/api/quotas/status", params={"entity_id": f"agent:{agent['id']}", "type": "agent"})
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["current_usage"]


def test_channel_specific_quota_is_independent(client, db, monkeypatch):
    a1 = create_agent(client, {"name": "Quota A", "channels": ["web"], "tools": [{"name": "memory"}], "memory_enabled": True, "role": "A", "system_prompt": "A", "model": "gpt-4o-mini", "guardrails": {}, "schedule": None})
    a2 = create_agent(client, {"name": "Quota B", "channels": ["web"], "tools": [{"name": "memory"}], "memory_enabled": True, "role": "B", "system_prompt": "B", "model": "gpt-4o-mini", "guardrails": {}, "schedule": None})
    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: "ok",
    )
    monkeypatch.setattr("app.middleware.limiter._estimate_tokens", lambda request: 1)

    headers = {"x-max-req-per-min": "5", "x-max-concurrent": "1", "x-max-tokens-per-hr": "20"}
    r1 = client.post(f"/api/agents/{a1['id']}/execute", json={"task_description": "one"}, headers=headers)
    r2 = client.post(f"/api/agents/{a2['id']}/execute", json={"task_description": "two"}, headers=headers)

    assert r1.status_code == 202
    assert r2.status_code == 202

    channel_headers = {"x-entity-id": "web", "x-quota-type": "channel", "x-max-req-per-min": "1", "x-max-concurrent": "1", "x-max-tokens-per-hr": "20"}
    first = client.post("/api/prompts/preview", json={"base_prompt": "hello", "variables": {}}, headers=channel_headers)
    second = client.post("/api/prompts/preview", json={"base_prompt": "hello again", "variables": {}}, headers=channel_headers)

    assert first.status_code == 200
    assert second.status_code == 429
