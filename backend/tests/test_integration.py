import concurrent.futures

from app.models.models import Message

from .conftest import create_agent
from .test_workflows import workflow_payload


def test_end_to_end_workflow(client, db, monkeypatch):
    first = create_agent(client, {**_agent("Agent One"), "channels": ["web", "telegram"]})
    second = create_agent(client, _agent("Agent Two"))
    payload = workflow_payload(first["id"])
    payload["nodes"].insert(
        2,
        {
            "id": "agent-two",
            "type": "agent",
            "position": {"x": 300, "y": 0},
            "data": {"agent_id": second["id"], "label": "Agent Two"},
        },
    )
    payload["edges"] = [
        {"id": "e1", "source": "input", "target": "agent"},
        {"id": "e2", "source": "agent", "target": "agent-two"},
        {"id": "e3", "source": "agent-two", "target": "output"},
    ]
    workflow = client.post("/workflows", json=payload).json()

    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_workflow",
        lambda self, nodes, edges, input_data: "telegram to agent chain response",
    )
    response = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input_data": {"channel": "telegram", "input": "hello"}},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert db.query(Message).filter(Message.workflow_run_id == run_id).count() >= 2


def test_concurrent_runs(client, monkeypatch):
    agent = create_agent(client, _agent("Concurrent Agent"))
    workflow = client.post("/workflows", json=workflow_payload(agent["id"])).json()
    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_workflow",
        lambda self, nodes, edges, input_data: "concurrent result",
    )

    def run_once():
        return client.post(
            f"/api/workflows/{workflow['id']}/run",
            json={"input_data": {"input": "parallel"}},
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        statuses = list(executor.map(lambda _: run_once(), range(3)))

    assert statuses == [202, 202, 202]


def _agent(name):
    return {
        "name": name,
        "role": "Integration Agent",
        "system_prompt": "Participate in integration tests.",
        "model": "gpt-4o-mini",
        "tools": [{"name": "memory"}],
        "channels": ["web"],
        "memory_enabled": True,
        "guardrails": {},
        "schedule": None,
    }
