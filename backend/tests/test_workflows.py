import asyncio

import pytest

from app.models.models import Message, Workflow, WorkflowRun, WorkflowRunStep

from .conftest import create_agent


@pytest.fixture(autouse=True)
def _sync_worker_pool(monkeypatch):
    """Make worker_pool.submit execute the function synchronously so tests
    don't have to race against background tasks."""

    async def _submit_sync(_self, _run_id, func, *args, priority=1, **kwargs):
        if asyncio.iscoroutinefunction(func):
            await func(*args, **kwargs)
        else:
            func(*args, **kwargs)
        return True

    monkeypatch.setattr(
        "app.runtime.worker_pool.WorkerPool.submit", _submit_sync
    )

    # Silence event broker publish so tests don't fail on missing subscribers
    async def _noop_publish(_self, _run_id, _event):
        pass

    monkeypatch.setattr(
        "app.agents.executor.RunEventBroker.publish", _noop_publish
    )


def workflow_payload(agent_id):
    return {
        "name": "Test Workflow",
        "description": "A test graph",
        "nodes": [
            {"id": "input", "type": "input", "position": {"x": 0, "y": 0}, "data": {"label": "Input"}},
            {
                "id": "agent",
                "type": "agent",
                "position": {"x": 200, "y": 0},
                "data": {"agent_id": agent_id, "label": "Agent"},
            },
            {"id": "output", "type": "output", "position": {"x": 400, "y": 0}, "data": {"label": "Output"}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "agent"},
            {"id": "e2", "source": "agent", "target": "output"},
        ],
        "is_template": False,
    }


def test_create_workflow(client, db):
    agent = create_agent(client)
    response = client.post("/workflows", json=workflow_payload(agent["id"]))

    assert response.status_code == 201
    assert db.query(Workflow).filter(Workflow.name == "Test Workflow").one()


def test_workflow_template(client):
    response = client.get("/workflows", params={"templates_only": True})

    assert response.status_code == 200
    names = {workflow["name"] for workflow in response.json()}
    assert "Research & Summarize" in names
    assert "Customer Support Router" in names


def test_workflow_execution(client, db, monkeypatch):
    agent = create_agent(client)
    workflow = client.post("/workflows", json=workflow_payload(agent["id"])).json()

    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: "workflow result",
    )
    response = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input_data": {"input": "go"}},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert db.query(Message).filter(Message.workflow_run_id == run_id).count() >= 2
    assert db.query(WorkflowRunStep).filter(WorkflowRunStep.workflow_run_id == run_id).count() == 3


def test_workflow_condition_routes_and_checkpoints(client, db, monkeypatch):
    first = create_agent(client, {"name": "Billing Agent", "role": "Billing", "system_prompt": "Handle billing.", "model": "gpt-4o-mini", "tools": [], "channels": ["web"], "memory_enabled": True, "guardrails": {}, "schedule": None})
    second = create_agent(client, {"name": "Tech Agent", "role": "Tech", "system_prompt": "Handle tech.", "model": "gpt-4o-mini", "tools": [], "channels": ["web"], "memory_enabled": True, "guardrails": {}, "schedule": None})
    payload = {
        "name": "Conditional Workflow",
        "description": "Routes by priority",
        "nodes": [
            {"id": "input", "type": "input", "position": {"x": 0, "y": 0}, "data": {"label": "Input"}},
            {"id": "condition", "type": "condition", "position": {"x": 100, "y": 0}, "data": {"expression": "input.priority == 'high'"}},
            {"id": "billing", "type": "agent", "position": {"x": 200, "y": 0}, "data": {"agent_id": first["id"], "label": "Billing"}},
            {"id": "tech", "type": "agent", "position": {"x": 200, "y": 100}, "data": {"agent_id": second["id"], "label": "Tech"}},
            {"id": "output", "type": "output", "position": {"x": 300, "y": 0}, "data": {"label": "Output"}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "condition"},
            {"id": "e2", "source": "condition", "target": "billing", "sourceHandle": "true"},
            {"id": "e3", "source": "condition", "target": "tech", "sourceHandle": "false"},
            {"id": "e4", "source": "billing", "target": "output"},
            {"id": "e5", "source": "tech", "target": "output"},
        ],
        "is_template": False,
    }
    workflow = client.post("/workflows", json=payload).json()
    monkeypatch.setattr(
        "app.agents.runtime.AgentRuntime.execute_single_agent",
        lambda self, agent_id, task_description: f"agent-{agent_id}",
    )

    response = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input_data": {"priority": "high"}},
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    step_ids = {
        step.step_id
        for step in db.query(WorkflowRunStep).filter(WorkflowRunStep.workflow_run_id == run_id)
    }
    assert "billing" in step_ids
    assert "tech" not in step_ids


def test_conditional_workflow_pauses_and_resumes_with_checkpoint(client, db):
    payload = {
        "name": "Conditional Pause",
        "description": "Pause at a condition and resume from the saved context.",
        "nodes": [
            {"id": "input", "type": "input", "position": {"x": 0, "y": 0}, "data": {"label": "Input"}},
            {
                "id": "condition",
                "type": "condition",
                "position": {"x": 200, "y": 0},
                "data": {
                    "label": "Approved?",
                    "expression": "input.approved == True",
                    "pause_on_condition": True,
                },
            },
            {"id": "yes", "type": "output", "position": {"x": 400, "y": 0}, "data": {"label": "Yes"}},
            {"id": "no", "type": "output", "position": {"x": 400, "y": 120}, "data": {"label": "No"}},
        ],
        "edges": [
            {"id": "e1", "source": "input", "target": "condition"},
            {"id": "e2", "source": "condition", "target": "yes", "sourceHandle": "true"},
            {"id": "e3", "source": "condition", "target": "no", "sourceHandle": "false"},
        ],
        "is_template": False,
    }
    workflow_response = client.post("/workflows", json=payload)
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()

    run_response = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input_data": {"approved": True, "payload": "keep me"}},
    )

    assert run_response.status_code == 202
    run_id = run_response.json()["run_id"]
    db.expire_all()
    run = db.get(WorkflowRun, run_id)
    assert run.status == "paused"

    condition_step = (
        db.query(WorkflowRunStep)
        .filter(WorkflowRunStep.workflow_run_id == run_id, WorkflowRunStep.step_id == "condition")
        .one()
    )
    assert condition_step.status == "paused"
    assert condition_step.context_snapshot["input"]["payload"] == "keep me"
    assert condition_step.context_snapshot["condition_result"] is True

    resume_response = client.post(
        f"/api/workflows/{workflow['id']}/resume",
        json={"run_id": run_id},
    )

    assert resume_response.status_code == 202
    db.expire_all()
    resumed = db.get(WorkflowRun, run_id)
    assert resumed.status == "completed"
    assert resumed.steps[-1].step_id == "yes"
    assert resumed.steps[-1].context_snapshot["input"]["payload"] == "keep me"


def test_workflow_validation(client):
    invalid = {
        "name": "Cyclic Workflow",
        "description": "Bad graph",
        "nodes": [
            {"id": "a", "type": "agent", "position": {"x": 0, "y": 0}, "data": {"agent_id": 1}},
            {"id": "b", "type": "agent", "position": {"x": 0, "y": 0}, "data": {"agent_id": 1}},
        ],
        "edges": [
            {"id": "ab", "source": "a", "target": "b"},
            {"id": "ba", "source": "b", "target": "a"},
        ],
        "is_template": False,
    }

    response = client.post("/workflows", json=invalid)

    assert response.status_code == 422
    assert "cycle" in response.text
