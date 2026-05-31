from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.models.database import SessionLocal
from app.models.models import QuotaCounter


logger = logging.getLogger(__name__)

DEFAULT_LIMITS = {
    "max_req_per_min": 10,
    "max_tokens_per_hr": 10_000,
    "max_concurrent": 3,
}


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    retry_after: int


def check_limit(entity_id: str, type: str, limits: dict[str, Any] | None = None, tokens: int = 0) -> LimitResult:
    session = SessionLocal()
    try:
        return _check_limit(session, entity_id, type, limits or {}, tokens)
    finally:
        session.close()


class QuotaLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        quota_info = _extract_quota_info(request)
        if not quota_info:
            return await call_next(request)

        session = SessionLocal()
        try:
            result = _check_limit(session, **quota_info)
            if not result.allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded",
                        "entity_id": quota_info["entity_id"],
                        "type": quota_info["type"],
                        "retry_after": result.retry_after,
                    },
                    headers={"Retry-After": str(result.retry_after)},
                )

            _increment_concurrent(session, quota_info["entity_id"], quota_info["type"])
            try:
                response = await call_next(request)
                return response
            finally:
                _finalize_usage(session, **quota_info)
        finally:
            session.close()


def _extract_quota_info(request: Request) -> dict[str, Any] | None:
    entity_id = request.headers.get("x-entity-id") or request.headers.get("x-quota-entity")
    quota_type = request.headers.get("x-quota-type")
    path = request.url.path
    if path.startswith("/api/agents/") and path.endswith("/execute"):
        match = re.match(r"^/api/agents/(?P<agent_id>[^/]+)/execute$", path)
        path_agent_id = match.group("agent_id") if match else None
        entity_id = entity_id or (f"agent:{path_agent_id}" if path_agent_id else None)
        quota_type = quota_type or "agent"
    if path.startswith("/api/quotas/"):
        return None
    if path.startswith("/api/") and not entity_id:
        return None
    if not entity_id:
        return None
    return {
        "entity_id": str(entity_id),
        "type": str(quota_type or "channel"),
        "limits": _parse_limits(request),
        "tokens": _estimate_tokens(request),
    }


def _parse_limits(request: Request) -> dict[str, Any]:
    limits: dict[str, Any] = {}
    headers = request.headers
    for key in DEFAULT_LIMITS:
        header_key = f"x-{key.replace('_', '-')}"
        if header_key in headers:
            try:
                limits[key] = int(headers[header_key])
            except ValueError:
                pass
    return limits


def _estimate_tokens(request: Request) -> int:
    content_length = request.headers.get("content-length")
    try:
        return max(1, int(content_length or "1") // 12)
    except ValueError:
        return 1


def _check_limit(session: Session, entity_id: str, type: str, limits: dict[str, Any], tokens: int) -> LimitResult:
    effective = {**DEFAULT_LIMITS, **limits}
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=1)
    reset_at = now + timedelta(minutes=1)
    counter = _get_counter(session, entity_id, type, now, reset_at)
    counter_window_start = _ensure_aware(counter.window_start)
    counter_reset_at = _ensure_aware(counter.reset_at)
    if counter_window_start < window_start or counter_reset_at <= now:
        counter.window_start = now
        counter.reset_at = reset_at
        counter.requests_count = 0
        counter.tokens_used = 0
        counter.concurrent_count = 0
        counter_window_start = now
        counter_reset_at = reset_at

    if counter.concurrent_count >= int(effective["max_concurrent"]):
        return LimitResult(False, max(1, int((counter_reset_at - now).total_seconds())))
    if counter.requests_count >= int(effective["max_req_per_min"]):
        return LimitResult(False, max(1, int((counter_reset_at - now).total_seconds())))
    if counter.tokens_used + tokens > int(effective["max_tokens_per_hr"]):
        return LimitResult(False, max(1, int((counter_reset_at - now).total_seconds())))

    return LimitResult(True, 0)


def _increment_concurrent(session: Session, entity_id: str, type: str) -> None:
    now = datetime.now(timezone.utc)
    reset_at = now + timedelta(minutes=1)
    counter = _get_counter(session, entity_id, type, now, reset_at)
    counter.concurrent_count += 1
    session.commit()


def _finalize_usage(session: Session, entity_id: str, type: str, limits: dict[str, Any], tokens: int) -> None:
    now = datetime.now(timezone.utc)
    reset_at = now + timedelta(minutes=1)
    counter = _get_counter(session, entity_id, type, now, reset_at)
    counter.requests_count += 1
    counter.tokens_used += tokens
    counter.concurrent_count = max(0, counter.concurrent_count - 1)
    session.commit()
    logger.info(
        "quota updated entity=%s type=%s requests=%s tokens=%s",
        entity_id,
        type,
        counter.requests_count,
        counter.tokens_used,
    )


def _get_counter(session: Session, entity_id: str, type: str, now: datetime, reset_at: datetime) -> QuotaCounter:
    counter = (
        session.query(QuotaCounter)
        .filter(QuotaCounter.entity_id == entity_id, QuotaCounter.quota_type == type)
        .one_or_none()
    )
    if not counter:
        counter = QuotaCounter(
            entity_id=entity_id,
            quota_type=type,
            requests_count=0,
            tokens_used=0,
            concurrent_count=0,
            window_start=now,
            reset_at=reset_at,
        )
        session.add(counter)
        session.commit()
        session.refresh(counter)
    return counter


def quota_status(entity_id: str | None = None, type: str | None = None, db: Session | None = None) -> dict[str, Any]:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        query = session.query(QuotaCounter)
        if entity_id:
            query = query.filter(QuotaCounter.entity_id == entity_id)
        if type:
            query = query.filter(QuotaCounter.quota_type == type)
        counters = query.all()
        now = datetime.now(timezone.utc)
        return {
            "limits": DEFAULT_LIMITS,
            "current_usage": [
                {
                    "entity_id": counter.entity_id,
                    "type": counter.quota_type,
                    "requests_count": counter.requests_count,
                    "tokens_used": counter.tokens_used,
                    "concurrent_count": counter.concurrent_count,
                    "window_start": _ensure_aware(counter.window_start).isoformat(),
                    "reset_at": _ensure_aware(counter.reset_at).isoformat(),
                    "retry_after": max(0, int((_ensure_aware(counter.reset_at) - now).total_seconds())),
                }
                for counter in counters
            ],
            "reset_time": (
                min((_ensure_aware(counter.reset_at) for counter in counters), default=now).isoformat()
                if counters
                else now.isoformat()
            ),
        }
    finally:
        if owns_session:
            session.close()


def release_limit(entity_id: str, type: str, db: Session | None = None) -> None:
    session = db or SessionLocal()
    owns_session = db is None
    try:
        counter = (
            session.query(QuotaCounter)
            .filter(QuotaCounter.entity_id == entity_id, QuotaCounter.quota_type == type)
            .one_or_none()
        )
        if counter:
            counter.concurrent_count = max(0, counter.concurrent_count - 1)
            session.commit()
    finally:
        if owns_session:
            session.close()


def _ensure_aware(value: datetime) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
