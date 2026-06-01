# Extension Guide — AI Orchestrator

This guide shows how to extend the AI Orchestrator platform by:

1. [Adding new tools](#1-adding-new-tools)
2. [Creating custom workflow node types](#2-creating-custom-workflow-node-types)
3. [Building new UI pages and hooks](#3-building-new-ui-pages-and-hooks)
4. [Deploying to production](#4-deploying-to-production)

---

## 1. Adding New Tools

The tool ecosystem supports three integration patterns: **webhook**, **MCP server**, and **OpenAPI spec**.

### 1a. Webhook Tool (simplest)

Register any HTTP endpoint as a tool:

```python
# backend/app/tools/ecosystem.py  (or a new file imported at startup)
from app.tools.ecosystem import tool_ecosystem

tool_ecosystem.register_external_tool(
    name="send_slack_message",
    description="Post a message to a Slack channel via webhook",
    url="https://hooks.slack.com/services/T000/B000/xxxx",
    method="POST",
    schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Message text"},
            "channel": {"type": "string"}
        },
        "required": ["text"]
    }
)
```

Call it from the FastAPI startup lifespan or a dedicated `tools/custom/slack.py` file imported there.

### 1b. MCP Server

Point the ecosystem loader at any running MCP server:

```python
tool_ecosystem.discover_mcp("http://localhost:3333")
```

The loader calls `GET /tools` on the server, parses the returned tool list, and registers each tool as a `WebhookTool`. If the server is offline, a fallback mock is used so the system stays operational.

### 1c. OpenAPI Spec

Fetch or load an OpenAPI JSON spec and register all endpoints:

```python
import httpx, json
from app.tools.ecosystem import tool_ecosystem

spec = httpx.get("https://petstore.swagger.io/v2/swagger.json").json()
tool_ecosystem.discover_openapi(spec, base_url="https://petstore.swagger.io/v2")
```

Every `GET` / `POST` operation becomes a callable tool named after its `operationId`.

### 1d. Native Python Tool (BaseTool subclass)

For maximum control, subclass `BaseTool` directly:

```python
# backend/app/tools/custom/my_tool.py
from app.tools.registry import BaseTool, tool_registry

class MyCustomTool(BaseTool):
    name = "my_custom_tool"
    description = "Does something amazing"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }

    def execute(self, params):
        query = params.get("query", "")
        # … your logic here …
        return {"result": f"Processed: {query}"}

tool_registry.register(MyCustomTool)
```

Import this module in the `lifespan` function in `app.py` (or anywhere before `tool_registry.reload()` is called).

### Sandbox limits

All tools executed via `ToolEcosystem.execute_with_safety()` pass through `ToolSandbox`:

| Limit | Default | Override |
|---|---|---|
| Timeout | 15 s | Pass `limits={"timeout": N}` |
| Output size | 10 KB | Pass `limits={"max_output": N}` |
| Cost cap | $0.10 | Pass `limits={"max_cost_usd": N}` |
| Rate limit | 10 calls/min | Hard-coded per agent/tool |

---

## 2. Creating Custom Workflow Node Types

### 2a. Backend — register node handling

In `backend/app/agents/executor.py`, the executor switches on `node["type"]`. Add a new branch:

```python
elif node_type == "my_node":
    result = await execute_my_node(node, context, db)
```

Implement `execute_my_node` returning a string result and updating the step status.

### 2b. Frontend — new React Flow node

Create `frontend/src/components/nodes/MyNode.jsx`:

```jsx
import React from "react";
import { Handle, Position } from "@xyflow/react";

export default function MyNode({ data, selected }) {
  return (
    <div className={`node-card ${selected ? "node-card--selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-label">{data.label}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
```

Register in `WorkflowBuilder.jsx`:

```jsx
import MyNode from "./nodes/MyNode";

const nodeTypes = {
  agent: AgentNode,
  condition: ConditionNode,
  input: InputNode,
  output: OutputNode,
  my_node: MyNode,   // ← add this
};
```

Add to `NodePalette.jsx` so users can drag it onto the canvas:

```jsx
{ type: "my_node", label: "My Custom Node", icon: "⚡" }
```

---

## 3. Building New UI Pages and Hooks

### 3a. New Page

Create `frontend/src/pages/MyPage.jsx`:

```jsx
import React from "react";
import ErrorBoundary from "../components/ErrorBoundary";

export default function MyPage() {
  return (
    <ErrorBoundary>
      <div className="page-container">
        <h1>My New Page</h1>
      </div>
    </ErrorBoundary>
  );
}
```

Add the route in `App.jsx`:

```jsx
const MyPage = lazy(() => import("./pages/MyPage"));

// Inside <Routes>:
<Route path="/my-page" element={<MyPage />} />
```

Add a nav link in `Layout.jsx`.

### 3b. New Hook

Follow the pattern of `useWorkflowStream`:

```js
// frontend/src/hooks/useMyData.js
import { useEffect, useState } from "react";
import { api } from "../services/api";

export function useMyData(id) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.get(`/api/my-resource/${id}`)
      .then((res) => setData(res.data))
      .finally(() => setLoading(false));
  }, [id]);

  return { data, loading };
}
```

### 3c. Using Toast in any component

```jsx
import { useToast } from "../components/ToastProvider";

function MyButton() {
  const toast = useToast();
  return (
    <button onClick={() => toast.success("Action completed!", "All data saved.")}>
      Save
    </button>
  );
}
```

---

## 4. Deploying to Production

### 4a. Docker Compose (simplest)

```bash
cp .env.example .env
# Set DATABASE_URL to postgres://user:pass@host:5432/dbname
# Set OPENAI_API_KEY

docker compose -f docker-compose.yml up --build -d
```

### 4b. Fly.io

```bash
fly launch --name ai-orchestrator-backend --dockerfile backend/Dockerfile
fly secrets set OPENAI_API_KEY=sk-...
fly deploy
```

Repeat for the frontend or serve the Vite build as static files via nginx.

### 4c. Production checklist

- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Use PostgreSQL (`DATABASE_URL=postgresql://...`)
- [ ] Run Alembic migrations instead of `create_all()` (see `README.md`)
- [ ] Set `CORS_ORIGINS` to your actual frontend domain
- [ ] Configure HTTPS / TLS termination (nginx, Caddy, or cloud load balancer)
- [ ] Set `LOG_LEVEL=WARNING` and ship logs to a structured log aggregator
- [ ] Enable health-check probes on `/health`
- [ ] Add a secrets manager (Vault, AWS Secrets Manager) for API keys

---

## Telemetry Integration

Every new subsystem should emit telemetry events:

```python
from app.services.telemetry import log_event

log_event(
    event_type="my_subsystem_event",
    source="my_module",
    payload={"key": "value"},
    run_id=run.id,
    agent_id=agent.id,
)
```

Events are batched asynchronously and searchable via:

```
GET /api/logs/search?correlation_id=<id>
```
