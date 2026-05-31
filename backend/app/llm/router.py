from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import SessionLocal
from app.models.models import TelemetryEvent
from app.utils.observability import get_request_context


logger = logging.getLogger(__name__)

MODEL_TIERS = {
    "cheap": "gpt-4o-mini" if settings.llm_provider == "openai" else settings.ollama_model,
    "mid": "gpt-4.1-mini" if settings.llm_provider == "openai" else settings.ollama_model,
    "premium": "gpt-4.1" if settings.llm_provider == "openai" else settings.ollama_model,
}

PRICE_TABLE = {
    "gpt-4o-mini": {"input": 0.00000015, "output": 0.00000060},
    "gpt-4.1-mini": {"input": 0.00000035, "output": 0.00000140},
    "gpt-4.1": {"input": 0.00000200, "output": 0.00000800},
    settings.ollama_model: {"input": 0.0, "output": 0.0},
}


@dataclass(frozen=True)
class RoutingDecision:
    complexity: str
    tier: str
    model: str


def route_request(prompt: str, config: dict[str, Any]) -> dict[str, Any]:
    session = SessionLocal()
    try:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt is required")

        decision = _select_model(prompt, config)
        chain = _fallback_chain(decision.model)
        last_error: Exception | None = None

        for attempt, model_name in enumerate(chain, start=1):
            try:
                response_text = _invoke_model(model_name, prompt, config)
                usage = _estimate_usage(prompt, response_text, model_name)
                telemetry = _log_telemetry(
                    session,
                    "llm_route_success",
                    {
                        "prompt": prompt,
                        "model": model_name,
                        "tier": decision.tier,
                        "complexity": decision.complexity,
                        "cost": usage["cost"],
                        "attempt": attempt,
                    },
                )
                return {
                    "response": response_text,
                    "model": model_name,
                    "tier": decision.tier,
                    "complexity": decision.complexity,
                    "cost": usage["cost"],
                    "usage": usage,
                    "telemetry_event_id": telemetry.id,
                    "fallback_used": attempt > 1,
                }
            except Exception as exc:
                last_error = exc
                _log_telemetry(
                    session,
                    "llm_route_failure",
                    {
                        "prompt": prompt,
                        "model": model_name,
                        "tier": decision.tier,
                        "complexity": decision.complexity,
                        "error": str(exc),
                        "attempt": attempt,
                    },
                )

        fallback_message = _fallback_message(prompt, decision, last_error)
        usage = _estimate_usage(prompt, fallback_message, decision.model)
        telemetry = _log_telemetry(
            session,
            "llm_route_fallback",
            {
                "prompt": prompt,
                "model": decision.model,
                "tier": decision.tier,
                "complexity": decision.complexity,
                "error": str(last_error) if last_error else "unknown",
                "cost": usage["cost"],
            },
        )
        return {
            "response": fallback_message,
            "model": decision.model,
            "tier": decision.tier,
            "complexity": decision.complexity,
            "cost": usage["cost"],
            "usage": usage,
            "telemetry_event_id": telemetry.id,
            "fallback_used": True,
            "fallback_message": True,
        }
    finally:
        session.close()


def _select_model(prompt: str, config: dict[str, Any]) -> RoutingDecision:
    override = config.get("model")
    if override:
        tier = _tier_for_model(str(override))
        return RoutingDecision(
            complexity=_classify_complexity(prompt, config),
            tier=tier,
            model=str(override),
        )
    complexity = _classify_complexity(prompt, config)
    tier = {"simple": "cheap", "moderate": "mid", "complex": "premium"}[complexity]
    return RoutingDecision(complexity=complexity, tier=tier, model=MODEL_TIERS[tier])


def _classify_complexity(prompt: str, config: dict[str, Any]) -> str:
    length = len(prompt.split())
    if config.get("complexity"):
        return str(config["complexity"])
    if length <= 6 and prompt.count("?") <= 1:
        return "simple"
    if length <= 120 and prompt.count("\n") <= 4:
        return "moderate"
    return "complex"


def _fallback_chain(primary_model: str) -> list[str]:
    ordered = [primary_model]
    for tier in ("mid", "premium", "cheap"):
        model = MODEL_TIERS[tier]
        if model not in ordered:
            ordered.append(model)
    return ordered


def _invoke_model(model_name: str, prompt: str, config: dict[str, Any]) -> str:
    provider = config.get("provider") or settings.llm_provider
    if provider == "ollama":
        return _call_ollama(model_name, prompt, config)
    return _call_openai(model_name, prompt, config)


def _call_openai(model_name: str, prompt: str, config: dict[str, Any]) -> str:
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("OpenAI client is not installed") from exc

    client = OpenAI(api_key=config.get("api_key") or settings.openai_api_key, timeout=config.get("timeout", 20), max_retries=0)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": config.get("system_prompt") or "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=float(config.get("temperature", 0.2)),
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned an empty response")
    return content


def _call_ollama(model_name: str, prompt: str, config: dict[str, Any]) -> str:
    try:
        import requests
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("requests is not installed") from exc

    base_url = config.get("base_url") or settings.ollama_base_url
    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={"model": model_name, "prompt": prompt, "stream": False},
        timeout=config.get("timeout", 20),
    )
    response.raise_for_status()
    data = response.json()
    text = data.get("response") or data.get("message") or ""
    if not text:
        raise RuntimeError("Ollama returned an empty response")
    return text


def _estimate_usage(prompt: str, response_text: str, model_name: str) -> dict[str, Any]:
    input_tokens = max(1, math.ceil(len(prompt.split()) * 1.3))
    output_tokens = max(1, math.ceil(len(response_text.split()) * 1.3))
    pricing = PRICE_TABLE.get(model_name, PRICE_TABLE.get(settings.openai_model, {"input": 0.0, "output": 0.0}))
    cost = round(input_tokens * pricing["input"] + output_tokens * pricing["output"], 8)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost": cost,
        "model": model_name,
    }


def _fallback_message(prompt: str, decision: RoutingDecision, error: Exception | None) -> str:
    reason = str(error) if error else "an unknown error"
    return (
        f"Fallback response: the {decision.tier} model could not complete this request "
        f"after routing it as {decision.complexity}. Last error: {reason}"
    )


def _tier_for_model(model_name: str) -> str:
    if model_name == MODEL_TIERS["premium"]:
        return "premium"
    if model_name == MODEL_TIERS["mid"]:
        return "mid"
    return "cheap"


def _log_telemetry(session: Session, event_type: str, payload: dict[str, Any]) -> TelemetryEvent:
    event = TelemetryEvent(
        event_type=event_type,
        source="llm_router",
        payload={**payload, "correlation_id": get_request_context().get("correlation_id")},
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    logger.info("LLM route event: %s", payload)
    return event
