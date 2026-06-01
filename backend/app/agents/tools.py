from __future__ import annotations

from typing import Any

from app.tools.registry import MemoryTool, tool_registry


def load_tools(tool_config: list[dict[str, Any]] | dict[str, Any] | None, memory_enabled: bool = True):
    configured = tool_config or []
    if isinstance(configured, dict):
        configured = configured.get("enabled", [])

    tools = []
    for item in configured:
        tool_name = item.get("name") if isinstance(item, dict) else str(item)
        tool_cls = tool_registry.get(str(tool_name).lower())
        if tool_cls:
            tools.append(tool_cls())

    if memory_enabled and not any(isinstance(tool, MemoryTool) for tool in tools):
        memory_cls = tool_registry.get("memory")
        if memory_cls:
            tools.append(memory_cls())

    return tools
