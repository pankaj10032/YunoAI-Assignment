from app.channels.manager import channel_manager
from app.channels.telegram import _upsert_telegram_channel
from app.models.models import Agent, Message, Workflow, WorkflowRun

from .conftest import create_agent


def test_telegram_message(client, monkeypatch):
    monkeypatch.setattr("app.app.settings.telegram_bot_token", "test-token")
    agent = create_agent(client, {**_payload(), "channels": ["telegram", "web"]})

    response = client.post(
        "/api/channels/telegram/connect",
        json={"agent_id": agent["id"], "chat_id": "12345"},
    )

    assert response.status_code == 200
    assert any(
        isinstance(channel, dict) and channel["name"] == "telegram" and channel["chat_id"] == "12345"
        for channel in response.json()["channels"]
    )


def test_message_persistence(db):
    agent = Agent(
        name="Persist Agent",
        role="Tester",
        system_prompt="Persist",
        model="gpt-4o-mini",
        tools=[],
        channels=["web"],
        guardrails={},
    )
    db.add(agent)
    db.flush()
    workflow = Workflow(name="Persist Workflow", nodes=[], edges=[])
    db.add(workflow)
    db.flush()
    run = WorkflowRun(workflow_id=workflow.id, status="running")
    db.add(run)
    db.flush()
    db.add(
        Message(
            workflow_run_id=run.id,
            sender_agent_id=agent.id,
            channel="internal",
            content="stored message",
            message_metadata={"tokens": 2},
        )
    )
    db.commit()

    assert db.query(Message).filter(Message.content == "stored message").count() == 1


def test_channel_routing(db):
    agent = Agent(
        name="Routed Agent",
        role="Router",
        system_prompt="Route",
        model="gpt-4o-mini",
        tools=[],
        channels=_upsert_telegram_channel(["telegram"], "777"),
        guardrails={},
    )
    db.add(agent)
    db.commit()

    routed = channel_manager.find_agent_for_channel(db, "telegram", "777")

    assert routed.id == agent.id


def _payload():
    return {
        "name": "Telegram Agent",
        "role": "Chat Agent",
        "system_prompt": "Reply to Telegram users.",
        "model": "gpt-4o-mini",
        "tools": [{"name": "memory"}],
        "memory_enabled": True,
        "guardrails": {},
        "schedule": None,
    }
