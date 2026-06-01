"""
Tool Sandbox
============
Provides a sandboxed execution layer for all agent tools, enforcing:

* **Timeout** — hard wall-clock limit (default 15 s).
* **Output size cap** — truncate results exceeding ``max_output_bytes``
  (default 10 KB).
* **PII sanitisation** — strip emails, API keys, bearer tokens from
  output before returning or persisting.
* **Cost tracking** — accumulate estimated token/cost figures per
  ``(agent_id, tool_name)`` pair for quota enforcement.

Usage
-----
Instantiate a single :class:`ToolSandbox` and call
:meth:`ToolSandbox.execute`::

    sandbox = ToolSandbox()
    result = sandbox.execute("web_search", {"query": "AI news"}, agent_id=42)
"""

from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT: float = 15.0       # seconds
DEFAULT_MAX_OUTPUT: int = 10_240    # bytes (10 KB)
DEFAULT_MAX_COST_USD: float = 0.10  # per single tool invocation
COST_PER_BYTE: float = 0.000_000_002  # rough estimate

# ── PII patterns ───────────────────────────────────────────────────────────────
_PII_PATTERNS: list[re.Pattern[str]] = [
    # API keys / secrets in key=value pairs
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|authorization)\b\s*[:=]\s*([^\s,;\"\'\]]+)",
        re.IGNORECASE,
    ),
    # Bearer tokens
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
    # E-mail addresses
    re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    # Credit-card-like numbers (naïve)
    re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    # SSN-like patterns
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
]


def _strip_pii(text: str) -> str:
    for pattern in _PII_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _sanitize_output(output: Any) -> Any:
    if isinstance(output, str):
        return _strip_pii(output)
    if isinstance(output, dict):
        return {k: _sanitize_output(v) for k, v in output.items()}
    if isinstance(output, list):
        return [_sanitize_output(item) for item in output]
    return output


def _truncate_output(output: Any, max_bytes: int) -> tuple[Any, bool]:
    """Return (possibly-truncated output, was_truncated)."""
    if isinstance(output, str):
        encoded = output.encode("utf-8", errors="replace")
        if len(encoded) > max_bytes:
            return (
                encoded[:max_bytes].decode("utf-8", errors="replace") + " …[truncated]",
                True,
            )
        return output, False
    if isinstance(output, (dict, list)):
        import json

        raw = json.dumps(output, ensure_ascii=False)
        truncated, was_trunc = _truncate_output(raw, max_bytes)
        if was_trunc:
            try:
                return json.loads(truncated.replace(" …[truncated]", "")), True
            except Exception:
                return {"_truncated": True, "_preview": truncated}, True
        return output, False
    return output, False


# ── Sandbox ────────────────────────────────────────────────────────────────────

class ToolSandbox:
    """Thread-pool-backed sandbox for safe, resource-bounded tool execution."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT,
        max_cost_usd: float = DEFAULT_MAX_COST_USD,
        max_workers: int = 8,
    ) -> None:
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self.max_cost_usd = max_cost_usd
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="tool-sandbox"
        )
        # cost tracker: (agent_id, tool_name) → cumulative_usd
        self._cost_tracker: dict[tuple[int | None, str], float] = {}

    # ------------------------------------------------------------------
    def execute(
        self,
        tool_callable,
        params: Any,
        *,
        tool_name: str = "unknown",
        agent_id: int | None = None,
        timeout: float | None = None,
        max_output_bytes: int | None = None,
    ) -> dict[str, Any]:
        """Run *tool_callable(params)* in a sandboxed thread.

        Parameters
        ----------
        tool_callable:
            Any callable that accepts ``params`` and returns a value.
        params:
            Arguments forwarded to ``tool_callable``.
        tool_name:
            Human-readable name used in logging and cost tracking.
        agent_id:
            Agent requesting the tool (used for per-agent cost tracking).
        timeout:
            Override the instance-level timeout (seconds).
        max_output_bytes:
            Override the instance-level output size cap.

        Returns
        -------
        dict with keys ``result``, ``tool_name``, ``latency_ms``,
        ``truncated``, ``cost_usd``, and optionally ``error``.
        """
        _timeout = timeout if timeout is not None else self.timeout
        _max_bytes = max_output_bytes if max_output_bytes is not None else self.max_output_bytes

        future = self._executor.submit(tool_callable, params)
        start = time.monotonic()

        try:
            raw_result = future.result(timeout=_timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            logger.warning("Tool %s timed out after %.1f s", tool_name, _timeout)
            return {
                "tool_name": tool_name,
                "error": {"type": "timeout", "message": f"Tool exceeded {_timeout}s time limit"},
                "result": None,
                "latency_ms": round((_timeout) * 1000),
                "truncated": False,
                "cost_usd": 0.0,
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - start) * 1000)
            logger.exception("Tool %s raised: %s", tool_name, exc)
            return {
                "tool_name": tool_name,
                "error": {"type": "execution_error", "message": str(exc)},
                "result": None,
                "latency_ms": latency_ms,
                "truncated": False,
                "cost_usd": 0.0,
            }

        latency_ms = round((time.monotonic() - start) * 1000)

        # Sanitise and truncate
        safe_result = _sanitize_output(raw_result)
        safe_result, was_truncated = _truncate_output(safe_result, _max_bytes)

        # Cost estimate
        output_bytes = len(str(safe_result).encode("utf-8", errors="replace"))
        cost_usd = round(output_bytes * COST_PER_BYTE, 8)
        key = (agent_id, tool_name)
        self._cost_tracker[key] = self._cost_tracker.get(key, 0.0) + cost_usd

        if was_truncated:
            logger.info("Tool %s output truncated to %d bytes", tool_name, _max_bytes)

        return {
            "tool_name": tool_name,
            "result": safe_result,
            "latency_ms": latency_ms,
            "truncated": was_truncated,
            "cost_usd": cost_usd,
            "error": None,
        }

    def cumulative_cost(self, agent_id: int | None, tool_name: str) -> float:
        """Return cumulative estimated cost in USD for this (agent, tool) pair."""
        return self._cost_tracker.get((agent_id, tool_name), 0.0)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)


# Module-level singleton — shared across the process
sandbox = ToolSandbox()
