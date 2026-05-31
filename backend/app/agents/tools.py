from __future__ import annotations

import ast
import operator
from typing import Any

from app.audit.trail import record_event
from app.utils.observability import get_request_context

try:
    from crewai.tools import BaseTool
except Exception:  # pragma: no cover - lets the API boot if CrewAI is not installed locally
    class BaseTool:  # type: ignore[no-redef]
        name: str = ""
        description: str = ""

        def run(self, *args, **kwargs):
            return self._run(*args, **kwargs)


MEMORY_STORE: dict[str, list[str]] = {}


class SearchTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web for recent information. Input should be a concise query."

    def _run(self, query: str) -> str:
        try:
            record_event(
                "tool_call_start",
                {"tool": self.name, "input": query},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                record_event(
                    "tool_call_end",
                    {"tool": self.name, "output": "No search results found."},
                    {"correlation_id": get_request_context().get("correlation_id")},
                )
                return "No search results found."
            output = "\n".join(
                f"- {item.get('title', 'Untitled')}: {item.get('body', '')} ({item.get('href', '')})"
                for item in results
            )
            record_event(
                "tool_call_end",
                {"tool": self.name, "output": output},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return output
        except Exception as exc:
            record_event(
                "error",
                {"tool": self.name, "error": str(exc)},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return f"Search unavailable: {exc}"


class CalculatorTool(BaseTool):
    name: str = "calculator"
    description: str = "Evaluate basic arithmetic expressions. Supports +, -, *, /, **, %, and parentheses."

    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _run(self, expression: str) -> str:
        try:
            record_event(
                "tool_call_start",
                {"tool": self.name, "input": expression},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            tree = ast.parse(expression, mode="eval")
            output = str(self._eval_node(tree.body))
            record_event(
                "tool_call_end",
                {"tool": self.name, "output": output},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return output
        except Exception as exc:
            record_event(
                "error",
                {"tool": self.name, "error": str(exc)},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return f"Calculation error: {exc}"

    def _eval_node(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](
                self._eval_node(node.left),
                self._eval_node(node.right),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._operators:
            return self._operators[type(node.op)](self._eval_node(node.operand))
        raise ValueError("unsupported expression")


class MemoryTool(BaseTool):
    name: str = "memory"
    description: str = "Store or retrieve short memories. Use 'store: text' or 'retrieve: query'."

    def _run(self, instruction: str) -> str:
        namespace = "default"
        record_event(
            "tool_call_start",
            {"tool": self.name, "input": instruction},
            {"correlation_id": get_request_context().get("correlation_id")},
        )
        if instruction.lower().startswith("store:"):
            value = instruction.split(":", 1)[1].strip()
            MEMORY_STORE.setdefault(namespace, []).append(value)
            output = "Memory stored."
            record_event(
                "tool_call_end",
                {"tool": self.name, "output": output},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return output
        if instruction.lower().startswith("retrieve:"):
            query = instruction.split(":", 1)[1].strip().lower()
            matches = [
                item
                for item in MEMORY_STORE.get(namespace, [])
                if query in item.lower() or not query
            ]
            output = "\n".join(matches[-5:]) if matches else "No matching memories found."
            record_event(
                "tool_call_end",
                {"tool": self.name, "output": output},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return output
        output = "Use 'store: text' or 'retrieve: query'."
        record_event(
            "tool_call_end",
            {"tool": self.name, "output": output},
            {"correlation_id": get_request_context().get("correlation_id")},
        )
        return output


TOOL_REGISTRY = {
    "search": SearchTool,
    "web_search": SearchTool,
    "calculator": CalculatorTool,
    "memory": MemoryTool,
}


def load_tools(tool_config: list[dict[str, Any]] | dict[str, Any] | None, memory_enabled: bool = True):
    configured = tool_config or []
    if isinstance(configured, dict):
        configured = configured.get("enabled", [])

    tools = []
    for item in configured:
        tool_name = item.get("name") if isinstance(item, dict) else str(item)
        tool_cls = TOOL_REGISTRY.get(str(tool_name).lower())
        if tool_cls:
            tools.append(tool_cls())

    if memory_enabled and not any(isinstance(tool, MemoryTool) for tool in tools):
        tools.append(MemoryTool())

    return tools
