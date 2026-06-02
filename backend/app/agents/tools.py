from __future__ import annotations

from typing import Any

from app.tools.registry import MemoryTool, tool_registry


def load_tools(tool_config: list[dict[str, Any]] | dict[str, Any] | None, memory_enabled: bool = True):
    configured = tool_config or []
    if isinstance(configured, dict):
        configured = configured.get("enabled", [])

    app_tools = []
    for item in configured:
        tool_name = item.get("name") if isinstance(item, dict) else str(item)
        tool_cls = tool_registry.get(str(tool_name).lower())
        if tool_cls:
            app_tools.append(tool_cls())

    if memory_enabled and not any(isinstance(tool, MemoryTool) for tool in app_tools):
        memory_cls = tool_registry.get("memory")
        if memory_cls:
            app_tools.append(memory_cls())

    try:
        from crewai.tools import BaseTool as CrewBaseTool
        
        crew_tools = []
        for t in app_tools:
            # Dynamically create a subclass of CrewBaseTool
            class WrapperTool(CrewBaseTool):
                name: str = t.name
                description: str = t.description
                _local_tool: Any = t
                
                def _run(self, *args, **kwargs) -> Any:
                    if args:
                        return self._local_tool.execute(args[0])
                    if kwargs:
                        return self._local_tool.execute(kwargs)
                    return self._local_tool.execute("")
                    
            crew_tools.append(WrapperTool())
        return crew_tools
    except ImportError:
        return app_tools

