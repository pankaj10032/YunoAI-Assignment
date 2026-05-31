import asyncio
import concurrent.futures

from app.messaging.queue import acknowledge, consume, publish, queue_stats, replay_interrupted, retry
from app.models.models import Agent, AgentMessage, DeadLetterMessage


def test_concurrent_messages_preserve_fifo_order(db):
    def publish_one(index):
        return publish(
            None,
            None,
            {"content": f"message-{index}", "sequence": index},
        ).id

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        ids = list(executor.map(publish_one, range(20)))

    expected_sequences = [row.payload["sequence"] for row in db.query(AgentMessage).order_by(AgentMessage.id.asc()).all()]
    consumed = []
    while True:
        message = consume(db)
        if not message:
            break
        consumed.append(message.payload["sequence"])
        acknowledge(message.id, db)

    assert consumed == expected_sequences
    assert queue_stats(db)["pending"] == 0


def test_processing_message_replays_after_consumer_crash(db):
    sender = _create_agent(db, "Crash Sender")
    receiver = _create_agent(db, "Crash Receiver")
    original = publish(sender.id, receiver.id, {"content": "survive"}, db)

    claimed = consume(db)
    assert claimed.id == original.id
    assert claimed.status == "processing"

    replayed = replay_interrupted(db)
    assert replayed == 1
    replayed_message = consume(db)
    assert replayed_message.id == original.id


def test_malformed_payload_retries_then_moves_to_dlq(db):
    bad_message = publish(None, None, {"oops": "missing content"}, db)
    claimed = consume(db)
    assert claimed.id == bad_message.id
    for _ in range(3):
        retry(claimed.id, "payload.content is required", db)
    db.expire_all()

    failed = db.get(AgentMessage, bad_message.id)
    dlq_message = db.query(DeadLetterMessage).one()
    assert failed.status == "failed"
    assert failed.retry_count == 3
    assert dlq_message.original_message_id == bad_message.id
    assert "payload.content is required" in dlq_message.error_reason
    assert queue_stats(db)["dlq"] == 1


def test_queue_stats_endpoint(client, db):
    response = client.get("/api/messaging/queue/stats")

    assert response.status_code == 200
    assert response.json() == {
        "pending": 0,
        "processing": 0,
        "failed": 0,
        "dlq": 0,
    }


def _create_agent(db, name):
    agent = Agent(
        name=name,
        role="Messaging Agent",
        system_prompt="Participate in queue tests.",
        model="gpt-4o-mini",
        tools=[],
        channels=["web"],
        memory_enabled=True,
        guardrails={},
        schedule=None,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent
