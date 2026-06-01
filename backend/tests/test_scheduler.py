from app.models.models import Agent


def test_schedule_status_and_pause_resume(client, db, agent_payload):
    agent_payload["schedule"] = {
        "enabled": True,
        "cron": "*/1 * * * *",
        "timezone": "UTC",
    }
    agent = Agent(**agent_payload)
    db.add(agent)
    db.commit()
    db.refresh(agent)

    response = client.get("/api/schedules/status")
    assert response.status_code == 200
    schedules = response.json()["schedules"]
    assert any(item["agent_id"] == agent.id for item in schedules)
    agent_status = next(item for item in schedules if item["agent_id"] == agent.id)
    assert agent_status["enabled"] is True
    assert agent_status["paused"] is False
    assert agent_status["cron"] == "*/1 * * * *"

    pause_response = client.post("/api/schedules/pause", json={"agent_id": agent.id})
    assert pause_response.status_code == 200
    assert pause_response.json()["enabled"] is False
    assert pause_response.json()["paused"] is True

    resume_response = client.post("/api/schedules/resume", json={"agent_id": agent.id})
    assert resume_response.status_code == 200
    assert resume_response.json()["enabled"] is True
    assert resume_response.json()["paused"] is False


def test_scheduler_missed_run_backfill(client, db, agent_payload):
    from datetime import datetime, timezone, timedelta
    from app.models.models import SchedulerMissedRun
    agent_payload["schedule"] = {
        "enabled": True,
        "cron": "*/5 * * * *",
        "timezone": "UTC",
    }
    agent = Agent(**agent_payload)
    agent.last_run_at = datetime.now(timezone.utc) - timedelta(minutes=25)
    db.add(agent)
    db.commit()
    db.refresh(agent)

    # Add a pending missed run manually to verify backfill processing
    missed = SchedulerMissedRun(
        agent_id=agent.id,
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        status="pending",
        reason="restart_backfill"
    )
    db.add(missed)
    db.commit()

    # Trigger scheduler backfill manually to test
    import asyncio
    from app.scheduler.engine import SchedulerEngine
    engine = SchedulerEngine()
    asyncio.run(engine._run_backfill())

    db.refresh(missed)
    assert missed.status in ("processed", "skipped")
