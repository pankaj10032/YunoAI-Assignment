from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.models import Agent, AgentMessage, DeadLetterMessage
from app.utils.observability import get_request_context

logger = logging.getLogger(__name__)
MAX_RETRIES = 3
POLL_INTERVAL_SECONDS = 0.25

SubscriberQueue = asyncio.Queue[AgentMessage]
SubscriptionMap = dict[str, dict[str, SubscriberQueue]]

subscriptions: SubscriptionMap = {}
subscription_lock = asyncio.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_topic(topic: str) -> str:
    return topic.strip().lower()


def _payload_hash(sender_id: int | None, topic: str, payload: dict[str, Any], timestamp: datetime) -> str:
    window = int(timestamp.replace(second=0, microsecond=0).timestamp() // 60)
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    payload_key = f"{sender_id}:{topic}:{data}:{window}"
    return hashlib.sha256(payload_key.encode("utf-8")).hexdigest()


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if not str(payload.get("content", "")).strip():
        raise ValueError("payload.content is required")
    return payload


def _find_subscribers(session: Session, topic: str) -> list[Agent]:
    normalized = _normalize_topic(topic)
    agents = session.query(Agent).filter(Agent.subscribed_topics != None).all()
    return [agent for agent in agents if normalized in [t.strip().lower() for t in (agent.subscribed_topics or [])]]


def publish(topic: str, payload: dict[str, Any], sender_id: str | int | None, idempotency_key: str | None = None) -> list[AgentMessage]:
    payload = _validate_payload(payload)
    topic = _normalize_topic(topic)
    now = _utc_now()
    if idempotency_key is None:
        idempotency_key = _payload_hash(sender_id, topic, payload, now)

    session = SessionLocal()
    try:
        existing = (
            session.query(AgentMessage)
            .filter(AgentMessage.sender_id == sender_id)
            .filter(AgentMessage.topic == topic)
            .filter(AgentMessage.idempotency_key == idempotency_key)
            .filter(AgentMessage.created_at >= now - timedelta(minutes=1))
            .all()
        )
        if existing:
            return existing

        subscribers = _find_subscribers(session, topic)
        if not subscribers:
            logger.info("No subscribers found for topic '%s'", topic)

        messages: list[AgentMessage] = []
        for subscriber in subscribers:
            message = AgentMessage(
                topic=topic,
                payload={**payload, "correlation_id": get_request_context().get("correlation_id")},
                sender_id=sender_id,
                receiver_id=subscriber.id,
                status="pending",
                retry_count=0,
                idempotency_key=idempotency_key,
            )
            session.add(message)
            messages.append(message)
        session.commit()
        for message in messages:
            session.refresh(message)
        return messages
    finally:
        session.close()


async def subscribe(topic: str, consumer_id: str) -> AsyncGenerator[AgentMessage, None]:
    normalized = _normalize_topic(topic)
    queue: SubscriberQueue = asyncio.Queue()

    async def _register() -> None:
        async with subscription_lock:
            topic_map = subscriptions.setdefault(normalized, {})
            topic_map[consumer_id] = queue
            logger.debug("Subscriber %s subscribed to %s", consumer_id, normalized)

    async def _unregister() -> None:
        async with subscription_lock:
            topic_map = subscriptions.get(normalized, {})
            topic_map.pop(consumer_id, None)
            if not topic_map:
                subscriptions.pop(normalized, None)
            logger.debug("Subscriber %s unsubscribed from %s", consumer_id, normalized)

    await _register()
    try:
        while True:
            message = await queue.get()
            yield message
    finally:
        await _unregister()


async def _deliver_message(session: Session, message: AgentMessage) -> bool:
    if message.receiver_id is None:
        raise ValueError("Message receiver_id is required for delivery")
    key = str(message.topic).strip().lower()
    async with subscription_lock:
        queue = subscriptions.get(key, {}).get(str(message.receiver_id))
        if queue is None:
            return False
        await queue.put(message)
        return True


def _mark_delivered(session: Session, message: AgentMessage) -> None:
    message.status = "delivered"
    message.delivered_at = _utc_now()
    message.error = None
    session.add(message)
    session.commit()


def _mark_failed(session: Session, message: AgentMessage, error_reason: str) -> None:
    message.retry_count += 1
    message.error = error_reason
    if message.retry_count >= MAX_RETRIES:
        message.status = "failed"
        _move_to_dlq(session, message, error_reason)
    session.add(message)
    session.commit()


def _move_to_dlq(session: Session, message: AgentMessage, error_reason: str) -> None:
    exists = (
        session.query(DeadLetterMessage)
        .filter(DeadLetterMessage.original_message_id == message.id)
        .one_or_none()
    )
    if exists:
        exists.error_reason = error_reason
        exists.retry_count = message.retry_count
    else:
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
            "delivered": counts.get("delivered", 0),
            "failed": counts.get("failed", 0),
            "dlq": session.query(DeadLetterMessage).count(),
        }
    finally:
        if owns_session:
            session.close()


def get_message_history(agent_id: int, limit: int = 200) -> list[AgentMessage]:
    session = SessionLocal()
    try:
        return (
            session.query(AgentMessage)
            .filter(
                (AgentMessage.sender_id == agent_id) | (AgentMessage.receiver_id == agent_id)
            )
            .order_by(AgentMessage.created_at.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def _deliver_pending_message(message: AgentMessage) -> None:
    session = SessionLocal()
    try:
        if _deliver_message(session, message):
            _mark_delivered(session, message)
    except Exception as exc:
        logger.warning("Failed to deliver message %s: %s", message.id, exc)
        _mark_failed(session, message, str(exc))
    finally:
        session.close()


async def consumer_loop(stop_event: asyncio.Event | None = None) -> None:
    while stop_event is None or not stop_event.is_set():
        session = SessionLocal()
        delivered_any = False
        try:
            pending = (
                session.query(AgentMessage)
                .filter(AgentMessage.status == "pending")
                .order_by(AgentMessage.id.asc())
                .limit(20)
                .all()
            )
            if pending:
                for message in pending:
                    try:
                        if await _deliver_message(session, message):
                            _mark_delivered(session, message)
                            delivered_any = True
                    except Exception as exc:
                        logger.warning("Delivery failure for message %s: %s", message.id, exc)
                        _mark_failed(session, message, str(exc))
                        delivered_any = True
        finally:
            session.close()
            
        if not delivered_any:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        else:
            await asyncio.sleep(0.01)


async def stream_bus_messages(websocket, agent_id: int) -> None:
    topic = f"agent_{agent_id}_inbox"
    async for message in subscribe(topic, str(agent_id)):
        await websocket.send_json(
            {
                "type": "message",
                "message_id": message.id,
                "topic": message.topic,
                "sender_id": message.sender_id,
                "receiver_id": message.receiver_id,
                "payload": message.payload,
                "status": message.status,
                "created_at": message.created_at.isoformat(),
            }
        )
