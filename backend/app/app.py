from contextlib import asynccontextmanager
import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
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
from app.messaging.queue import consumer_loop, queue_stats
from app.memory.graph import add_agent_state, cleanup_loop, serialize_graph
from app.models.database import create_all_tables, get_db
from app.models.models import Agent, Message, TelemetryEvent, Workflow, WorkflowRun
from app.prompts.template import invalidate_template_cache, preview_prompt
from app.models.schemas import (
    AgentCreate,
    AgentExecuteRequest,
    AgentGenerateRequest,
    AgentResponse,
    AgentUpdate,
    PromptPreviewRequest,
    PromptPreviewResponse,
    RunAcceptedResponse,
    TelegramConnectRequest,
    TelegramStatusResponse,
    MessageResponse,
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
    app.state.message_queue_task = asyncio.create_task(
        consumer_loop(app.state.message_queue_stop)
    )
    app.state.memory_cleanup_stop = asyncio.Event()
    app.state.memory_cleanup_task = asyncio.create_task(
        cleanup_loop(app.state.memory_cleanup_stop, interval_sec=30.0)
    )
    logger.info("Database schema initialized")
    yield
    app.state.message_queue_stop.set()
    app.state.message_queue_task.cancel()
    app.state.memory_cleanup_stop.set()
    app.state.memory_cleanup_task.cancel()
    try:
        await app.state.message_queue_task
    except asyncio.CancelledError:
        pass
    try:
        await app.state.memory_cleanup_task
    except asyncio.CancelledError:
        pass
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


@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/", tags=["system"])
async def root():
    return {
        "service": settings.app_name,
        "status": "ok",
        "docs_url": "/docs",
    }


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
async def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


@app.put("/agents/{agent_id}", response_model=AgentResponse, tags=["agents"])
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


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["agents"])
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
    background_tasks.add_task(
        execute_agent_background,
        run.id,
        agent_ref,
        payload.task_description,
        get_request_context().get("correlation_id"),
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
    background_tasks.add_task(
        execute_workflow_background,
        run.id,
        workflow.id,
        payload.input_data,
        get_request_context().get("correlation_id"),
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

    background_tasks.add_task(
        resume_workflow_background,
        run.id,
        workflow.id,
        run.input_data or {},
        payload.resume_from_step,
        get_request_context().get("correlation_id"),
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
    background_tasks.add_task(
        execute_workflow_background,
        run.id,
        workflow.id,
        replay_input,
        get_request_context().get("correlation_id"),
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
