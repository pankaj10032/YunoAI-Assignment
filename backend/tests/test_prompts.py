from app.agents.runtime import AgentRuntime
from app.models.models import Agent, Message, Workflow, WorkflowRun
from app.prompts.template import render_template

from .conftest import create_agent


def test_prompt_preview_matches_renderer(client):
    payload = {
        "base_prompt": "Hello {{user_context}} {{memory_summary}} {{guardrail_rules}} {{current_time}}",
        "variables": {
            "user_context": "world",
            "memory_summary": "memo",
            "guardrail_rules": {"tone": "concise"},
            "current_time": "2026-05-30T12:00:00Z",
        },
    }

    response = client.post("/api/prompts/preview", json=payload)

    assert response.status_code == 200
    assert response.json()["rendered_prompt"] == render_template(
        payload["base_prompt"],
        payload["variables"],
    )


def test_agent_execution_injects_memory_summary(client, db, monkeypatch):
    agent = create_agent(
        client,
        {
            "name": "Prompt Agent",
            "role": "Prompt Runner",
            "system_prompt": "Use memory: {{memory_summary}} | Context: {{user_context}}",
            "model": "gpt-4o-mini",
            "tools": [{"name": "memory"}],
            "channels": ["web"],
            "memory_enabled": True,
            "guardrails": {"context_window": 2000, "tone": "careful"},
            "schedule": None,
        },
    )
    db.add(
        Message(
            workflow_run_id=_seed_run(db),
            sender_agent_id=agent["id"],
            channel="internal",
            content="previous memory note",
            message_metadata={"tokens": 2},
        )
    )
    db.commit()

    seen = {}

    def fake_create_crewai_agent(self, agent_model, prompt=None):
        seen["prompt"] = prompt
        return object()

    monkeypatch.setattr("app.agents.runtime.AgentRuntime.create_crewai_agent", fake_create_crewai_agent)
    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.create_task",
        lambda self, agent, goal, description: {"goal": goal, "description": description},
    )
    monkeypatch.setattr(
        "app.agents.runtime.Crew",
        lambda **kwargs: type("CrewStub", (), {"kickoff": lambda self, inputs=None: "ok"})(),
    )
    monkeypatch.setattr("app.agents.runtime.Process", type("ProcessStub", (), {"sequential": "sequential"}))

    runtime = AgentRuntime(db)
    runtime.execute_single_agent(agent["id"], "please process this")

    assert "previous memory note" in seen["prompt"]
    assert "please process this" in seen["prompt"]
    assert "context_window" not in seen["prompt"]


def test_prompt_render_truncates_large_prompt():
    rendered = render_template(
        "Start {{user_context}} middle {{memory_summary}} end {{guardrail_rules}} {{current_time}}",
        {
            "user_context": "alpha " * 3000,
            "memory_summary": "beta " * 3000,
            "guardrail_rules": {"max_tokens": 10},
            "current_time": "2026-05-30T12:00:00Z",
            "context_window": 120,
        },
    )

    assert "Prompt was truncated" in rendered
    assert len(rendered.split()) <= 500


def _seed_run(db):
    workflow = Workflow(name="Prompt Workflow", nodes=[], edges=[])
    db.add(workflow)
    db.flush()
    run = WorkflowRun(workflow_id=workflow.id, status="running")
    db.add(run)
    db.commit()
    return run.id
