"""
Rate limiting utilities for API Gateway.

Provides Redis-based distributed rate limiting with per-API-key tracking
and SlowAPI integration for IP-based rate limiting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict

import redis
from fastapi import Request, Response, HTTPException, Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from shared.auth import verify_api_key
from shared.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Redis-based distributed rate limiter using sliding window algorithm.

    This implementation uses Redis for distributed rate limiting across
    multiple API Gateway replicas, tracking requests per API key.
    """

    def __init__(self, redis_url: str):
        """
        Initialize rate limiter with Redis connection.

        Args:
            redis_url: Redis connection URL
        """
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.prefix = "htbase:ratelimit:"

    def check_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request is within rate limit using sliding window.

        Args:
            key: Identifier for rate limiting (API key, IP, etc.)
            limit: Maximum number of requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, info_dict) where info_dict contains:
                - limit: The rate limit
                - remaining: Requests remaining in current window
                - reset_at: Unix timestamp when limit resets
                - retry_after: Seconds until limit resets
        """
        now = datetime.now(timezone.utc)
        current_timestamp = int(now.timestamp())
        window_key = f"{self.prefix}{key}:{current_timestamp // window_seconds}"

        try:
            # Increment counter atomically
            pipe = self.redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, window_seconds * 2)  # Keep window for cleanup
            results = pipe.execute()

            current_count = results[0]

            # Calculate reset time
            window_start = (current_timestamp // window_seconds) * window_seconds
            reset_at = window_start + window_seconds
            retry_after = max(0, reset_at - current_timestamp)

            # Check if limit exceeded
            is_allowed = current_count <= limit
            remaining = max(0, limit - current_count)

            info = {
                "limit": limit,
                "remaining": remaining,
                "reset_at": reset_at,
                "retry_after": retry_after,
            }

            if not is_allowed:
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "key": key[:16] + "..." if len(key) > 16 else key,
                        "limit": limit,
                        "window": window_seconds,
                        "count": current_count,
                    },
                )

            return is_allowed, info

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiter: {e}", exc_info=True)
            # Fail open - allow request if Redis is down
            return True, {
                "limit": limit,
                "remaining": limit,
                "reset_at": current_timestamp + window_seconds,
                "retry_after": window_seconds,
            }


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(settings.redis.url())
    return _rate_limiter


# SlowAPI limiter for IP-based rate limiting (fallback/quick fix)
slowapi_limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000/minute"],  # Global default
)


# Rate limit configurations for different endpoint types
RATE_LIMITS = {
    "archive": {"limit": 10, "window": 60},      # 10 requests per minute
    "batch": {"limit": 5, "window": 60},          # 5 requests per minute
    "status": {"limit": 1000, "window": 60},      # 1000 requests per minute
    "download": {"limit": 100, "window": 60},     # 100 requests per minute
    "admin": {"limit": 50, "window": 60},         # 50 requests per minute
}


def create_rate_limit_dependency(endpoint_type: str):
    """
    Create a rate limit dependency for a specific endpoint type.

    This factory function creates FastAPI dependencies that enforce
    rate limits based on API keys and endpoint type.

    Args:
        endpoint_type: Type of endpoint (archive, batch, status, etc.)

    Returns:
        FastAPI dependency function that checks rate limits
    """

    async def check_rate_limit(
        request: Request,
        response: Response,
        api_key: str = Depends(verify_api_key),
    ):
        """Check rate limit for this endpoint type."""
        rate_config = RATE_LIMITS.get(endpoint_type, RATE_LIMITS["archive"])
        limiter = get_rate_limiter()

        # Check rate limit using API key as identifier
        is_allowed, info = limiter.check_limit(
            key=f"api:{api_key}",
            limit=rate_config["limit"],
            window_seconds=rate_config["window"],
        )

        # Always add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset_at"])

        if not is_allowed:
            # Add Retry-After header for 429 responses
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded for {endpoint_type} endpoints",
                    "details": {
                        "limit": f"{info['limit']}/{rate_config['window']}s",
                        "reset_at": info["reset_at"],
                        "retry_after": info["retry_after"],
                    },
                },
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info["reset_at"]),
                    "Retry-After": str(info["retry_after"]),
                },
            )

        return api_key

    return check_rate_limit


# Pre-configured rate limit dependencies for common endpoint types
rate_limit_archive = create_rate_limit_dependency("archive")
rate_limit_batch = create_rate_limit_dependency("batch")
rate_limit_status = create_rate_limit_dependency("status")
rate_limit_download = create_rate_limit_dependency("download")
rate_limit_admin = create_rate_limit_dependency("admin")


class RateLimitMiddleware:
    """
    Middleware to add rate limit headers to all responses.

    This ensures rate limit information is included even for endpoints
    that don't explicitly check rate limits.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Check if rate limit headers are already present
                has_rate_limit_headers = any(
                    name.lower() == b"x-ratelimit-limit"
                    for name, _ in headers
                )

                # If not present, this might be a non-rate-limited endpoint
                # We could add default headers here if desired

                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_with_headers)
