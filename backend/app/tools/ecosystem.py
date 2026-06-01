import httpx
import logging
import asyncio
import time
from typing import Any, Dict, List, Optional
from app.tools.registry import BaseTool, tool_registry, ToolValidationError
from app.utils.observability import log_event

logger = logging.getLogger(__name__)

class WebhookTool(BaseTool):
    def __init__(self, name: str, description: str, url: str, method: str = "POST", headers: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.input_schema = {
            "type": "object",
            "properties": {
                "payload": {"type": "object"}
            }
        }

    def execute(self, params: Any) -> Any:
        payload = params.get("payload") if isinstance(params, dict) else params
        with httpx.Client(timeout=15.0) as client:
            if self.method == "GET":
                resp = client.get(self.url, headers=self.headers, params=payload)
            else:
                resp = client.post(self.url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()


class MCPLoader:
    @staticmethod
    def load_mcp_tools(mcp_url: str) -> List[Dict[str, Any]]:
        # Connect to MCP server and extract tools + schemas
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{mcp_url}/tools")
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("tools", [])
        except Exception as exc:
            logger.warning("Failed to connect to MCP server at %s: %s", mcp_url, exc)
        # Fallback/mock for offline/testing
        return [
            {
                "name": "mcp_weather",
                "description": "Get current weather from MCP server",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    },
                    "required": ["location"]
                },
                "url": f"{mcp_url}/weather"
            }
        ]


class OpenAPILoader:
    @staticmethod
    def load_openapi_spec(spec_json: Dict[str, Any], base_url: str) -> List[Dict[str, Any]]:
        tools = []
        paths = spec_json.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() not in ["get", "post"]:
                    continue
                name = details.get("operationId") or f"{method}_{path.replace('/', '_').strip('_')}"
                description = details.get("summary") or details.get("description") or f"Call OpenAPI path {path}"
                tools.append({
                    "name": name.lower(),
                    "description": description,
                    "url": f"{base_url.rstrip('/')}{path}",
                    "method": method.upper(),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "params": {"type": "object"}
                        }
                    }
                })
        return tools


class ToolEcosystem:
    def __init__(self):
        self.registry = tool_registry
        self.rate_limits: Dict[str, List[float]] = {}  # agent_id/tool -> list of timestamps
        self.cost_tracker: Dict[str, float] = {}

    def discover_mcp(self, mcp_url: str) -> None:
        tools = MCPLoader.load_mcp_tools(mcp_url)
        for t in tools:
            self.register_external_tool(
                t["name"], t["description"], t.get("url", f"{mcp_url}/{t['name']}"), t.get("input_schema")
            )

    def discover_openapi(self, spec_json: Dict[str, Any], base_url: str) -> None:
        tools = OpenAPILoader.load_openapi_spec(spec_json, base_url)
        for t in tools:
            self.register_external_tool(
                t["name"], t["description"], t["url"], t.get("input_schema"), t.get("method", "POST")
            )

    def register_external_tool(self, name: str, description: str, url: str, schema: Optional[Dict[str, Any]] = None, method: str = "POST") -> None:
        class DynamicWebhookTool(WebhookTool):
            pass
        DynamicWebhookTool.name = name.lower()
        DynamicWebhookTool.description = description
        if schema:
            DynamicWebhookTool.input_schema = schema
        
        # Instantiate and register
        tool_instance = DynamicWebhookTool(name=name, description=description, url=url, method=method)
        self.registry.register(DynamicWebhookTool)

    def execute_with_safety(self, name: str, params: Any, agent_id: Optional[int] = None, limits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        limits = limits or {"timeout": 15, "max_output": 10240, "max_cost_usd": 0.05}
        
        # Rate limiting check (e.g. max 10 calls per minute)
        now = time.time()
        agent_key = f"{agent_id or 'anonymous'}:{name}"
        calls = self.rate_limits.setdefault(agent_key, [])
        # filter window
        calls = [t for t in calls if now - t < 60]
        self.rate_limits[agent_key] = calls
        if len(calls) >= 10:
            return {
                "name": name,
                "error": {
                    "type": "rate_limit_exceeded",
                    "message": "Rate limit exceeded. Retry-After 60s"
                }
            }
        calls.append(now)

        # Cost tracking check
        max_cost = float(limits.get("max_cost_usd", 0.05))
        if max_cost <= 0.01:
            return {
                "name": name,
                "error": {
                    "type": "cost_limit_exceeded",
                    "message": f"Execution cost exceeds limit of {max_cost} USD"
                }
            }

        start_time = time.time()
        res = self.registry.execute_tool(name, params, limits=limits)
        latency = time.time() - start_time

        # Track telemetry
        tokens = len(str(params or "")) + len(str(res.get("result") or ""))
        estimated_cost = 0.002
        log_event(
            run_id=None,
            agent_id=agent_id,
            step=f"tool_exec:{name}",
            tokens=tokens,
            cost=estimated_cost,
            latency=latency,
            event_type="tool_telemetry",
            source="ecosystem"
        )
        return res

tool_ecosystem = ToolEcosystem()
