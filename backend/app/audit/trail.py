from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.models import AuditEvent
from app.utils.observability import get_request_context, sanitize_value


def record_event(event_type: str, payload: dict[str, Any], metadata: dict[str, Any] | None = None, db: Session | None = None) -> AuditEvent:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        context = get_request_context()
        event_row = AuditEvent(
            correlation_id=(metadata or {}).get("correlation_id") or context.get("correlation_id"),
            event_type=event_type,
            agent_id=(metadata or {}).get("agent_id"),
            run_id=(metadata or {}).get("run_id"),
            payload={
                "payload": sanitize_value(payload),
                "metadata": sanitize_value(metadata or {}),
                "context": sanitize_value(context),
            },
            created_at=datetime.now(timezone.utc),
        )
        session.add(event_row)
        session.commit()
        session.refresh(event_row)
        return event_row
    finally:
        if owns_session:
            session.close()


def run_timeline(run_id: int, db: Session | None = None) -> list[dict[str, Any]]:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        rows = (
            session.query(AuditEvent)
            .filter(AuditEvent.run_id == run_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
            .all()
        )
        return [
            {
                "id": row.id,
                "correlation_id": row.correlation_id,
                "event_type": row.event_type,
                "agent_id": row.agent_id,
                "run_id": row.run_id,
                "payload": row.payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    finally:
        if owns_session:
            session.close()


def install_immutability_guards() -> None:
    @event.listens_for(AuditEvent, "before_update", propagate=True)
    def _no_update(*_args, **_kwargs):  # pragma: no cover
        raise RuntimeError("Audit events are immutable")

    @event.listens_for(AuditEvent, "before_delete", propagate=True)
    def _no_delete(*_args, **_kwargs):  # pragma: no cover
        raise RuntimeError("Audit events are immutable")
