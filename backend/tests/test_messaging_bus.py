import asyncio
import time
from datetime import datetime, timezone

import pytest
from app.messaging.bus import publish, queue_stats, subscribe
from app.models.models import Agent, AgentMessage, DeadLetterMessage


@pytest.mark.asyncio
async def test_publish_subscribe_and_deduplication(client, db):
    sender = Agent(
        name="Sender Agent",
        role="Sender",
        system_prompt="Send messages.",
        model="gpt-4o-mini",
        tools=[{"name": "memory"}],
        channels=["web"],
        memory_enabled=True,
        guardrails={},
        schedule=None,
        subscribed_topics=["test_bus"],
    )
    receiver = Agent(
        name="Receiver Agent",
        role="Receiver",
        system_prompt="Receive messages.",
        model="gpt-4o-mini",
        tools=[{"name": "memory"}],
        channels=["web"],
        memory_enabled=True,
        guardrails={},
        schedule=None,
        subscribed_topics=["test_bus"],
    )
    db.add(sender)
    db.add(receiver)
    db.commit()
    db.refresh(sender)
    db.refresh(receiver)

    received = []
    stop_event = asyncio.Event()

    async def consumer():
        async for message in subscribe("test_bus", str(receiver.id)):
            received.append(message)
            if len(received) >= 10:
                stop_event.set()
                break

    consumer_task = asyncio.create_task(consumer())

    for _ in range(10):
        publish(
            topic="test_bus",
            payload={"content": "payload"},
            sender_id=sender.id,
            idempotency_key="dup-key",
        )
    await asyncio.wait_for(stop_event.wait(), timeout=5)
    assert len(received) == 1
    assert received[0].topic == "test_bus"
    assert received[0].sender_id == sender.id
    assert received[0].receiver_id == receiver.id
    assert queue_stats()["pending"] == 0
    assert queue_stats()["delivered"] >= 1

    consumer_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer_task


@pytest.mark.asyncio
async def test_retry_and_dead_letter(db):
    sender = Agent(
        name="Retry Sender",
        role="Sender",
        system_prompt="Send messages.",
        model="gpt-4o-mini",
        tools=[{"name": "memory"}],
        channels=["web"],
        memory_enabled=True,
        guardrails={},
        schedule=None,
        subscribed_topics=["broken_topic"],
    )
    receiver = Agent(
        name="Broken Receiver",
        role="Receiver",
        system_prompt="Receive messages.",
        model="gpt-4o-mini",
        tools=[{"name": "memory"}],
        channels=["web"],
        memory_enabled=True,
        guardrails={},
        schedule=None,
        subscribed_topics=["broken_topic"],
    )
    db.add(sender)
    db.add(receiver)
    db.commit()
    db.refresh(sender)
    db.refresh(receiver)

    publish(
        topic="broken_topic",
        payload={"content": "should fail"},
        sender_id=sender.id,
        idempotency_key="retry-key",
    )

    message = db.query(AgentMessage).filter(AgentMessage.sender_id == sender.id).first()
    assert message is not None

    class FailingQueue:
        async def put(self, _):
            raise RuntimeError("consumer failure")

    from app.messaging import bus

    async with bus.subscription_lock:
        topic_map = bus.subscriptions.setdefault("broken_topic", {})
        topic_map[str(receiver.id)] = FailingQueue()

    async def process_once():
        stop = asyncio.Event()
        task = asyncio.create_task(bus.consumer_loop(stop_event=stop))
        await asyncio.sleep(1)
        stop.set()
        await task

    task = asyncio.create_task(process_once())
    await task

    db.refresh(message)
    assert message.retry_count >= 1
    if message.retry_count >= 3:
        assert db.query(DeadLetterMessage).filter(DeadLetterMessage.original_message_id == message.id).count() == 1


@pytest.mark.asyncio
async def test_p2p_message_routing(client, db):
    from app.messaging.p2p_router import MessageRouter, p2p_background_worker
    
    sender = Agent(
        name="P2P Sender", role="Sender", model="gpt-4o-mini", tools=[], channels=["web"]
    )
    receiver = Agent(
        name="P2P Receiver", role="Receiver", model="gpt-4o-mini", tools=[], channels=["web"]
    )
    db.add(sender)
    db.add(receiver)
    db.commit()
    db.refresh(sender)
    db.refresh(receiver)

    msg = await MessageRouter.send_message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        content="hello direct peer",
        session_id="session-123"
    )
    assert msg.status == "pending"
    assert msg.session_id == "session-123"
    assert msg.correlation_id is not None

    stop = asyncio.Event()
    worker_task = asyncio.create_task(p2p_background_worker(stop))
    await asyncio.sleep(1.5)
    stop.set()
    await worker_task

    db.refresh(msg)
    success = await MessageRouter.acknowledge_message(msg.id)
    assert success is True
    db.refresh(msg)
    assert msg.status == "acked"
