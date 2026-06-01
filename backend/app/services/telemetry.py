"""
Async Telemetry Service
=======================
Provides a high-throughput, non-blocking telemetry pipeline for the
AI Orchestrator backend.

Design
------
* ``log_event(...)`` — public API.  Enqueues an event in a thread-safe
  ``deque``; never blocks the caller.
* A daemon background thread flushes the queue to the database every
  ``FLUSH_INTERVAL`` seconds **or** whenever the queue grows beyond
  ``FLUSH_BATCH_SIZE`` items (whichever comes first).
* All event payloads are sanitised (PII stripped) before persistence.

Integration
-----------
Import and call ``log_event`` from anywhere in the backend::

    from app.services.telemetry import log_event

    log_event(
        event_type="tool_call",
        source="executor",
        payload={"tool": "web_search", "query": "..."},
        run_id=run.id,
        agent_id=agent.id,
        correlation_id=cid,
    )
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from app.utils.observability import sanitize_value, get_request_context

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
FLUSH_INTERVAL: float = 5.0   # seconds between forced flushes
FLUSH_BATCH_SIZE: int = 50    # flush immediately when queue exceeds this size

# ── Internal state ─────────────────────────────────────────────────────────────
_queue: deque[dict[str, Any]] = deque()
_lock = threading.Lock()
_flush_event = threading.Event()


# ── Public API ─────────────────────────────────────────────────────────────────

def log_event(
    *,
    event_type: str = "usage",
    source: str = "system",
    payload: dict[str, Any] | None = None,
    run_id: int | None = None,
    agent_id: int | None = None,
    correlation_id: str | None = None,
) -> None:
    """Enqueue a telemetry event for async persistence.

    This function is intentionally **non-blocking** — it appends to an in-memory
    deque and returns immediately.  The background flush thread handles DB writes.

    Parameters
    ----------
    event_type:
        Category of the event, e.g. ``"tool_call"``, ``"workflow_step"``,
        ``"ui_render_error"``.
    source:
        Subsystem that produced the event, e.g. ``"executor"``, ``"ecosystem"``.
    payload:
        Arbitrary JSON-serialisable dict with event-specific data.
    run_id:
        ID of the workflow run associated with this event (optional).
    agent_id:
        ID of the agent associated with this event (optional).
    correlation_id:
        Request correlation ID.  Falls back to the current context value when
        not explicitly provided.
    """
    ctx = get_request_context()
    cid = correlation_id or ctx.get("correlation_id")

    entry: dict[str, Any] = {
        "event_type": event_type,
        "source": source,
        "payload": sanitize_value(
            {
                **(payload or {}),
                "run_id": run_id,
                "agent_id": agent_id,
                "correlation_id": cid,
            }
        ),
    }

    with _lock:
        _queue.append(entry)
        should_flush_now = len(_queue) >= FLUSH_BATCH_SIZE

    if should_flush_now:
        _flush_event.set()  # wake background thread early


# ── Background flush thread ────────────────────────────────────────────────────

def _flush_worker() -> None:
    """Daemon thread: drains the telemetry queue into the database."""
    while True:
        # Wait for either a timed interval or an early-flush signal
        _flush_event.wait(timeout=FLUSH_INTERVAL)
        _flush_event.clear()

        batch: list[dict[str, Any]] = []
        with _lock:
            while _queue:
                batch.append(_queue.popleft())

        if not batch:
            continue

        try:
            from app.models.database import SessionLocal  # local import — avoids circular deps
            from app.models.models import TelemetryEvent

            db = SessionLocal()
            try:
                db.bulk_save_objects(
                    [
                        TelemetryEvent(
                            event_type=ev["event_type"],
                            source=ev["source"],
                            payload=ev["payload"],
                        )
                        for ev in batch
                    ]
                )
                db.commit()
                logger.debug("Telemetry flushed %d events to DB", len(batch))
            except Exception as exc:
                logger.warning("Telemetry flush error: %s", exc)
                db.rollback()
                # Re-enqueue failed events so they are retried next cycle
                with _lock:
                    _queue.extendleft(reversed(batch))
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Telemetry flush critical error: %s", exc)


# Start once at import time (daemon so it doesn't block process exit)
_flush_thread = threading.Thread(target=_flush_worker, daemon=True, name="telemetry-flush")
_flush_thread.start()
