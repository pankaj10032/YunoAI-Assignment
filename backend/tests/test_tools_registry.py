import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.app import app
from app.tools.registry import BaseTool, CalculatorTool, MemoryTool, SearchTool, ToolRegistry, tool_registry


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_tool_list_endpoint_returns_builtin_tools(client: TestClient):
    response = client.get("/api/tools/list")
    assert response.status_code == 200
    names = [tool["name"] for tool in response.json()]
    assert "memory" in names
    assert "web_search" in names


def test_tool_reload_endpoint_loads_custom_plugin(client: TestClient):
    response = client.post("/api/tools/reload")
    assert response.status_code == 200
    payload = response.json()
    assert "tools" in payload
    assert any(tool["name"] == "calculator_plus" for tool in payload["tools"])


def test_global_tool_registry_can_execute_custom_plugin():
    result = tool_registry.execute_tool("calculator_plus", "2+2")
    assert result.get("result") == "4"


def test_invalid_tool_is_rejected_by_registry(tmp_path: Path):
    bad_tool = tmp_path / "InvalidTool.py"
    bad_tool.write_text(
        textwrap.dedent(
            """
            from app.tools.registry import BaseTool

            class InvalidTool(BaseTool):
                name = 'invalid_tool'
                description = 'Missing execute implementation'
            """
        )
    )

    registry = ToolRegistry(custom_dir=tmp_path)
    registry.register(SearchTool, builtin=True)
    registry.register(CalculatorTool, builtin=True)
    registry.register(MemoryTool, builtin=True)
    result = registry.reload()

    assert "invalid_tool" not in [tool["name"] for tool in result["tools"]]
    assert result["errors"]
    assert any("execute" in err["error"] for err in result["errors"])


def test_tool_execution_timeout_and_output_limit(tmp_path: Path):
    class SlowEmitter(BaseTool):
        name = "slow_emitter"
        description = "Sleeps and emits a long string."
        input_schema = {"type": "string"}

        def execute(self, params):
            import time

            time.sleep(0.1)
            return "a" * 20

    registry = ToolRegistry(custom_dir=tmp_path)
    registry.register(SearchTool, builtin=True)
    registry.register(CalculatorTool, builtin=True)
    registry.register(MemoryTool, builtin=True)
    registry.register(SlowEmitter)

    timeout_result = registry.execute_tool("slow_emitter", "anything", limits={"timeout": 0.01})
    assert timeout_result["error"]["type"] == "timeout"

    length_result = registry.execute_tool("slow_emitter", "anything", limits={"max_output": 5})
    assert length_result["result"] == "aaaaa..."


def test_openapi_loader_and_mcp_discovery():
    from app.tools.ecosystem import tool_ecosystem
    # Test OpenAPI spec mapping
    spec = {
        "paths": {
            "/weather": {
                "get": {
                    "operationId": "get_weather",
                    "summary": "Retrieve weather info"
                }
            }
        }
    }
    tool_ecosystem.discover_openapi(spec, "https://api.weather.com")
    tool = tool_registry.get("get_weather")
    assert tool is not None
    assert tool.name == "get_weather"

    # Test MCP mapping
    tool_ecosystem.discover_mcp("http://localhost:5000")
    mcp_tool = tool_registry.get("mcp_weather")
    assert mcp_tool is not None
    assert mcp_tool.name == "mcp_weather"
