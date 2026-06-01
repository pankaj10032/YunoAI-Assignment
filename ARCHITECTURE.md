# Architecture — AI Orchestrator

This document provides a component-level description of the AI Orchestrator system.

---

## System Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (React)                         │
│                                                                 │
│  ┌────────────────────┐  ┌───────────────────┐                 │
│  │   WorkflowBuilder  │  │  DashboardAnalytics│                 │
│  │ (React Flow canvas)│  │ (recharts + CSV)   │                 │
│  └────────┬───────────┘  └───────────────────┘                 │
│           │                                                     │
│  ┌────────▼──────────────────────────────────────────────────┐  │
│  │              useWorkflowStream(runId)                     │  │
│  │     WebSocket · exponential back-off · local log queue    │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────┐  ┌───────────────────┐                 │
│  │   ErrorBoundary    │  │   ToastProvider   │                 │
│  │ → POST /telemetry  │  │ (slide-in, dedupe)│                 │
│  └────────────────────┘  └───────────────────┘                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ HTTP REST + WebSocket
┌─────────────────────────────────▼───────────────────────────────┐
│                          FastAPI App                            │
│                                                                 │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                     Middleware Stack                     │  │
│   │  CorrelationIDMiddleware → CORSMiddleware → RateLimiter  │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│   ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│   │  Agents API   │  │ Workflows API│  │  Schedules API   │    │
│   └───────┬───────┘  └──────┬───────┘  └────────┬─────────┘    │
│           └─────────────────┼───────────────────┘              │
│                      ┌──────▼──────┐                           │
│                      │ WorkerPool  │                           │
│                      │ (priority   │                           │
│                      │  queue)     │                           │
│                      └──────┬──────┘                           │
│              ┌──────────────┴──────────────┐                   │
│         ┌────▼────┐               ┌────────▼──────┐            │
│         │Executor │               │ ToolEcosystem │            │
│         │(CrewAI) │               │  (sandbox)    │            │
│         └────┬────┘               └────────┬──────┘            │
│              └──────────────┬──────────────┘                   │
│                      ┌──────▼──────┐                           │
│                      │  P2P Router │                           │
│                      │ (ACK/retry/ │                           │
│                      │  DLQ)       │                           │
│                      └──────┬──────┘                           │
│                      ┌──────▼──────┐                           │
│                      │ Telemetry   │                           │
│                      │ Service     │                           │
│                      │ (async buf) │                           │
│                      └──────┬──────┘                           │
└─────────────────────────────┼───────────────────────────────────┘
                              │ SQLAlchemy
                   ┌──────────▼──────────┐
                   │   SQLite / Postgres  │
                   │  agents             │
                   │  workflows          │
                   │  workflow_runs      │
                   │  workflow_run_steps │
                   │  messages           │
                   │  agent_messages     │
                   │  dlq                │
                   │  telemetry_events   │
                   └─────────────────────┘
```

---

## Component Details

### Frontend

#### `useWorkflowStream(runId)`
- Opens a WebSocket to `/ws/run/{runId}`.
- Reconnects with exponential back-off (cap: 30 s, base: 500 ms).
- Local log queue: messages sent while disconnected are flushed on reconnect.
- Returns `{ connected, events, sendLocal }`.

#### `WorkflowBuilder`
- Built on **React Flow v11+**.
- Node types: `agent`, `condition`, `input`, `output`.
- Inline validation runs on every change:
  - **Cycle detection**: depth-first search over the adjacency list.
  - **Orphan detection**: agent nodes with no incoming edges.
  - **Invalid edges**: edges referencing non-existent node IDs.
- Validation errors highlighted in red with tooltip messages.

#### `ScheduleConfig`
- Cron expression validated with 5-field rule.
- Timezone list from `Intl.supportedValuesOf('timeZone')` (≈ 600 entries).
- Next 5 fire times computed client-side from cron fields.

#### `ToastProvider`
- Context-based global toast system.
- Types: `success`, `error`, `info`, `warning`.
- Deduplication within 2.5 s windows.
- Auto-dismiss after 5 s; manual close button.
- `toastSlideIn` CSS animation.

#### `ErrorBoundary`
- React class component catching render errors.
- Reports to `POST /api/telemetry` (fire-and-forget) with:
  - `error_id`, `message`, truncated `stack`, `component_stack`, `url`, `timestamp`.
- Retry button resets component tree; Reload button reloads page.

#### `DashboardAnalytics`
- Dual-area recharts chart: token usage (left Y-axis) + cost in USD (right Y-axis).
- CSV export via `Blob` + dynamic `<a>` download.
- Total summary badges.

---

### Backend

#### `CorrelationIDMiddleware`
- Starlette `BaseHTTPMiddleware`.
- Reads `X-Correlation-ID` header; generates `uuid4().hex` if absent.
- Writes to `request.state.correlation_id` and structured logging context.
- Echoes back in response `X-Correlation-ID` header.

#### `TelemetryService` (`services/telemetry.py`)
- Module-level `deque` + `threading.Lock` for thread-safe enqueueing.
- Background daemon thread (`telemetry-flush`) flushes to DB:
  - Every `FLUSH_INTERVAL = 5.0` seconds, **or**
  - Immediately when queue depth ≥ `FLUSH_BATCH_SIZE = 50`.
- Uses `bulk_save_objects` for efficient batch inserts.
- Failed batches are re-enqueued for the next cycle.
- All payloads sanitised via `observability.sanitize_value`.

#### `WorkerPool` (`runtime/worker_pool.py`)
- Three priority queues: **0=High** (direct agent calls), **1=Normal** (workflows), **2=Low** (schedules).
- Up to `max_workers=5` concurrent `asyncio.Task`s.
- **Circuit breaker**: after 5 consecutive failures, enters `OPEN` state for 60 s cooldown, then `HALF_OPEN`.
- Step checkpointing: serialises intermediate state so runs can be resumed.
- Graceful shutdown via `asyncio.Event`.

#### `ToolEcosystem` (`tools/ecosystem.py`)
- **MCPLoader**: connects to MCP servers, fetches `/tools` endpoint, registers as `WebhookTool`s.
- **OpenAPILoader**: parses OpenAPI spec JSON, wraps each `GET`/`POST` path as a tool.
- **WebhookTool**: direct HTTP endpoint wrapper with configurable method/headers.
- `execute_with_safety`: rate-limit check (10 calls/min per agent/tool), cost-limit guard, then delegates to `ToolSandbox`.

#### `ToolSandbox` (`tools/sandbox.py`)
- Thread-pool-backed (`ThreadPoolExecutor`, max 8 workers).
- **Timeout**: 15 s hard limit (configurable).
- **Output cap**: 10 KB; oversized results are truncated with `…[truncated]` marker.
- **PII stripping**: regex removal of API keys, bearer tokens, emails, card numbers, SSNs.
- **Cost tracking**: `(agent_id, tool_name) → cumulative_usd`.

#### `P2P MessageRouter` (`messaging/p2p_router.py`)
- `AgentDirectory`: tracks agent status (`idle`, `busy`, `offline`).
- `SessionManager`: per-session sequence numbers; stores sessions in `agent_messages`.
- Reliable delivery: max 3 retry attempts with exponential back-off.
- Undeliverable messages moved to `DeadLetterMessage` (DLQ table).
- Background worker runs as an `asyncio.Task` started in the app lifespan.

---

## Data Flow: Workflow Run

```
User clicks "Run"
      │
      ▼
POST /api/workflows/{id}/run
      │
      ▼
create_workflow_run(db) → WorkflowRun(status="pending")
      │
      ▼
worker_pool.submit(run.id, execute_workflow_background, ..., priority=1)
      │
      ▼  (async, in background worker task)
execute_workflow_background(run_id, workflow_id, input_data, correlation_id)
      │
      ├─► For each node in topological order:
      │       AgentExecutor.run(agent, task)
      │           └─► LLM call (streaming)
      │           └─► Tool calls → ToolSandbox.execute()
      │           └─► log_event(telemetry)
      │           └─► event_broker.publish(run_id, step_event)  ← WebSocket
      │
      └─► WorkflowRun(status="completed"|"failed")
```

---

## Database Schema (key tables)

| Table | Purpose |
|---|---|
| `agents` | Agent configuration, schedule, tools |
| `workflows` | Workflow definitions (nodes + edges JSON) |
| `workflow_runs` | Execution instances with status and token totals |
| `workflow_run_steps` | Per-node step status, output, and checkpoints |
| `messages` | LLM message history per run |
| `agent_messages` | P2P messages with ACK/retry tracking |
| `dlq` | Dead-letter queue for permanently failed messages |
| `telemetry_events` | Structured telemetry events (usage, errors, tool calls) |
| `scheduler_missed_runs` | APScheduler missed-run records |
