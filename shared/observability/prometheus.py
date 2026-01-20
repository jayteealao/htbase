"""
Prometheus metrics middleware for FastAPI.

Provides automatic request/response instrumentation with Prometheus metrics.
"""

import time
import re
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from shared.metrics import (
    http_requests_total,
    http_request_duration_seconds,
)


def normalize_path(path: str) -> str:
    """Normalize path to reduce cardinality by replacing IDs with placeholders.

    Examples:
        /api/v1/archives/abc123 -> /api/v1/archives/{id}
        /api/v1/artifacts/abc123/singlefile -> /api/v1/artifacts/{id}/{archiver}
    """
    # Replace UUIDs
    path = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '{id}',
        path,
        flags=re.IGNORECASE
    )
    # Replace numeric IDs
    path = re.sub(r'/\d+(?=/|$)', '/{id}', path)
    # Replace alphanumeric IDs (at least 8 chars, likely IDs)
    path = re.sub(r'/[a-zA-Z0-9_-]{8,}(?=/|$)', '/{id}', path)
    return path


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware that records Prometheus metrics for HTTP requests."""

    # Paths to exclude from metrics (health checks, metrics endpoint itself)
    EXCLUDED_PATHS = {'/health', '/metrics', '/'}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Normalize path for metric labels
        normalized_path = normalize_path(request.url.path)
        method = request.method

        # Track request duration
        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.time() - start_time

            # Record metrics
            http_requests_total.labels(
                method=method,
                endpoint=normalized_path,
                status_code=status_code,
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=normalized_path,
            ).observe(duration)

        return response


def get_metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
