from app.llm.router import MODEL_TIERS, route_request
from app.models.database import SessionLocal
from app.models.models import TelemetryEvent


def test_routing_by_complexity_and_cost_logging(db, monkeypatch):
    calls = []

    def fake_invoke(model_name, prompt, config):
        calls.append(model_name)
        return f"{model_name}:{prompt[:10]}"

    monkeypatch.setattr("app.llm.router._invoke_model", fake_invoke)

    samples = [
        ("hello", "simple"),
        ("please summarize this short text", "simple"),
        ("can you compare two approaches for me in detail", "moderate"),
        (" ".join(["word"] * 90), "moderate"),
        (" ".join(["word"] * 220), "complex"),
    ]

    for prompt, expected in samples:
        result = route_request(prompt, {})
        assert result["complexity"] == expected
        assert result["model"] in MODEL_TIERS.values()
        assert result["cost"] >= 0

    with SessionLocal() as session:
        telemetry = session.query(TelemetryEvent).filter(TelemetryEvent.event_type == "llm_route_success").all()
    assert len(telemetry) == len(samples)
    assert len(calls) == len(samples)


def test_primary_failure_triggers_fallback_and_logs_telemetry(db, monkeypatch):
    attempts = {"count": 0}

    def fake_invoke(model_name, prompt, config):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("primary timeout")
        return "fallback success"

    monkeypatch.setattr("app.llm.router._invoke_model", fake_invoke)

    result = route_request("Explain the architecture", {"model": "custom-model"})

    assert result["response"] == "fallback success"
    assert result["fallback_used"] is True
    assert attempts["count"] >= 2

    with SessionLocal() as session:
        failures = session.query(TelemetryEvent).filter(TelemetryEvent.event_type == "llm_route_failure").count()
        successes = session.query(TelemetryEvent).filter(TelemetryEvent.event_type == "llm_route_success").count()
    assert failures >= 1
    assert successes >= 1
