# AI Orchestrator

AI Orchestrator is a local-first platform for creating, configuring, and running collaborative AI agents. The challenge build uses FastAPI, CrewAI, SQLite, React, React Flow, Telegram Bot API, and Docker Compose.

## Quick Start

1. Copy environment variables:

   ```bash
   cp .env.example .env
   ```

2. Add an `OPENAI_API_KEY` to `.env`, or set `LLM_PROVIDER=ollama` and run Ollama locally.

3. Start the stack:

   ```bash
   docker compose up --build
   ```

4. Open the apps:

   - Frontend: http://localhost:3000
   - Backend health: http://localhost:8000/health
   - API docs: http://localhost:8000/docs

## Project Structure

```text
ai-orchestrator/
  backend/
    app/
      agents/
      channels/
      models/
      utils/
      workflows/
      config.py
      app.py
    tests/
    Dockerfile
    requirements.txt
  frontend/
    public/
    src/
      components/
      pages/
      services/
      App.jsx
    Dockerfile
    package.json
  docker-compose.yml
```

## Current Scope

This first milestone provides production-oriented scaffolding, container setup, environment loading, CORS, a backend health endpoint, and a React shell ready for the workflow builder and management UI.
