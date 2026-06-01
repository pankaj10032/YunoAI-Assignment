from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
import time
from collections import deque
import threading

# Telemetry batching queue and lock
_telemetry_queue: deque[dict[str, Any]] = deque()
_telemetry_lock = threading.Lock()
_telemetry_flush_interval = 5.0

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
agent_id_var: ContextVar[str | None] = ContextVar("agent_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
step_var: ContextVar[str | None] = ContextVar("step", default=None)

_recent_logs: deque[dict[str, Any]] = deque(maxlen=1000)
_log_lock = threading.Lock()

_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|authorization)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
]


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_request_context(
    *,
    correlation_id: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    step: str | None = None,
) -> None:
    if correlation_id is not None:
        correlation_id_var.set(correlation_id)
    if agent_id is not None:
        agent_id_var.set(agent_id)
    if run_id is not None:
        run_id_var.set(run_id)
    if step is not None:
        step_var.set(step)


def get_request_context() -> dict[str, str | None]:
    return {
        "correlation_id": correlation_id_var.get(),
        "agent_id": agent_id_var.get(),
        "run_id": run_id_var.get(),
        "step": step_var.get(),
    }


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        sanitized = value
        for pattern in _SENSITIVE_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized
    if isinstance(value, dict):
        return {key: sanitize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    return value


def record_log_entry(payload: dict[str, Any]) -> None:
    with _log_lock:
        _recent_logs.append(sanitize_value(payload))


def search_log_entries(correlation_id: str) -> list[dict[str, Any]]:
    with _log_lock:
        return [entry for entry in list(_recent_logs) if entry.get("correlation_id") == correlation_id]


def structured_log_payload(
    level: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = get_request_context()
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "message": message,
        **context,
    }
    if extra:
        payload.update(sanitize_value(extra))
    return sanitize_value(payload)


class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": sanitize_value(record.getMessage()),
            **get_request_context(),
        }
        for key in ("agent_id", "run_id", "step", "correlation_id"):
            if hasattr(record, key) and getattr(record, key) is not None:
                payload[key] = sanitize_value(getattr(record, key))
        if record.args:
            payload["args"] = sanitize_value([str(arg) for arg in record.args])
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        record_log_entry(payload)
        return json.dumps(payload, ensure_ascii=True)


def log_event(
    run_id: int | None = None,
    agent_id: int | None = None,
    step: str | None = None,
    tokens: int | None = None,
    cost: float | None = None,
    latency: float | None = None,
    event_type: str = "usage",
    source: str = "llm_router",
) -> None:
    """Queue a telemetry event to be flushed asynchronously to the DB.

    Fields are sanitized before enqueueing. Events are flushed in batches
    every `_telemetry_flush_interval` seconds by a background thread.
    """
    payload = {
        "run_id": run_id,
        "agent_id": agent_id,
        "step": step,
        "tokens": tokens,
        "cost": cost,
        "latency": latency,
    }
    entry = {"event_type": event_type, "source": source, "payload": sanitize_value(payload)}
    with _telemetry_lock:
        _telemetry_queue.append(entry)


def _flush_telemetry_worker() -> None:
    from app.models.database import SessionLocal
    from app.models.models import TelemetryEvent

    while True:
        try:
            to_flush: list[dict[str, Any]] = []
            with _telemetry_lock:
                while _telemetry_queue:
                    to_flush.append(_telemetry_queue.popleft())
            if to_flush:
                db = SessionLocal()
                try:
                    for ev in to_flush:
                        te = TelemetryEvent(event_type=ev.get("event_type", "usage"), source=ev.get("source", "llm_router"), payload=ev.get("payload", {}))
                        db.add(te)
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()
        except Exception:
            # ensure worker keeps running despite occasional errors
            pass
        time.sleep(_telemetry_flush_interval)


# Start background telemetry flush thread (daemon so it doesn't block shutdown)
_telemetry_thread = threading.Thread(target=_flush_telemetry_worker, daemon=True)
_telemetry_thread.start()
