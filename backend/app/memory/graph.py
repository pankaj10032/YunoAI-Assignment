from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.models.models import Agent, MemoryEdge, MemoryNode, Message


logger = logging.getLogger(__name__)
DEFAULT_TTL_HOURS = 24


def add_node(
    agent_id: int,
    node_type: str,
    content: str,
    source_id: int | None = None,
    facts: dict[str, Any] | None = None,
    ttl_hours: int | None = None,
    db: Session | None = None,
) -> MemoryNode:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        node = MemoryNode(
            agent_id=agent_id,
            node_type=node_type,
            source_id=source_id,
            content=content,
            facts=facts or {},
            ttl_expires_at=_ttl_expiry(ttl_hours),
        )
        session.add(node)
        session.commit()
        session.refresh(node)
        return node
    finally:
        if owns_session:
            session.close()


def add_edge(
    source_node_id: int,
    target_node_id: int,
    edge_type: str,
    metadata: dict[str, Any] | None = None,
    db: Session | None = None,
) -> MemoryEdge:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        edge = MemoryEdge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            metadata_payload=metadata or {},
        )
        session.add(edge)
        session.commit()
        session.refresh(edge)
        return edge
    finally:
        if owns_session:
            session.close()


def add_message_node(
    message: Message,
    db: Session | None = None,
    ttl_hours: int | None = None,
) -> MemoryNode:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        sender_id = message.sender_agent_id or message.receiver_agent_id
        if sender_id is None:
            raise ValueError("message must have a sender or receiver agent")

        facts = _extract_facts(message.content)
        node = add_node(
            agent_id=sender_id,
            node_type="message",
            source_id=message.id,
            content=message.content,
            facts=facts,
            ttl_hours=ttl_hours,
            db=session,
        )

        if message.sender_agent_id:
            sender_state = _latest_agent_state(session, message.sender_agent_id)
            if sender_state:
                add_edge(sender_state.id, node.id, "sender->receiver", {"message_id": message.id}, db=session)
        if message.receiver_agent_id:
            receiver_state = _latest_agent_state(session, message.receiver_agent_id)
            if receiver_state:
                add_edge(node.id, receiver_state.id, "reply-to", {"message_id": message.id}, db=session)
        return node
    finally:
        if owns_session:
            session.close()


def add_agent_state(agent: Agent, db: Session | None = None, ttl_hours: int | None = None) -> MemoryNode:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        content = json.dumps(
            {
                "name": agent.name,
                "role": agent.role,
                "system_prompt": agent.system_prompt,
                "guardrails": agent.guardrails or {},
            },
            ensure_ascii=True,
        )
        return add_node(
            agent_id=agent.id,
            node_type="agent_state",
            source_id=agent.id,
            content=content,
            facts=_extract_facts(content),
            ttl_hours=ttl_hours,
            db=session,
        )
    finally:
        if owns_session:
            session.close()


def query_context(agent_id: int, depth: int = 3, db: Session | None = None) -> str:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        seeds = (
            session.query(MemoryNode)
            .filter(MemoryNode.agent_id == agent_id)
            .order_by(MemoryNode.created_at.desc())
            .limit(max(1, depth))
            .all()
        )
        if not seeds:
            return ""

        visited: set[int] = set()
        frontier = [node.id for node in seeds]
        collected: list[MemoryNode] = []
        hops = 0
        while frontier and hops < depth:
            next_frontier: list[int] = []
            for node_id in frontier:
                if node_id in visited:
                    continue
                visited.add(node_id)
                node = session.get(MemoryNode, node_id)
                if not node:
                    continue
                collected.append(node)
                incoming = (
                    session.query(MemoryEdge.source_node_id)
                    .filter(MemoryEdge.target_node_id == node_id)
                    .all()
                )
                next_frontier.extend(source for (source,) in incoming if source not in visited)
            frontier = next_frontier
            hops += 1

        facts: list[str] = []
        for node in reversed(collected):
            extracted = node.facts.get("facts") if isinstance(node.facts, dict) else None
            if isinstance(extracted, list):
                facts.extend(str(item) for item in extracted if str(item).strip())
            if node.content.strip():
                facts.append(_summarize(node.content))

        unique_facts = _dedupe(facts)
        return "\n".join(unique_facts[: max(1, depth * 4)])
    finally:
        if owns_session:
            session.close()


def cleanup_expired_nodes(db: Session | None = None) -> int:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        now = datetime.now(timezone.utc)
        expired_ids = [
            node_id
            for (node_id,) in session.query(MemoryNode.id)
            .filter(MemoryNode.ttl_expires_at.is_not(None), MemoryNode.ttl_expires_at < now)
            .all()
        ]
        if not expired_ids:
            return 0
        session.execute(delete(MemoryEdge).where(
            (MemoryEdge.source_node_id.in_(expired_ids)) | (MemoryEdge.target_node_id.in_(expired_ids))
        ))
        session.execute(delete(MemoryNode).where(MemoryNode.id.in_(expired_ids)))
        session.commit()
        return len(expired_ids)
    finally:
        if owns_session:
            session.close()


async def cleanup_loop(stop_event: asyncio.Event | None = None, interval_sec: float = 30.0) -> None:
    while stop_event is None or not stop_event.is_set():
        await asyncio.to_thread(cleanup_expired_nodes)
        await asyncio.sleep(interval_sec)


def serialize_graph(agent_id: int, depth: int = 3, db: Session | None = None) -> dict[str, Any]:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        nodes = (
            session.query(MemoryNode)
            .filter(MemoryNode.agent_id == agent_id)
            .order_by(MemoryNode.created_at.desc())
            .limit(max(1, depth) * 6)
            .all()
        )
        node_ids = [node.id for node in nodes]
        edges = session.query(MemoryEdge).filter(
            (MemoryEdge.source_node_id.in_(node_ids)) | (MemoryEdge.target_node_id.in_(node_ids))
        ).all()
        return {
            "nodes": [
                {
                    "id": node.id,
                    "agent_id": node.agent_id,
                    "node_type": node.node_type,
                    "source_id": node.source_id,
                    "content": node.content,
                    "facts": node.facts,
                    "ttl_expires_at": node.ttl_expires_at.isoformat() if node.ttl_expires_at else None,
                    "created_at": node.created_at.isoformat() if node.created_at else None,
                }
                for node in nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "source_node_id": edge.source_node_id,
                    "target_node_id": edge.target_node_id,
                    "edge_type": edge.edge_type,
                    "metadata": edge.metadata_payload,
                    "created_at": edge.created_at.isoformat() if edge.created_at else None,
                }
                for edge in edges
            ],
            "context": query_context(agent_id, depth=depth, db=session),
        }
    finally:
        if owns_session:
            session.close()


def _latest_agent_state(session: Session, agent_id: int) -> MemoryNode | None:
    return (
        session.query(MemoryNode)
        .filter(MemoryNode.agent_id == agent_id, MemoryNode.node_type == "agent_state")
        .order_by(MemoryNode.created_at.desc())
        .first()
    )


def _extract_facts(text: str) -> dict[str, Any]:
    sentences = [part.strip() for part in re.split(r"[.!?\n]+", text) if part.strip()]
    facts = [sentence[:160] for sentence in sentences[:5]]
    return {"facts": facts}


def _summarize(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:240]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def _ttl_expiry(ttl_hours: int | None) -> datetime:
    hours = ttl_hours if ttl_hours is not None else DEFAULT_TTL_HOURS
    return datetime.now(timezone.utc) + timedelta(hours=hours)
