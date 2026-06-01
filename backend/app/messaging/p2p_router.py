import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.models import Agent, AgentMessage, DeadLetterMessage
from app.messaging.bus import subscription_lock, subscriptions

logger = logging.getLogger(__name__)

class AgentDirectory:
    def __init__(self):
        # Maps agent_id -> {"status": "idle"/"busy"/"offline", "inbox_topic": str}
        self.directory: Dict[int, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def register(self, agent_id: int, status: str = "idle") -> None:
        async with self.lock:
            self.directory[agent_id] = {
                "status": status,
                "inbox_topic": f"agent_{agent_id}_inbox"
            }

    async def set_status(self, agent_id: int, status: str) -> None:
        async with self.lock:
            if agent_id in self.directory:
                self.directory[agent_id]["status"] = status
            else:
                self.directory[agent_id] = {
                    "status": status,
                    "inbox_topic": f"agent_{agent_id}_inbox"
                }

    async def get_status(self, agent_id: int) -> str:
        async with self.lock:
            if agent_id in self.directory:
                return self.directory[agent_id]["status"]
            return "offline"

    async def get_inbox_topic(self, agent_id: int) -> str:
        return f"agent_{agent_id}_inbox"


class SessionManager:
    @staticmethod
    def create_session() -> str:
        return f"session_{uuid.uuid4().hex}"


agent_directory = AgentDirectory()
session_manager = SessionManager()

class MessageRouter:
    @staticmethod
    async def send_message(
        sender_id: int,
        receiver_id: int,
        content: str,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> AgentMessage:
        if not session_id:
            session_id = session_manager.create_session()
        if not correlation_id:
            correlation_id = uuid.uuid4().hex

        topic = f"agent_{receiver_id}_inbox"
        payload = {
            "content": content,
            "correlation_id": correlation_id,
            "session_id": session_id,
            "sender_id": sender_id,
            "receiver_id": receiver_id
        }

        db: Session = SessionLocal()
        try:
            # Enforce max concurrent sessions limit if applicable
            agent = db.get(Agent, receiver_id)
            if agent:
                active_sessions_count = db.query(AgentMessage.session_id).filter(
                    AgentMessage.receiver_id == receiver_id,
                    AgentMessage.status.in_(["pending", "sent"])
                ).distinct().count()
                limit = getattr(agent, "max_concurrent_sessions", 5)
                if active_sessions_count >= limit:
                    logger.warning(
                        "Agent %s has reached max concurrent sessions limit (%s/%s)",
                        receiver_id, active_sessions_count, limit
                    )

            msg = AgentMessage(
                topic=topic,
                sender_id=sender_id,
                receiver_id=receiver_id,
                payload=payload,
                status="pending",
                retry_count=0,
                session_id=session_id,
                correlation_id=correlation_id,
                idempotency_key=f"p2p_{uuid.uuid4().hex}"
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return msg
        finally:
            db.close()

    @staticmethod
    async def acknowledge_message(message_id: int) -> bool:
        db: Session = SessionLocal()
        try:
            msg = db.get(AgentMessage, message_id)
            if msg:
                msg.status = "acked"
                msg.delivered_at = datetime.now(timezone.utc)
                db.commit()
                # Notify subscriber queues
                await MessageRouter.push_to_inbox_queue(msg)
                return True
            return False
        finally:
            db.close()

    @staticmethod
    async def push_to_inbox_queue(msg: AgentMessage) -> bool:
        topic = msg.topic.strip().lower()
        async with subscription_lock:
            topic_map = subscriptions.get(topic, {})
            # Push message to receiver's subscriber queue
            queue = topic_map.get(str(msg.receiver_id))
            if queue:
                await queue.put(msg)
                return True
        return False


async def p2p_background_worker(stop_event: asyncio.Event) -> None:
    """Worker checks pending messages, delivers them, handles retries, DLQ."""
    logger.info("P2P Router background worker starting")
    while not stop_event.is_set():
        db: Session = SessionLocal()
        try:
            # 1. Fetch pending messages
            pending_msgs = db.query(AgentMessage).filter(
                AgentMessage.status == "pending"
            ).order_by(AgentMessage.id.asc()).limit(20).all()

            for msg in pending_msgs:
                # Try delivery
                delivered = await MessageRouter.push_to_inbox_queue(msg)
                if delivered:
                    msg.status = "sent"
                    msg.delivered_at = datetime.now(timezone.utc)
                    db.commit()
                else:
                    # Retry
                    msg.retry_count += 1
                    if msg.retry_count >= 3:
                        msg.status = "failed"
                        msg.error = "Delivery timeout / subscriber offline after 3 attempts"
                        dlq_msg = DeadLetterMessage(
                            original_message_id=msg.id,
                            sender_id=msg.sender_id,
                            receiver_id=msg.receiver_id,
                            payload=msg.payload,
                            error_reason=msg.error,
                            retry_count=msg.retry_count
                        )
                        db.add(dlq_msg)
                    db.commit()

            # 2. Check for "sent" messages that haven't been acked for 30s
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)
            unacked_msgs = db.query(AgentMessage).filter(
                AgentMessage.status == "sent",
                AgentMessage.delivered_at <= cutoff
            ).all()

            for msg in unacked_msgs:
                msg.retry_count += 1
                if msg.retry_count >= 3:
                    msg.status = "failed"
                    msg.error = "No ACK received within timeout"
                    dlq_msg = DeadLetterMessage(
                        original_message_id=msg.id,
                        sender_id=msg.sender_id,
                        receiver_id=msg.receiver_id,
                        payload=msg.payload,
                        error_reason=msg.error,
                        retry_count=msg.retry_count
                    )
                    db.add(dlq_msg)
                else:
                    # Move back to pending to trigger re-delivery
                    msg.status = "pending"
                db.commit()

        except Exception as exc:
            logger.exception("Error in P2P background worker: %s", exc)
        finally:
            db.close()

        await asyncio.sleep(1.0)
