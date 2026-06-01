from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Type

logger = logging.getLogger(__name__)

KNOWN_JSON_SCHEMA_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}
MEMORY_STORE: dict[str, list[str]] = {}


class ToolValidationError(Exception):
    pass


class ToolExecutionError(Exception):
    pass


class ToolTimeoutError(TimeoutError):
    pass


class BaseTool:
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] | None = None
    aliases: list[str] = []
    timeout: int = 10
    max_output: int = 5000

    def execute(self, params: Any) -> Any:
        raise NotImplementedError("Tool subclasses must implement execute()")

    def run(self, params: Any) -> Any:
        return self.execute(params)


class ToolRegistry:
    def __init__(self, custom_dir: str | Path | None = None):
        self._custom_dir = Path(custom_dir or Path(__file__).parent / "custom")
        self._tool_classes: dict[str, type[BaseTool]] = {}
        self._builtin_tool_classes: list[type[BaseTool]] = []
        self._load_errors: list[dict[str, Any]] = []
        self._loaded = False

    @property
    def load_errors(self) -> list[dict[str, Any]]:
        return list(self._load_errors)

    def register(self, tool_cls: type[BaseTool], builtin: bool = False) -> None:
        self._validate_tool_class(tool_cls)
        name = getattr(tool_cls, "name", "")
        if not isinstance(name, str) or not name.strip():
            raise ToolValidationError("Tool name must be a non-empty string")
        canonical_name = name.lower().strip()
        if canonical_name in self._tool_classes:
            raise ToolValidationError(f"Tool name '{canonical_name}' is already registered")

        self._tool_classes[canonical_name] = tool_cls
        for alias in getattr(tool_cls, "aliases", []) or []:
            if not isinstance(alias, str) or not alias.strip():
                continue
            alias_name = alias.lower().strip()
            if alias_name in self._tool_classes:
                raise ToolValidationError(f"Tool alias '{alias_name}' collides with an existing tool")
            self._tool_classes[alias_name] = tool_cls

        if builtin and tool_cls not in self._builtin_tool_classes:
            self._builtin_tool_classes.append(tool_cls)

    def list(self) -> list[dict[str, Any]]:
        unique_tools: dict[str, type[BaseTool]] = {}
        for tool_cls in self._tool_classes.values():
            unique_tools[tool_cls.name.lower()] = tool_cls

        return [
            {
                "name": tool_cls.name,
                "description": tool_cls.description,
                "input_schema": tool_cls.input_schema,
                "aliases": getattr(tool_cls, "aliases", []),
            }
            for tool_cls in unique_tools.values()
        ]

    def get(self, name: str) -> type[BaseTool] | None:
        if not name:
            return None
        return self._tool_classes.get(str(name).lower())

    def reload(self) -> dict[str, Any]:
        self._load_errors = []
        self._tool_classes = {}
        for tool_cls in list(self._builtin_tool_classes):
            try:
                self.register(tool_cls, builtin=True)
            except ToolValidationError as exc:
                self._load_errors.append({"tool": getattr(tool_cls, "name", "unknown"), "error": str(exc)})

        self._custom_dir.mkdir(parents=True, exist_ok=True)
        importlib.invalidate_caches()
        tool_files = sorted(self._custom_dir.glob("*.py"))
        for tool_file in tool_files:
            module_name = f"app.tools.custom.{tool_file.stem}"
            try:
                if module_name in sys.modules:
                    del sys.modules[module_name]
                spec = importlib.util.spec_from_file_location(module_name, str(tool_file))
                if spec is None or spec.loader is None:
                    raise ToolValidationError(f"Cannot load module spec for {tool_file}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            except Exception as exc:
                logger.exception("Failed to load tool module %s", tool_file)
                self._load_errors.append({"file": str(tool_file), "error": str(exc)})
                continue

            loaded = False
            for obj in vars(module).values():
                if inspect.isclass(obj) and issubclass(obj, BaseTool) and obj is not BaseTool:
                    try:
                        self.register(obj)
                        loaded = True
                    except ToolValidationError as exc:
                        logger.warning("Invalid tool in %s: %s", tool_file, exc)
                        self._load_errors.append({"file": str(tool_file), "error": str(exc)})
                    except Exception:
                        logger.exception("Unexpected error registering tool %s", tool_file)
                        self._load_errors.append({"file": str(tool_file), "error": traceback.format_exc()})
            if not loaded:
                logger.debug("No valid BaseTool subclasses found in %s", tool_file)
        self._loaded = True
        return {
            "loaded": len(self._tool_classes),
            "errors": self.load_errors,
            "tools": self.list(),
        }

    def execute_tool(
        self,
        name: str,
        params: Any,
        limits: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool_cls = self.get(name)
        if not tool_cls:
            return {
                "name": name,
                "error": {
                    "type": "tool_not_found",
                    "message": f"Tool '{name}' is not registered.",
                },
            }
        tool = tool_cls()
        limits = limits or {}
        timeout = int(limits.get("timeout", getattr(tool, "timeout", 10)))
        max_output = int(limits.get("max_output", getattr(tool, "max_output", 5000)))

        try:
            validated = self._validate_input(tool.input_schema, params)
        except ToolValidationError as exc:
            logger.warning("Tool input validation failed for %s: %s", name, exc)
            return {
                "name": name,
                "error": {"type": "validation_error", "message": str(exc)},
            }

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(tool.execute, validated)
                raw_output = future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            logger.warning("Tool execution timed out for %s", name)
            return {
                "name": name,
                "error": {"type": "timeout", "message": f"Tool execution exceeded {timeout} seconds."},
            }
        except Exception as exc:
            logger.exception("Tool execution failed for %s", name, exc_info=exc)
            return {
                "name": name,
                "error": {"type": "execution_error", "message": str(exc)},
            }

        sanitized_output = self._sanitize_output(raw_output, max_output)
        logger.debug(
            "Tool executed %s | raw_output=%s | sanitized_output=%s",
            name,
            raw_output,
            sanitized_output,
        )
        return {"name": name, "result": sanitized_output}

    def _validate_tool_class(self, tool_cls: type[BaseTool]) -> None:
        if not inspect.isclass(tool_cls):
            raise ToolValidationError("tool must be a class")
        if not issubclass(tool_cls, BaseTool):
            raise ToolValidationError("tool must extend BaseTool")
        if not hasattr(tool_cls, "name") or not isinstance(tool_cls.name, str):
            raise ToolValidationError("tool must define a string name")
        if not hasattr(tool_cls, "description") or not isinstance(tool_cls.description, str):
            raise ToolValidationError("tool must define a string description")
        if not hasattr(tool_cls, "execute") or not callable(getattr(tool_cls, "execute", None)) or tool_cls.execute == BaseTool.execute:
            raise ToolValidationError("tool must define/override execute() method")
        if tool_cls.input_schema is not None:
            self._validate_schema(tool_cls.input_schema)

    def _validate_schema(self, schema: Any) -> None:
        if not isinstance(schema, dict):
            raise ToolValidationError("input_schema must be a JSON object")
        schema_type = schema.get("type")
        if schema_type not in KNOWN_JSON_SCHEMA_TYPES:
            raise ToolValidationError(
                f"input_schema.type must be one of {sorted(KNOWN_JSON_SCHEMA_TYPES)}"
            )
        if schema_type == "object":
            properties = schema.get("properties")
            if properties is not None and not isinstance(properties, dict):
                raise ToolValidationError("object schemas must define a properties object")
            if properties is not None:
                for prop_schema in properties.values():
                    self._validate_schema(prop_schema)
            required = schema.get("required")
            if required is not None and not isinstance(required, list):
                raise ToolValidationError("object schema required must be a list")
        if schema_type == "array":
            items = schema.get("items")
            if items is not None:
                self._validate_schema(items)

    def _validate_input(self, schema: dict[str, Any] | None, params: Any) -> Any:
        if schema is None:
            return params
        schema_type = schema.get("type")
        if schema_type == "string":
            if isinstance(params, str):
                return params
            if isinstance(params, dict) and "query" in params:
                return params["query"]
            raise ToolValidationError("Expected a string input")
        if schema_type == "number":
            if isinstance(params, (int, float)):
                return params
            raise ToolValidationError("Expected a number")
        if schema_type == "integer":
            if isinstance(params, int) and not isinstance(params, bool):
                return params
            raise ToolValidationError("Expected an integer")
        if schema_type == "boolean":
            if isinstance(params, bool):
                return params
            raise ToolValidationError("Expected a boolean")
        if schema_type == "object":
            if not isinstance(params, dict):
                raise ToolValidationError("Expected a JSON object")
            properties = schema.get("properties", {})
            required = schema.get("required", []) or []
            for field_name in required:
                if field_name not in params:
                    raise ToolValidationError(f"Missing required field: {field_name}")
            for key, value in params.items():
                if key in properties:
                    self._validate_input(properties[key], value)
            return params
        if schema_type == "array":
            if not isinstance(params, list):
                raise ToolValidationError("Expected a JSON array")
            items_schema = schema.get("items")
            if items_schema is not None:
                for item in params:
                    self._validate_input(items_schema, item)
            return params
        return params

    def _sanitize_output(self, output: Any, max_output: int) -> Any:
        if isinstance(output, str):
            sanitized = output.strip()
            return sanitized if len(sanitized) <= max_output else sanitized[:max_output] + "..."
        if isinstance(output, (dict, list)):
            text = str(output)
            return text if len(text) <= max_output else text[:max_output] + "..."
        return output


tool_registry = ToolRegistry()

# built-in tools

class SearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for recent information. Input should be a concise query."
    aliases = ["search"]
    input_schema = {"type": "string"}

    def execute(self, params: Any) -> str:
        query = params if isinstance(params, str) else str(params)
        from app.audit.trail import record_event
        from app.utils.observability import get_request_context
        from duckduckgo_search import DDGS

        record_event(
            "tool_call_start",
            {"tool": self.name, "input": query},
            {"correlation_id": get_request_context().get("correlation_id")},
        )
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            output = "No search results found."
            record_event(
                "tool_call_end",
                {"tool": self.name, "output": output},
                {"correlation_id": get_request_context().get("correlation_id")},
            )
            return output
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


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate basic arithmetic expressions. Supports +, -, *, /, **, %, and parentheses."
    input_schema = {"type": "string"}

    def execute(self, params: Any) -> str:
        import ast
        import operator

        expression = params if isinstance(params, str) else str(params)
        from app.audit.trail import record_event
        from app.utils.observability import get_request_context

        operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        record_event(
            "tool_call_start",
            {"tool": self.name, "input": expression},
            {"correlation_id": get_request_context().get("correlation_id")},
        )
        try:
            tree = ast.parse(expression, mode="eval")
            output = str(self._eval_node(tree.body, operators))
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

    def _eval_node(self, node: Any, operators: dict) -> Any:
        import ast

        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](
                self._eval_node(node.left, operators),
                self._eval_node(node.right, operators),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](self._eval_node(node.operand, operators))
        raise ValueError("unsupported expression")


class MemoryTool(BaseTool):
    name = "memory"
    description = "Store or retrieve short memories. Use 'store: text' or 'retrieve: query'."
    input_schema = {"type": "string"}

    def execute(self, params: Any) -> str:
        instruction = params if isinstance(params, str) else str(params)
        from app.audit.trail import record_event
        from app.utils.observability import get_request_context

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


tool_registry.register(SearchTool, builtin=True)
tool_registry.register(CalculatorTool, builtin=True)
tool_registry.register(MemoryTool, builtin=True)

tool_registry.reload()
