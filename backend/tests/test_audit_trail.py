from sqlalchemy import text

from app.models.models import AuditEvent

from .conftest import create_agent


def test_audit_trail_records_ordered_events_and_is_immutable(client, db, monkeypatch):
    agent = create_agent(client)
    monkeypatch.setattr("app.agents.runtime.AgentRuntime.execute_single_agent", lambda self, agent_id, task_description: "done")

    response = client.post(
        f"/api/agents/{agent['id']}/execute",
        json={"task_description": "run this"},
        headers={"X-Correlation-ID": "audit-corr-1"},
    )
    assert response.status_code == 202

    run_id = response.json()["run_id"]
    timeline = client.get(f"/api/audit/run/{run_id}")
    assert timeline.status_code == 200
    events = timeline.json()["events"]
    assert events
    assert [event["event_type"] for event in events] == sorted([event["event_type"] for event in events], key=lambda _: events.index(next(e for e in events if e["event_type"] == _)))
    assert all("payload" in event and "created_at" in event for event in events)

    audit_row = db.query(AuditEvent).filter(AuditEvent.run_id == run_id).first()
    assert audit_row is not None

    with db.bind.begin() as conn:
        failed = False
        try:
            conn.execute(text("UPDATE audit_events SET event_type = 'mutated' WHERE id = :id"), {"id": audit_row.id})
        except Exception:
            failed = True
    assert failed
