import pytest
from fastapi.testclient import TestClient

from app.app import app
from app.models.database import SessionLocal, create_all_tables
from app.models.models import (
    Agent,
    AgentMessage,
    DeadLetterMessage,
    Message,
    MemoryEdge,
    MemoryNode,
    QuotaCounter,
    TelemetryEvent,
    Workflow,
    WorkflowRun,
    WorkflowRunStep,
)
from app.workflows.templates import seed_workflow_templates


@pytest.fixture()
def db():
    create_all_tables()
    session = SessionLocal()
    session.query(DeadLetterMessage).delete()
    session.query(TelemetryEvent).delete()
    session.query(MemoryEdge).delete()
    session.query(MemoryNode).delete()
    session.query(QuotaCounter).delete()
    session.query(AgentMessage).delete()
    session.query(WorkflowRunStep).delete()
    session.query(Message).delete()
    session.query(WorkflowRun).delete()
    session.query(Workflow).delete()
    session.query(Agent).delete()
    session.commit()
    seed_workflow_templates(session)
    try:
        yield session
    finally:
        session.query(DeadLetterMessage).delete()
        session.query(TelemetryEvent).delete()
        session.query(MemoryEdge).delete()
        session.query(MemoryNode).delete()
        session.query(QuotaCounter).delete()
        session.query(AgentMessage).delete()
        session.query(WorkflowRunStep).delete()
        session.query(Message).delete()
        session.query(WorkflowRun).delete()
        session.query(Workflow).delete()
        session.query(Agent).delete()
        session.commit()
        session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def agent_payload():
    return {
        "name": "Test Researcher",
        "role": "Research Agent",
        "system_prompt": "Research carefully and answer concisely.",
        "model": "gpt-4o-mini",
        "tools": [{"name": "memory"}],
        "channels": ["web"],
        "memory_enabled": True,
        "guardrails": {"tone": "concise"},
        "schedule": None,
    }


def create_agent(client, payload=None):
    response = client.post(
        "/agents",
        json=payload
        or {
            "name": "Helper Agent",
            "role": "Helper",
            "system_prompt": "Help with tasks.",
            "model": "gpt-4o-mini",
            "tools": [{"name": "memory"}],
            "channels": ["web"],
            "memory_enabled": True,
            "guardrails": {},
            "schedule": None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
