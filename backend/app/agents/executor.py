from __future__ import annotations

import asyncio
import logging
from queue import Queue
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.agents.runtime import AgentRuntime
from app.audit.trail import record_event
from app.memory.graph import add_message_node
from app.models.database import SessionLocal
from app.models.models import Agent, Message, Workflow, WorkflowRun
from app.utils.observability import get_request_context, set_request_context, log_event
from app.workflows.engine import WorkflowPaused, execute_workflow


class RunEventBroker:
    def __init__(self):
        self._subscribers: dict[int, set[Queue]] = {}

    async def subscribe(self, run_id: int) -> Queue:
        queue: Queue = Queue()
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    async def unsubscribe(self, run_id: int, queue: Queue) -> None:
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    async def publish(self, run_id: int, event: dict[str, Any]) -> None:
        for queue in self._subscribers.get(run_id, set()).copy():
            queue.put(event)


event_broker = RunEventBroker()


async def stream_run_events(websocket: WebSocket, run_id: int):
    await websocket.accept()
    queue = await event_broker.subscribe(run_id)
    try:
        await websocket.send_json({"type": "connected", "run_id": run_id})
        while True:
            event = await asyncio.to_thread(queue.get)
            await websocket.send_json(event)
            if event.get("type") in {"completed", "failed", "paused"}:
                break
    finally:
        await event_broker.unsubscribe(run_id, queue)


def create_workflow_run(
    db: Session,
    workflow_id: int,
    input_data: dict[str, Any] | None = None,
) -> WorkflowRun:
    run = WorkflowRun(
        workflow_id=workflow_id,
        status="pending",
        started_at=datetime.now(timezone.utc),
        input_data=input_data or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_agent_background(
    run_id: int,
    agent_id: int,
    task_description: str,
    correlation_id: str | None = None,
) -> None:
    _run_coroutine(_execute_agent(run_id, agent_id, task_description, correlation_id))


def execute_workflow_background(
    run_id: int,
    workflow_id: int,
    input_data: dict[str, Any],
    correlation_id: str | None = None,
) -> None:
    _run_coroutine(_execute_workflow(run_id, workflow_id, input_data, None, correlation_id))


def resume_workflow_background(
    run_id: int,
    workflow_id: int,
    input_data: dict[str, Any],
    resume_from_step: str | None = None,
    correlation_id: str | None = None,
) -> None:
    _run_coroutine(_execute_workflow(run_id, workflow_id, input_data, resume_from_step, correlation_id))


def _run_coroutine(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    if loop.is_running():
        future = asyncio.ensure_future(coro)
        if future.done() and future.exception():
            raise future.exception()
        return

    loop.run_until_complete(coro)


async def _execute_agent(
    run_id: int,
    agent_id: int,
    task_description: str,
    correlation_id: str | None = None,
) -> None:
    set_request_context(correlation_id=correlation_id, run_id=str(run_id), agent_id=str(agent_id), step="agent_execute")
    logger = logging.getLogger(__name__)
    logger.info("agent execution started", extra={"agent_id": agent_id, "run_id": run_id, "step": "agent_execute"})
    db = SessionLocal()
    try:
        run = db.get(WorkflowRun, run_id)
        agent = db.get(Agent, agent_id)
        if not run or not agent:
            raise ValueError("Run or agent not found")
        record_event("agent_start", {"task_description": task_description}, {"agent_id": agent_id, "run_id": run_id, "correlation_id": correlation_id}, db=db)

        await _mark_running(db, run, f"Executing agent {agent.name}", agent_id)
        runtime = AgentRuntime(db)
        record_event("decision_point", {"action": "execute_single_agent", "task_description": task_description}, {"agent_id": agent_id, "run_id": run_id, "correlation_id": correlation_id}, db=db)
        result = await asyncio.to_thread(runtime.execute_single_agent, agent_id, task_description)
        _persist_message(db, run_id, agent_id, None, "internal", result)
        record_event("completion", {"result": result}, {"agent_id": agent_id, "run_id": run_id, "correlation_id": correlation_id}, db=db)
        await _mark_completed(db, run, result)
    except Exception as exc:
        record_event("error", {"error": str(exc)}, {"agent_id": agent_id, "run_id": run_id, "correlation_id": correlation_id}, db=db)
        await _mark_failed(db, run_id, exc)
    finally:
        db.close()


async def _execute_workflow(
    run_id: int,
    workflow_id: int,
    input_data: dict[str, Any],
    resume_from_step: str | None = None,
    correlation_id: str | None = None,
) -> None:
    set_request_context(correlation_id=correlation_id, run_id=str(run_id), step=resume_from_step or "workflow_execute")
    logger = logging.getLogger(__name__)
    logger.info(
        "workflow execution started",
        extra={"run_id": run_id, "step": resume_from_step or "workflow_execute"},
    )
    db = SessionLocal()
    try:
        run = db.get(WorkflowRun, run_id)
        workflow = db.get(Workflow, workflow_id)
        if not run or not workflow:
            raise ValueError("Run or workflow not found")
        record_event("agent_start", {"workflow": workflow.name}, {"run_id": run_id, "correlation_id": correlation_id}, db=db)

        await _mark_running(db, run, f"Executing workflow {workflow.name}", None)
        result = await asyncio.to_thread(
            execute_workflow,
            workflow.id,
            input_data,
            resume_from_step,
            run.id,
        )
        _persist_message(db, run_id, None, None, "internal", result)
        record_event("completion", {"result": result}, {"run_id": run_id, "correlation_id": correlation_id}, db=db)
        await _mark_completed(db, run, result)
    except WorkflowPaused as exc:
        record_event("decision_point", {"paused_at": exc.step_id}, {"run_id": run_id, "correlation_id": correlation_id}, db=db)
        await _mark_paused(db, run_id, exc.step_id)
    except Exception as exc:
        record_event("error", {"error": str(exc)}, {"run_id": run_id, "correlation_id": correlation_id}, db=db)
        await _mark_failed(db, run_id, exc)
    finally:
        db.close()


async def _mark_running(db: Session, run: WorkflowRun, message: str, agent_id: int | None) -> None:
    run.status = "running"
    run.started_at = run.started_at or datetime.now(timezone.utc)
    db.commit()
    _persist_message(db, run.id, agent_id, None, "internal", message)
    record_event("message_sent", {"message": message}, {"agent_id": agent_id, "run_id": run.id}, db=db)
    await event_broker.publish(run.id, {"type": "log", "run_id": run.id, "message": message})


async def _mark_completed(db: Session, run: WorkflowRun, result: str) -> None:
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    usage = _estimate_usage(result)
    run.total_tokens = usage["tokens"]
    run.total_cost = usage["cost"]
    db.commit()
    record_event("completion", {"usage": usage, "result": result}, {"run_id": run.id}, db=db)
    try:
        log_event(run_id=run.id, step="completed", tokens=usage.get("tokens"), cost=usage.get("cost"))
    except Exception:
        pass
    await event_broker.publish(
        run.id,
        {
            "type": "completed",
            "run_id": run.id,
            "message": "Execution completed",
            "result": result,
            "usage": usage,
        },
    )


async def _mark_paused(db: Session, run_id: int, step_id: str) -> None:
    run = db.get(WorkflowRun, run_id)
    if run:
        run.status = "paused"
        db.commit()
    message = f"Workflow paused at step {step_id}"
    _persist_message(db, run_id, None, None, "internal", message)
    await event_broker.publish(
        run_id,
        {"type": "paused", "run_id": run_id, "message": message, "step_id": step_id},
    )


async def _mark_failed(db: Session, run_id: int, exc: Exception) -> None:
    run = db.get(WorkflowRun, run_id)
    if run:
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
    message = str(exc)
    _persist_message(db, run_id, None, None, "internal", f"Execution failed: {message}")
    await event_broker.publish(
        run_id,
        {"type": "failed", "run_id": run_id, "message": message},
    )


def _persist_message(
    db: Session,
    run_id: int,
    sender_agent_id: int | None,
    receiver_agent_id: int | None,
    channel: str,
    content: str,
) -> Message:
    usage = _estimate_usage(content)
    message = Message(
        workflow_run_id=run_id,
        sender_agent_id=sender_agent_id,
        receiver_agent_id=receiver_agent_id,
        channel=channel,
        content=content,
        message_metadata={**usage, "correlation_id": get_request_context().get("correlation_id")},
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    try:
        add_message_node(message, db=db)
    except Exception:
        pass
    # queue telemetry entry for the message (batched flush)
    try:
        meta = message.message_metadata or {}
        log_event(run_id=message.workflow_run_id, agent_id=message.sender_agent_id, step="message_sent", tokens=meta.get("tokens"), cost=meta.get("cost"))
    except Exception:
        pass
    return message


def _estimate_usage(text: str) -> dict[str, Any]:
    tokens = max(1, len(text.split()) * 2)
    return {
        "tokens": tokens,
        "cost": round(tokens * 0.00000015, 8),
        "estimated": True,
    }
