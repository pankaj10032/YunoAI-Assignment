# AI Orchestrator

> **Production-ready agentic orchestration platform** — build, schedule, monitor, and extend multi-agent AI workflows with real-time observability.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Running Tests](#running-tests)
- [Database Migrations](#database-migrations)
- [Extending the Platform](#extending-the-platform)

---

## Overview

AI Orchestrator is a local-first platform for creating, configuring, and running collaborative AI agents. It combines FastAPI, React + React Flow, SQLite/PostgreSQL, APScheduler, and Docker Compose into a single cohesive system.

Key differentiators over the first-milestone scaffold:

- **Real-time execution visibility** via WebSocket streams with auto-reconnect
- **Inline workflow validation** (cycle detection, orphan nodes, invalid edges)
- **Full tool ecosystem** (MCP servers, OpenAPI specs, webhooks) with sandboxed execution
- **Structured telemetry** with async buffering, PII sanitisation, and correlation ID tracing
- **Production-grade worker pool** with priority queues, circuit breaker, and step checkpointing

---

## Features

| Category | Details |
|---|---|
| **Real-time streaming** | WebSocket per run (`/ws/run/{run_id}`) with exponential back-off auto-reconnect and local log queue |
| **Workflow validation** | Cycle + orphan + invalid-edge detection — inline UI + `POST /api/workflows/validate` |
| **Schedule config** | Cron expression UI with full IANA timezone list (via `Intl.supportedValuesOf`) and next-5-run preview |
| **Error boundaries** | React `ErrorBoundary` reports crashes to `/api/telemetry` with correlation ID |
| **Toast notifications** | Slide-in toasts (success / error / info / warning) with deduplication and auto-dismiss |
| **Dashboard analytics** | Dual-area chart (tokens + cost) with CSV export |
| **Structured telemetry** | Async-buffered, PII-sanitised events flushed to DB every 5 s or 50 events |
| **Correlation IDs** | `X-Correlation-ID` propagated: HTTP middleware → log context → DB rows |
| **Tool sandbox** | 15 s timeout, 10 KB output cap, PII stripping, per-agent cost tracking |
| **P2P messaging** | ACK/NAK persistence, retry queue (max 3 attempts), Dead Letter Queue |
| **Worker pool** | Priority queues (High / Normal / Low), circuit breaker, step-level checkpointing |

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   React Frontend (Vite)                │
│  WorkflowBuilder · DashboardAnalytics · ToastProvider  │
│  useWorkflowStream(runId) — WebSocket auto-reconnect   │
└───────────────────────┬────────────────────────────────┘
                        │ REST + WebSocket
┌───────────────────────▼────────────────────────────────┐
│                  FastAPI Backend                        │
│  CorrelationIDMiddleware → QuotaLimiterMiddleware       │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │   Agents    │  │  Workflows  │  │   Scheduler   │  │
│  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘  │
│         └────────────────┼─────────────────┘          │
│                    WorkerPool (priority queue)         │
│                    ┌──────┴──────┐                     │
│               Executor      ToolEcosystem              │
│                              └── ToolSandbox           │
│                    └──────┬──────┘                     │
│                  P2P MessageRouter                      │
│                  TelemetryService (async buffer)        │
└───────────────────────┬────────────────────────────────┘
                        │ SQLAlchemy ORM
                   SQLite / PostgreSQL
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for component-level details.

---

## Quick Start

### Prerequisites

- **Python ≥ 3.11**
- **Node.js ≥ 18**
- An OpenAI API key (or any compatible LLM endpoint)

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env        # add OPENAI_API_KEY
docker compose up --build
```

- Frontend: **http://localhost:3000**
- Backend API docs: **http://localhost:8000/docs**

### Option B — Local dev (no Docker)

**Backend:**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
uvicorn app.app:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

---

## Project Structure

```text
ai-orchestrator/
  backend/
    app/
      agents/         ← agent executor, generator
      channels/       ← Telegram, web channel integrations
      messaging/      ← P2P router, message bus
      middleware/     ← CorrelationIDMiddleware, rate limiter
      models/         ← SQLAlchemy ORM + Pydantic schemas
      runtime/        ← worker pool, circuit breaker
      scheduler/      ← APScheduler engine
      services/       ← telemetry async service
      tools/          ← registry, ecosystem, sandbox
      utils/          ← observability, structured logging
      workflows/      ← templates, validators
      app.py          ← FastAPI application entry point
    tests/
    requirements.txt
    Dockerfile
  frontend/
    src/
      components/     ← WorkflowBuilder, DashboardAnalytics, ToastProvider, ErrorBoundary …
      hooks/          ← useWorkflowStream, useRunStream
      pages/          ← DashboardPage, WorkflowsPage, Monitor …
      services/       ← api.js
    package.json
    Dockerfile
  docker-compose.yml
  ARCHITECTURE.md
  EXTENSION_GUIDE.md
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | **Required** for LLM calls |
| `DATABASE_URL` | `sqlite:///./orchestrator.db` | SQLAlchemy connection string |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed CORS origins (JSON array) |
| `TELEGRAM_BOT_TOKEN` | — | Optional Telegram bot integration |
| `ENABLE_TELEGRAM_POLLING` | `false` | Enable Telegram polling mode |
| `LOG_LEVEL` | `INFO` | Python `logging` level |
| `ENVIRONMENT` | `development` | `development` or `production` |

---

## API Reference

Full interactive docs: **http://localhost:8000/docs**

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/agents/{id}/execute` | Execute an agent (async — returns `run_id`) |
| `POST` | `/api/workflows` | Create a workflow |
| `POST` | `/api/workflows/{id}/run` | Start a workflow run |
| `POST` | `/api/workflows/validate` | Validate workflow JSON (`{valid, errors}`) |
| `GET` | `/api/runs/{id}` | Get run status & metadata |
| `WS` | `/ws/run/{id}` | Real-time run events stream |
| `POST` | `/api/telemetry` | Ingest UI-side telemetry (ErrorBoundary, etc.) |
| `GET` | `/api/logs/search?correlation_id=…` | Search structured logs by correlation ID |
| `GET` | `/api/runtime/status` | Worker pool health & queue depths |
| `POST` | `/api/messaging/send` | Send a P2P message between agents |

---

## Running Tests

```bash
# Backend
cd backend
pytest -v

# Frontend
cd frontend
npm test
```

---

## Database Migrations

The project uses SQLAlchemy `create_all()` for dev convenience. For production use [Alembic](https://alembic.sqlalchemy.org/).

**Dev reset** (when adding/removing columns in SQLite):

```bash
# Windows
del backend\orchestrator.db
# macOS / Linux
rm backend/orchestrator.db
# Restart the backend — create_all() recreates all tables automatically
```

---

## Extending the Platform

See [EXTENSION_GUIDE.md](./EXTENSION_GUIDE.md) for step-by-step guides on:

- Adding MCP / OpenAPI / webhook tools
- Creating custom workflow node types in React Flow
- Building new UI pages and hooks
- Deploying to production (Render, Fly.io, Docker Swarm)
