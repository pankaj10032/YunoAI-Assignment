from contextlib import asynccontextmanager
import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, WebSocket, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.middleware.correlation_id import CorrelationIDMiddleware
from app.services.telemetry import log_event as telemetry_log_event
from sqlalchemy.orm import Session

from app.config import settings
from app.agents.executor import (
    create_workflow_run,
    event_broker,
    execute_agent_background,
    execute_workflow_background,
    resume_workflow_background,
    stream_run_events,
)
from app.agents.generator import GenerationError, generate_agent_config
from app.channels.manager import channel_manager
from app.channels.telegram import telegram_channel
from app.audit.trail import install_immutability_guards, record_event, run_timeline
from app.middleware.limiter import QuotaLimiterMiddleware, quota_status
from app.messaging.bus import consumer_loop, get_message_history, queue_stats, stream_bus_messages
from app.memory.graph import add_agent_state, cleanup_loop, serialize_graph
from app.models.database import create_all_tables, get_db
from app.models.models import Agent, Message, TelemetryEvent, Workflow, WorkflowRun, AgentMessage
from app.prompts.template import invalidate_template_cache, preview_prompt
from app.scheduler.engine import SchedulerEngine
from app.tools.registry import tool_registry
from app.runtime.worker_pool import worker_pool
from app.messaging.p2p_router import MessageRouter, p2p_background_worker
from app.models.schemas import (
    AgentCreate,
    AgentExecuteRequest,
    AgentGenerateRequest,
    AgentResponse,
    AgentUpdate,
    PromptPreviewRequest,
    PromptPreviewResponse,
    RunAcceptedResponse,
    ScheduleStatusItem,
    ScheduleStatusResponse,
    ScheduleToggleRequest,
    TelegramConnectRequest,
    TelegramStatusResponse,
    MessageResponse,
    AgentMessageHistoryResponse,
    WorkflowCreate,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowResumeRequest,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.validators import ValidationError, validate_agent_config, validate_workflow
from app.workflows.templates import seed_workflow_templates
from app.utils.observability import (
    StructuredJSONFormatter,
    get_request_context,
    new_correlation_id,
    sanitize_value,
    search_log_entries,
    set_request_context,
)


logging.basicConfig(
    level=settings.log_level,
)
for handler in logging.getLogger().handlers:
    handler.setFormatter(StructuredJSONFormatter())
logger = logging.getLogger(__name__)
_agent_generation_requests: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Orchestrator API in %s mode", settings.environment)
    create_all_tables()
    install_immutability_guards()
    from app.models.database import SessionLocal

    db = SessionLocal()
    try:
        seed_workflow_templates(db)
    finally:
        db.close()
    if settings.telegram_bot_token:
        try:
            telegram_channel.initialize(settings.telegram_bot_token)
            await telegram_channel.start_webhook(app)
            channel_manager.register_channel("telegram", telegram_channel)
            if settings.enable_telegram_polling:
                telegram_channel.polling_task = asyncio.create_task(
                    telegram_channel.start_polling()
                )
            logger.info("Telegram channel initialized")
        except Exception as exc:
            logger.exception("Telegram channel initialization failed: %s", exc)
    app.state.message_queue_stop = asyncio.Event()
    tool_registry.reload()
    app.state.message_queue_task = asyncio.create_task(
        consumer_loop(app.state.message_queue_stop)
    )
    app.state.memory_cleanup_stop = asyncio.Event()
    app.state.memory_cleanup_task = asyncio.create_task(
        cleanup_loop(app.state.memory_cleanup_stop, interval_sec=30.0)
    )
    # Start P2P worker
    app.state.p2p_stop = asyncio.Event()
    app.state.p2p_task = asyncio.create_task(
        p2p_background_worker(app.state.p2p_stop)
    )
    worker_pool.start()
    app.state.scheduler = SchedulerEngine()
    # await app.state.scheduler.start()
    logger.info("Database schema initialized")
    yield
    try:
        await app.state.scheduler.shutdown()
    except Exception:
        logger.exception("Scheduler shutdown failed")
    app.state.message_queue_stop.set()
    app.state.message_queue_task.cancel()
    app.state.memory_cleanup_stop.set()
    app.state.memory_cleanup_task.cancel()
    app.state.p2p_stop.set()
    app.state.p2p_task.cancel()
    try:
        await app.state.message_queue_task
    except asyncio.CancelledError:
        pass
    try:
        await app.state.memory_cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await app.state.p2p_task
    except asyncio.CancelledError:
        pass
    await worker_pool.shutdown()
    if telegram_channel.connected:
        await telegram_channel.disconnect()
    logger.info("Shutting down AI Orchestrator API")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API for creating, configuring, and orchestrating collaborative AI agents.",
    lifespan=lifespan,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or new_correlation_id()
    set_request_context(correlation_id=correlation_id)
    logger.info(
        "request received",
        extra={
            "correlation_id": correlation_id,
            "step": request.url.path,
            "agent_id": request.path_params.get("agent_id") if hasattr(request, "path_params") else None,
        },
    )
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(QuotaLimiterMiddleware)
app.add_middleware(CorrelationIDMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("Unhandled application error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(_, exc: ValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors},
    )


@app.post("/api/telemetry", tags=["observability"])
async def ingest_telemetry(request: Request):
    """Accept UI-side telemetry events (e.g. ErrorBoundary crash reports)."""
    try:
        body = await request.json()
        telemetry_log_event(
            event_type=body.get("event_type", "ui_event"),
            source=body.get("source", "frontend"),
            payload=body.get("payload", {}),
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        return {"status": "queued"}
    except Exception as exc:
        logger.warning("Telemetry ingest error: %s", exc)
        return JSONResponse(status_code=400, content={"error": str(exc)})


@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


# Root endpoint removed to allow React frontend serving from `/`


@app.get("/api/tools/list", tags=["tools"])
async def list_tools():
    return tool_registry.list()


@app.post("/api/tools/reload", tags=["tools"])
async def reload_tools():
    return tool_registry.reload()


@app.post(
    "/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    validate_agent_config(payload.model_dump())
    agent = Agent(**payload.model_dump())
    db.add(agent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent named '{payload.name}' already exists",
        ) from exc
    db.refresh(agent)
    invalidate_template_cache(f"agent:{agent.id}")
    add_agent_state(agent, db=db)
    return agent


@app.post(
    "/api/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["agents"],
)
async def create_agent_api(payload: AgentCreate, db: Session = Depends(get_db)):
    """API endpoint for creating agents - delegates to create_agent logic"""
    validate_agent_config(payload.model_dump())
    agent = Agent(**payload.model_dump())
    db.add(agent)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent named '{payload.name}' already exists",
        ) from exc
    db.refresh(agent)
    invalidate_template_cache(f"agent:{agent.id}")
    add_agent_state(agent, db=db)
    return agent


@app.post("/api/agents/generate", tags=["agents"])
async def generate_agent(payload: AgentGenerateRequest, request: Request):
    client_id = request.client.host if request.client else "unknown"
    if not _allow_generation_request(client_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many generation requests. Please wait a minute and try again.",
        )
    try:
        result = generate_agent_config(payload.prompt)
        return {"config": result["config"]}
    except GenerationError as exc:
        logger.warning("Agent generation failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Failed to generate valid config"},
        )


@app.get("/agents", response_model=list[AgentResponse], tags=["agents"])
async def list_agents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(Agent).order_by(Agent.created_at.desc()).offset(skip).limit(limit).all()


@app.get("/api/agents", response_model=list[AgentResponse], tags=["agents"])
async def list_agents_api(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return await list_agents(skip=skip, limit=limit, db=db)


def _allow_generation_request(client_id: str) -> bool:
    now = time.monotonic()
    window_start = now - 60
    recent = [
        requested_at
        for requested_at in _agent_generation_requests.get(client_id, [])
        if requested_at >= window_start
    ]
    if len(recent) >= 5:
        _agent_generation_requests[client_id] = recent
        return False
    recent.append(now)
    _agent_generation_requests[client_id] = recent
    return True


@app.get("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
@app.get("/api/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
async def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


@app.put("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
@app.put("/api/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
async def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    validate_agent_config(
        {
            "name": agent.name,
            "model": agent.model,
            "channels": agent.channels,
            "guardrails": agent.guardrails,
        }
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent name already exists",
        ) from exc
    db.refresh(agent)
    invalidate_template_cache(f"agent:{agent.id}")
    add_agent_state(agent, db=db)
    return agent


@app.get("/api/schedules/status", response_model=ScheduleStatusResponse, tags=["schedules"])
async def schedule_status():
    return {"schedules": app.state.scheduler.get_schedule_status()}


@app.post("/api/schedules/pause", response_model=ScheduleStatusItem, tags=["schedules"])
async def pause_schedule(payload: ScheduleToggleRequest):
    try:
        return app.state.scheduler.pause_agent_schedule(payload.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@app.post("/api/schedules/resume", response_model=ScheduleStatusItem, tags=["schedules"])
async def resume_schedule(payload: ScheduleToggleRequest):
    try:
        return app.state.scheduler.resume_agent_schedule(payload.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["agents"])
@app.delete("/api/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["agents"])
async def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    db.delete(agent)
    db.commit()
    return None


@app.post(
    "/api/agents/{agent_id}/execute",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["runtime"],
)
async def execute_agent(
    agent_id: int,
    payload: AgentExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    agent_ref = agent.id
    workflow = Workflow(
        name=f"Direct run: {agent.name}",
        description="Ephemeral workflow created for a direct agent execution.",
        nodes=[
            {
                "id": f"agent-{agent.id}",
                "type": "agent",
                "data": {"agent_id": agent.id, "label": agent.name},
                "position": {"x": 0, "y": 0},
            }
        ],
        edges=[],
        is_template=False,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    run = create_workflow_run(db, workflow.id, {"task_description": payload.task_description})
    record_event(
        "agent_start",
        {"task_description": payload.task_description},
        {"agent_id": agent_ref, "run_id": run.id},
        db=db,
    )
    background_tasks_placeholder = background_tasks  # keep signature
    submitted = await worker_pool.submit(
        run.id,
        execute_agent_background,
        run.id,
        agent_ref,
        payload.task_description,
        get_request_context().get("correlation_id"),
        priority=0
    )
    if not submitted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution queue is full. Please try again later."
        )
    return {
        "run_id": run.id,
        "status": run.status,
        "websocket_url": f"/ws/run/{run.id}",
    }


@app.post(
    "/api/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["workflows"],
)
@app.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["workflows"],
)
async def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    validate_workflow(payload.nodes, payload.edges)
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


@app.post("/api/workflows/validate", tags=["workflows"])
async def validate_workflow_endpoint(payload: WorkflowCreate):
    try:
        validate_workflow(payload.nodes, payload.edges)
        return {"valid": True, "errors": []}
    except ValidationError as exc:
        return {"valid": False, "errors": exc.errors}


@app.get("/api/workflows", response_model=list[WorkflowResponse], tags=["workflows"])
@app.get("/workflows", response_model=list[WorkflowResponse], tags=["workflows"])
async def list_workflows(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    templates_only: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Workflow)
    if templates_only:
        query = query.filter(Workflow.is_template.is_(True))
    return query.order_by(Workflow.created_at.desc()).offset(skip).limit(limit).all()


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["workflows"])
@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["workflows"])
async def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    return workflow


@app.put("/api/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["workflows"])
@app.put("/workflows/{workflow_id}", response_model=WorkflowResponse, tags=["workflows"])
async def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workflow, field, value)
    validate_workflow(workflow.nodes, workflow.edges)

    db.commit()
    db.refresh(workflow)
    return workflow


@app.delete(
    "/api/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["workflows"],
)
@app.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["workflows"],
)
async def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    db.delete(workflow)
    db.commit()
    return None


@app.post(
    "/api/workflows/{workflow_id}/run",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["runtime"],
)
async def run_workflow(
    workflow_id: int,
    payload: WorkflowRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    run = create_workflow_run(db, workflow.id, payload.input_data)
    record_event(
        "decision_point",
        {"workflow_id": workflow.id, "input_data": sanitize_value(payload.input_data)},
        {"run_id": run.id},
        db=db,
    )
    background_tasks_placeholder = background_tasks  # keep signature
    submitted = await worker_pool.submit(
        run.id,
        execute_workflow_background,
        run.id,
        workflow.id,
        payload.input_data,
        get_request_context().get("correlation_id"),
        priority=1
    )
    if not submitted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution queue is full. Please try again later."
        )
    return {
        "run_id": run.id,
        "status": run.status,
        "websocket_url": f"/ws/run/{run.id}",
    }


@app.post(
    "/api/workflows/{workflow_id}/resume",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["runtime"],
)
async def resume_workflow(
    workflow_id: int,
    payload: WorkflowResumeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    run = db.get(WorkflowRun, payload.run_id)
    if not run or run.workflow_id != workflow.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    if run.status not in {"paused", "failed", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only paused, failed, or interrupted workflow runs can be resumed",
        )

    background_tasks_placeholder = background_tasks  # keep signature
    submitted = await worker_pool.submit(
        run.id,
        resume_workflow_background,
        run.id,
        workflow.id,
        run.input_data or {},
        payload.resume_from_step,
        get_request_context().get("correlation_id"),
        priority=1
    )
    if not submitted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution queue is full. Please try again later."
        )
    return {
        "run_id": run.id,
        "status": run.status,
        "websocket_url": f"/ws/run/{run.id}",
    }


@app.post(
    "/api/runs/{run_id}/rerun",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["runtime"],
)
async def rerun_workflow(
    run_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    original = db.get(WorkflowRun, run_id)
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    workflow = db.get(Workflow, original.workflow_id)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    replay_input = original.input_data or {}
    run = create_workflow_run(db, workflow.id, replay_input)
    background_tasks_placeholder = background_tasks  # keep signature
    submitted = await worker_pool.submit(
        run.id,
        execute_workflow_background,
        run.id,
        workflow.id,
        replay_input,
        get_request_context().get("correlation_id"),
        priority=1
    )
    if not submitted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution queue is full. Please try again later."
        )
    return {
        "run_id": run.id,
        "status": run.status,
        "websocket_url": f"/ws/run/{run.id}",
    }


@app.post("/api/runs/{run_id}/stop", tags=["runtime"])
async def stop_workflow_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    if run.status not in {"pending", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending or running workflow runs can be stopped",
        )
    run.status = "paused"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    await event_broker.publish(
        run.id,
        {"type": "paused", "run_id": run.id, "message": "Run stopped by user"},
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "websocket_url": f"/ws/run/{run.id}",
    }


@app.get("/api/runs/{run_id}", response_model=WorkflowRunResponse, tags=["runtime"])
async def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    return run


@app.get("/api/runs", response_model=list[WorkflowRunResponse], tags=["runtime"])
async def list_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(WorkflowRun)
    if status_filter:
        query = query.filter(WorkflowRun.status == status_filter)
    return (
        query.order_by(WorkflowRun.started_at.desc().nullslast(), WorkflowRun.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@app.get(
    "/api/runs/{run_id}/messages",
    response_model=list[MessageResponse],
    tags=["runtime"],
)
async def get_run_messages(run_id: int, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    return (
        db.query(Message)
        .filter(Message.workflow_run_id == run_id)
        .order_by(Message.timestamp.asc())
        .all()
    )


@app.get("/api/messages", response_model=list[MessageResponse], tags=["runtime"])
async def list_messages(
    run_id: int | None = None,
    agent_id: int | None = None,
    channel: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = db.query(Message)
    if run_id:
        query = query.filter(Message.workflow_run_id == run_id)
    if agent_id:
        query = query.filter(
            (Message.sender_agent_id == agent_id) | (Message.receiver_agent_id == agent_id)
        )
    if channel:
        query = query.filter(Message.channel == channel)
    return query.order_by(Message.timestamp.desc()).limit(limit).all()


@app.get("/api/agents/{agent_id}/memory/graph", tags=["memory"])
async def get_agent_memory_graph(agent_id: int, depth: int = Query(default=3, ge=1, le=10), db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return serialize_graph(agent_id, depth=depth, db=db)


@app.get("/api/messaging/queue/stats", tags=["messaging"])
async def messaging_queue_stats(db: Session = Depends(get_db)):
    return queue_stats(db)


@app.get("/api/messaging/history", response_model=list[AgentMessageHistoryResponse], tags=["messaging"])
async def messaging_history(agent_id: int, limit: int = Query(default=200, ge=1, le=1000)):
    return get_message_history(agent_id, limit=limit)


@app.websocket("/ws/messages")
async def message_bus_websocket(websocket: WebSocket, agent_id: int):
    await stream_bus_messages(websocket, agent_id)


@app.get("/api/quotas/status", tags=["quotas"])
async def quota_status_endpoint(
    entity_id: str | None = None,
    type: str | None = None,
    db: Session = Depends(get_db),
):
    return quota_status(entity_id=entity_id, type=type, db=db)


@app.post("/api/prompts/preview", response_model=PromptPreviewResponse, tags=["prompts"])
async def preview_prompt_render(payload: PromptPreviewRequest):
    variables = dict(payload.variables)
    if payload.context_window is not None:
        variables["context_window"] = payload.context_window
    return {"rendered_prompt": preview_prompt(payload.base_prompt, variables)}


@app.websocket("/ws/run/{run_id}")
async def run_log_websocket(websocket: WebSocket, run_id: int):
    await stream_run_events(websocket, run_id)


@app.post("/api/channels/telegram/webhook", tags=["channels"])
async def telegram_webhook(request: Request):
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot token is not configured",
        )
    payload = await request.json()
    try:
        set_request_context(step="telegram_webhook")
        logger.info("telegram webhook received", extra={"payload": sanitize_value(payload)})
        return await telegram_channel.receive(payload)
    except Exception as exc:
        logger.exception("Telegram webhook processing failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Telegram update: {exc}",
        ) from exc


@app.post(
    "/api/channels/telegram/connect",
    response_model=AgentResponse,
    tags=["channels"],
)
async def connect_telegram_agent(payload: TelegramConnectRequest):
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot token is not configured",
        )
    try:
        return await telegram_channel.register_agent(payload.agent_id, payload.chat_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/channels/telegram/status",
    response_model=TelegramStatusResponse,
    tags=["channels"],
)
async def telegram_status():
    channel = channel_manager.get_channel("telegram")
    return channel.status() if channel else telegram_channel.status()


# ── Telegram webhook management ────────────────────────────────────────────────

class TelegramWebhookSetRequest(BaseModel):
    webhook_url: str

class TelegramSendRequest(BaseModel):
    chat_id: str
    text: str




@app.post("/api/channels/telegram/webhook/set", tags=["channels"])
async def telegram_set_webhook(payload: TelegramWebhookSetRequest):
    """Register a webhook URL with the Telegram Bot API."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot token is not configured")
    if not telegram_channel.application:
        raise HTTPException(status_code=503, detail="Telegram channel not initialized")

    try:
        await telegram_channel.set_webhook(payload.webhook_url)
        return {"success": True, "webhook_url": payload.webhook_url}
    except Exception as exc:
        logger.exception("Failed to set Telegram webhook")
        raise HTTPException(status_code=500, detail=f"Failed to set webhook: {exc}") from exc


@app.post("/api/channels/telegram/webhook/delete", tags=["channels"])
async def telegram_delete_webhook():
    """Remove the current Telegram webhook."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot token is not configured")
    if not telegram_channel.application:
        raise HTTPException(status_code=503, detail="Telegram channel not initialized")
    try:
        await telegram_channel.delete_webhook()
        logger.info("Telegram webhook deleted")
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/channels/telegram/webhook/info", tags=["channels"])
async def telegram_webhook_info():
    """Fetch current webhook info from Telegram Bot API."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot token is not configured")
    if not telegram_channel.application:
        raise HTTPException(status_code=503, detail="Telegram channel not initialized")
    try:
        info = await telegram_channel.get_webhook_info()
        return {
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_message": info.last_error_message,
            "last_error_date": _serialize_telegram_timestamp(info.last_error_date),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/channels/telegram/send", tags=["channels"])
async def telegram_send_message(payload: TelegramSendRequest):
    """Send a message to a Telegram chat."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot token is not configured")

    # Ensure telegram channel is initialized and connected
    if not telegram_channel.application:
        try:
            telegram_channel.initialize(settings.telegram_bot_token)
            await telegram_channel.connect()
            logger.info("Telegram channel initialized for send operation")
        except Exception as init_exc:
            logger.exception("Failed to initialize Telegram channel")
            raise HTTPException(status_code=503, detail=f"Telegram channel initialization failed: {str(init_exc)}") from init_exc

    # Ensure the channel is connected
    if not telegram_channel.connected:
        try:
            await telegram_channel.connect()
            logger.info("Telegram channel connected for send operation")
        except Exception as conn_exc:
            logger.exception("Failed to connect Telegram channel")
            raise HTTPException(status_code=503, detail=f"Telegram channel connection failed: {str(conn_exc)}") from conn_exc
    
    try:
        await telegram_channel.send_message(payload.chat_id, payload.text)
        logger.info("Telegram message sent successfully", extra={"chat_id": payload.chat_id})
        return {"ok": True, "chat_id": payload.chat_id, "message": "Message sent successfully"}
    except Exception as exc:
        logger.exception("Failed to send Telegram message", extra={"chat_id": payload.chat_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(exc)}") from exc


def _serialize_telegram_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[return-value]
    return str(value)




@app.get("/api/logs/search", tags=["observability"])
async def search_logs(correlation_id: str = Query(..., min_length=8)):
    from app.models.database import SessionLocal

    db = SessionLocal()
    try:
        telemetry = (
            db.query(TelemetryEvent)
            .filter(TelemetryEvent.payload["correlation_id"].as_string() == correlation_id)
            .order_by(TelemetryEvent.created_at.asc())
            .all()
        )
        db_entries = [
            {
                "type": "telemetry",
                "event_type": event.event_type,
                "source": event.source,
                "payload": sanitize_value(event.payload),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in telemetry
        ]
    finally:
        db.close()
    return {
        "correlation_id": correlation_id,
        "entries": search_log_entries(correlation_id) + db_entries,
    }


@app.get("/api/audit/run/{run_id}", tags=["audit"])
async def audit_run(run_id: int, db: Session = Depends(get_db)):
    return {"run_id": run_id, "events": run_timeline(run_id, db=db)}


# --- Runtime Worker Pool Endpoints ---

@app.get("/api/runtime/status", tags=["runtime"])
async def get_runtime_status():
    return worker_pool.get_status()


@app.post("/api/runtime/pause", tags=["runtime"])
async def pause_runtime():
    worker_pool.paused = True
    return {"status": "paused", "message": "Worker pool execution paused successfully"}


@app.post("/api/runtime/resume", tags=["runtime"])
async def resume_runtime():
    worker_pool.paused = False
    return {"status": "resumed", "message": "Worker pool execution resumed successfully"}


# --- P2P Messaging Endpoints ---


class P2PMessageSendRequest(BaseModel):
    sender: int
    receiver: int
    content: str
    session_id: str | None = None


@app.post("/api/messaging/send", tags=["messaging"])
async def send_p2p_message(payload: P2PMessageSendRequest):
    correlation_id = get_request_context().get("correlation_id") or new_correlation_id()
    msg = await MessageRouter.send_message(
        sender_id=payload.sender,
        receiver_id=payload.receiver,
        content=payload.content,
        session_id=payload.session_id,
        correlation_id=correlation_id
    )
    return {
        "message_id": msg.id,
        "correlation_id": msg.correlation_id,
        "session_id": msg.session_id,
        "status": msg.status
    }


@app.get("/api/messages/session/{session_id}", tags=["messaging"])
async def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    return db.query(AgentMessage).filter(AgentMessage.session_id == session_id).order_by(AgentMessage.created_at.asc()).all()


@app.post("/api/messaging/ack/{message_id}", tags=["messaging"])
async def ack_message(message_id: int):
    success = await MessageRouter.acknowledge_message(message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "acked"}


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Mount static files for assets if they exist (used by Vite)
if os.path.isdir("/app/static/assets"):
    app.mount("/assets", StaticFiles(directory="/app/static/assets"), name="assets")

# Catch-all route to serve the React UI (must be at the end of all other routes)
@app.get("/{full_path:path}", tags=["frontend"])
async def serve_frontend(full_path: str):
    static_dir = "/app/static"
    path = os.path.join(static_dir, full_path)
    if os.path.isfile(path):
        return FileResponse(path)
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
