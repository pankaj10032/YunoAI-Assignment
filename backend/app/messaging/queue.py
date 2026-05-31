from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.models import AgentMessage, DeadLetterMessage
from app.utils.observability import get_request_context


logger = logging.getLogger(__name__)
MAX_RETRIES = 3
POLL_INTERVAL_SECONDS = 0.25
MessageHandler = Callable[[AgentMessage], Awaitable[None] | None]


def publish(
    sender_id: int | None,
    receiver_id: int | None,
    payload: Any,
    db: Session | None = None,
) -> AgentMessage:
    """Persist a message for async delivery."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        message = AgentMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            payload={**payload, "correlation_id": get_request_context().get("correlation_id")} if isinstance(payload, dict) else payload,
            status="pending",
            retry_count=0,
        )
        session.add(message)
        session.commit()
        session.refresh(message)
        return message
    finally:
        if owns_session:
            session.close()


def consume(db: Session | None = None) -> AgentMessage | None:
    """Claim the oldest pending message and mark it processing."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        message = (
            session.query(AgentMessage)
            .filter(AgentMessage.status == "pending")
            .order_by(AgentMessage.id.asc())
            .first()
        )
        if not message:
            return None
        message.status = "processing"
        message.error = None
        session.commit()
        session.refresh(message)
        return message
    finally:
        if owns_session:
            session.close()


def acknowledge(message_id: int, db: Session | None = None) -> AgentMessage | None:
    """Mark a claimed message as delivered."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        message = session.get(AgentMessage, message_id)
        if not message:
            return None
        message.status = "delivered"
        message.delivered_at = _utc_now()
        message.error = None
        session.commit()
        session.refresh(message)
        return message
    finally:
        if owns_session:
            session.close()


def retry(message_id: int, error_reason: str, db: Session | None = None) -> AgentMessage | None:
    """Retry a failed delivery or move it to the dead-letter queue."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        message = session.get(AgentMessage, message_id)
        if not message:
            return None
        message.retry_count += 1
        message.error = error_reason
        if message.retry_count >= MAX_RETRIES:
            message.status = "failed"
            _move_to_dlq(session, message, error_reason)
        else:
            message.status = "pending"
        session.commit()
        session.refresh(message)
        return message
    finally:
        if owns_session:
            session.close()


def queue_stats(db: Session | None = None) -> dict[str, int]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        counts = dict(
            session.query(AgentMessage.status, func.count(AgentMessage.id))
            .group_by(AgentMessage.status)
            .all()
        )
        return {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "failed": counts.get("failed", 0),
            "dlq": session.query(DeadLetterMessage).count(),
        }
    finally:
        if owns_session:
            session.close()


def replay_interrupted(db: Session | None = None) -> int:
    """Return processing messages to pending so another worker can claim them."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        messages = (
            session.query(AgentMessage)
            .filter(AgentMessage.status == "processing")
            .order_by(AgentMessage.id.asc())
            .all()
        )
        for message in messages:
            message.status = "pending"
            message.error = "Replayed after interrupted consumer"
        session.commit()
        return len(messages)
    finally:
        if owns_session:
            session.close()


async def consumer_loop(
    stop_event: asyncio.Event | None = None,
    handler: MessageHandler | None = None,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    replayed = await asyncio.to_thread(replay_interrupted)
    if replayed:
        logger.info("Replayed %s interrupted agent message(s)", replayed)

    while stop_event is None or not stop_event.is_set():
        message = await asyncio.to_thread(consume)
        if not message:
            await asyncio.sleep(poll_interval)
            continue

        try:
            await _dispatch(message, handler)
            await asyncio.to_thread(acknowledge, message.id)
        except Exception as exc:
            logger.warning("Agent message %s delivery failed: %s", message.id, exc)
            await asyncio.to_thread(retry, message.id, str(exc))


async def _dispatch(message: AgentMessage, handler: MessageHandler | None) -> None:
    _validate_payload(message.payload)
    if handler:
        result = handler(message)
        if asyncio.iscoroutine(result):
            await result


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if not str(payload.get("content", "")).strip():
        raise ValueError("payload.content is required")


def _move_to_dlq(session: Session, message: AgentMessage, error_reason: str) -> None:
    exists = (
        session.query(DeadLetterMessage)
        .filter(DeadLetterMessage.original_message_id == message.id)
        .one_or_none()
    )
    if exists:
        exists.error_reason = error_reason
        exists.retry_count = message.retry_count
        return
    session.add(
        DeadLetterMessage(
            original_message_id=message.id,
            sender_id=message.sender_id,
            receiver_id=message.receiver_id,
            payload=message.payload,
            error_reason=error_reason,
            retry_count=message.retry_count,
        )
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
