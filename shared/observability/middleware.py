"""Middleware for FastAPI and Celery integration.

Provides request correlation and wide-event emission for HTTP and task processing.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Callable, Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .correlation import get_or_create_request_id, get_or_create_correlation_id, set_request_id, set_correlation_id
from .events import (
    APIRequestEvent,
    AuthContext,
    ArticleContext,
    Outcome,
    ErrorDetails,
    emit_wide_event,
)

logger = logging.getLogger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware to extract/generate correlation and request IDs.

    This should be installed BEFORE WideEventMiddleware.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate request ID
        request_id = get_or_create_request_id(
            request.headers.get("x-request-id")
        )

        # Extract or generate correlation ID
        correlation_id = get_or_create_correlation_id(
            request.headers.get("x-correlation-id")
        )

        # Attach to request state for route handlers to access
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Include IDs in response headers
        response.headers["x-request-id"] = request_id
        if correlation_id:
            response.headers["x-correlation-id"] = correlation_id

        return response


class WideEventMiddleware(BaseHTTPMiddleware):
    """Middleware to emit wide events for HTTP requests.

    This captures the complete request/response lifecycle and emits
    a single canonical event with all context.
    """

    def __init__(
        self,
        app: ASGIApp,
        service_name: str = "api-gateway",
        version: str = "unknown",
        deployment_id: str = "local",
    ):
        super().__init__(app)
        self.service_name = service_name
        self.version = version
        self.deployment_id = deployment_id

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # Get correlation IDs from request state (set by CorrelationMiddleware)
        request_id = getattr(request.state, "request_id", None)
        correlation_id = getattr(request.state, "correlation_id", None)

        # Initialize wide event (attach to request for handlers to enrich)
        wide_event = APIRequestEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_id=request_id or "unknown",
            correlation_id=correlation_id,
            service=self.service_name,
            version=self.version,
            deployment_id=self.deployment_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        # Attach to request state for route handlers to enrich
        request.state.wide_event = wide_event

        # Process request
        try:
            response = await call_next(request)

            # Update event with response details
            wide_event.status_code = response.status_code
            wide_event.duration_ms = int((time.time() - start_time) * 1000)
            wide_event.outcome = (
                Outcome.ERROR if response.status_code >= 500 else Outcome.SUCCESS
            )

            return response

        except Exception as exc:
            # Log unhandled exceptions
            duration_ms = int((time.time() - start_time) * 1000)

            wide_event.status_code = 500
            wide_event.duration_ms = duration_ms
            wide_event.outcome = Outcome.ERROR
            wide_event.error = ErrorDetails(
                type=type(exc).__name__,
                message=str(exc),
                code="unhandled_exception",
                retriable=False,
            )

            # Emit event before re-raising
            emit_wide_event(wide_event)

            # Return error response
            return JSONResponse(
                status_code=500,
                content={"error": "internal_server_error", "message": "An unexpected error occurred"},
                headers={
                    "x-request-id": request_id or "unknown",
                }
            )

        finally:
            # Emit wide event (if not already emitted in exception handler)
            if wide_event.duration_ms is not None:
                emit_wide_event(wide_event)


def enrich_api_event(
    request: Request,
    *,
    auth: Optional[AuthContext] = None,
    article: Optional[ArticleContext] = None,
    **kwargs,
) -> None:
    """Enrich the wide event with business context.

    Call this from route handlers to add context to the request's wide event.

    Args:
        request: The FastAPI request object
        auth: Authentication context
        article: Article context
        **kwargs: Additional fields to add to the event
    """
    wide_event: Optional[APIRequestEvent] = getattr(request.state, "wide_event", None)

    if wide_event is None:
        logger.warning("No wide event found on request - is middleware installed?")
        return

    if auth is not None:
        wide_event.auth = auth

    if article is not None:
        wide_event.article = article

    # Add any additional fields
    for key, value in kwargs.items():
        if hasattr(wide_event, key):
            setattr(wide_event, key, value)
