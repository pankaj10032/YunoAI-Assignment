import time

from app.agents.tools import load_tools
from app.models.database import SessionLocal
from app.models.models import Agent, Message

from .conftest import create_agent


def test_create_agent(client, db, agent_payload):
    response = client.post("/agents", json=agent_payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == agent_payload["name"]
    assert db.query(Agent).filter(Agent.name == agent_payload["name"]).one()


def test_update_agent(client, db):
    agent = create_agent(client)

    response = client.put(
        f"/agents/{agent['id']}",
        json={"role": "Updated Helper", "memory_enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "Updated Helper"
    assert response.json()["memory_enabled"] is False


def test_delete_agent(client, db):
    agent = create_agent(client)

    response = client.delete(f"/agents/{agent['id']}")

    assert response.status_code == 204
    assert db.get(Agent, agent["id"]) is None


def test_agent_execution(client, db, monkeypatch):
    agent = create_agent(client)

    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: "agent result",
    )
    response = client.post(
        f"/api/agents/{agent['id']}/execute",
        json={"task_description": "Summarize the test"},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    messages = []
    for _ in range(50):
        db.expire_all()
        messages = db.query(Message).filter(Message.workflow_run_id == run_id).all()
        if any(message.content == "agent result" for message in messages):
            break
        time.sleep(0.05)
    assert any(message.content == "agent result" for message in messages)


def test_agent_with_tools(client, db, monkeypatch):
    payload = {
        "name": "Search Agent",
        "role": "Searcher",
        "system_prompt": "Search and answer.",
        "model": "gpt-4o-mini",
        "tools": [{"name": "search"}, {"name": "calculator"}],
        "channels": ["web"],
        "memory_enabled": True,
        "guardrails": {},
        "schedule": None,
    }
    agent = create_agent(client, payload)
    tools = load_tools(payload["tools"], memory_enabled=True)

    assert {tool.name for tool in tools} >= {"web_search", "calculator", "memory"}

    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: "tool-assisted result",
    )
    response = client.post(
        f"/api/agents/{agent['id']}/execute",
        json={"task_description": "Use available tools"},
    )
    assert response.status_code == 202


def test_generate_agent_config(client, monkeypatch):
    monkeypatch.setattr("app.agents.generator.settings.openai_api_key", None)

    response = client.post(
        "/api/agents/generate",
        json={
            "prompt": "A cybersecurity analyst agent that scans code snippets for vulnerabilities and suggests patches"
        },
    )

    assert response.status_code == 200
    config = response.json()["config"]
    assert config["model"] == "gpt-4o-mini"
    assert config["channels"] == ["web"]
    assert config["memory_enabled"] is True
    assert config["name"]
    assert any(tool["name"] in ("search", "web_search") for tool in config["tools"])
