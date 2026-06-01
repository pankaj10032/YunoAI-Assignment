"""
Correlation ID Middleware
=========================
Generates or propagates an ``X-Correlation-ID`` header for every HTTP request
and attaches it to the structured logging context so every log line emitted
during the request lifecycle carries the same identifier.

Usage
-----
Add to the FastAPI app **before** any business-logic middleware::

    from app.middleware.correlation_id import CorrelationIDMiddleware
    app.add_middleware(CorrelationIDMiddleware)
"""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.utils.observability import set_request_context

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Correlation-ID"


def _generate_correlation_id() -> str:
    """Return a compact hex UUID."""
    return uuid.uuid4().hex


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Starlette/FastAPI middleware that ensures every request has a correlation ID.

    * Reads ``X-Correlation-ID`` from the incoming request headers.
    * Generates a new UUID if the header is absent or empty.
    * Stores the ID in:
      - ``request.state.correlation_id`` — available to route handlers.
      - The structured logging context (``observability.set_request_context``).
    * Echoes the ID back in the response via ``X-Correlation-ID``.
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        correlation_id: str = (
            request.headers.get(HEADER_NAME, "").strip() or _generate_correlation_id()
        )

        request.state.correlation_id = correlation_id
        set_request_context(
            correlation_id=correlation_id,
            step=request.url.path,
        )

        logger.debug(
            "Request started",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
            },
        )

        response: Response = await call_next(request)
        response.headers[HEADER_NAME] = correlation_id
        return response
