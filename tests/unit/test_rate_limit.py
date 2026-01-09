"""
Tests for rate limiting functionality.

Tests both Redis-based rate limiter and SlowAPI integration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import time

from shared.rate_limit import (
    RateLimiter,
    create_rate_limit_dependency,
    RATE_LIMITS,
    get_rate_limiter,
)


class TestRateLimiter:
    """Tests for Redis-based RateLimiter class."""

    def test_rate_limiter_initialization(self):
        """Test that rate limiter initializes with Redis connection."""
        limiter = RateLimiter("redis://localhost:6379/0")
        assert limiter.redis is not None
        assert limiter.prefix == "htbase:ratelimit:"

    @patch("shared.rate_limit.redis")
    def test_check_limit_allows_requests_within_limit(self, mock_redis):
        """Test that requests within rate limit are allowed."""
        # Mock Redis client
        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.return_value = [5, True]  # Current count is 5
        mock_client.pipeline.return_value = mock_pipeline
        mock_redis.from_url.return_value = mock_client

        limiter = RateLimiter("redis://localhost:6379/0")
        is_allowed, info = limiter.check_limit("test-key", limit=10, window_seconds=60)

        assert is_allowed is True
        assert info["limit"] == 10
        assert info["remaining"] == 5
        assert info["reset_at"] > 0
        assert info["retry_after"] >= 0

    @patch("shared.rate_limit.redis")
    def test_check_limit_blocks_requests_over_limit(self, mock_redis):
        """Test that requests over rate limit are blocked."""
        # Mock Redis client
        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.return_value = [11, True]  # Current count is 11
        mock_client.pipeline.return_value = mock_pipeline
        mock_redis.from_url.return_value = mock_client

        limiter = RateLimiter("redis://localhost:6379/0")
        is_allowed, info = limiter.check_limit("test-key", limit=10, window_seconds=60)

        assert is_allowed is False
        assert info["limit"] == 10
        assert info["remaining"] == 0
        assert info["reset_at"] > 0
        assert info["retry_after"] >= 0

    @patch("shared.rate_limit.redis")
    def test_check_limit_sets_expiry_on_first_request(self, mock_redis):
        """Test that expiry is set on the first request in a window."""
        # Mock Redis client
        mock_client = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute.return_value = [1, True]  # First request
        mock_client.pipeline.return_value = mock_pipeline
        mock_redis.from_url.return_value = mock_client

        limiter = RateLimiter("redis://localhost:6379/0")
        limiter.check_limit("test-key", limit=10, window_seconds=60)

        # Verify expiry was set
        mock_pipeline.expire.assert_called_once()

    @patch("shared.rate_limit.redis")
    def test_check_limit_fails_open_on_redis_error(self, mock_redis):
        """Test that rate limiter allows requests if Redis is down (fail open)."""
        # Mock Redis client to raise error
        mock_client = MagicMock()
        mock_client.pipeline.side_effect = Exception("Redis connection failed")
        mock_redis.from_url.return_value = mock_client

        limiter = RateLimiter("redis://localhost:6379/0")
        is_allowed, info = limiter.check_limit("test-key", limit=10, window_seconds=60)

        # Should fail open (allow request)
        assert is_allowed is True
        assert info["limit"] == 10

    def test_check_limit_calculates_reset_time_correctly(self):
        """Test that reset time is calculated correctly for sliding window."""
        with patch("shared.rate_limit.redis") as mock_redis:
            mock_client = MagicMock()
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [1, True]
            mock_client.pipeline.return_value = mock_pipeline
            mock_redis.from_url.return_value = mock_client

            limiter = RateLimiter("redis://localhost:6379/0")
            is_allowed, info = limiter.check_limit("test-key", limit=10, window_seconds=60)

            now = int(datetime.now(timezone.utc).timestamp())
            window_start = (now // 60) * 60
            expected_reset = window_start + 60

            assert info["reset_at"] == expected_reset
            assert info["retry_after"] >= 0
            assert info["retry_after"] <= 60


class TestRateLimitDependencies:
    """Tests for FastAPI rate limit dependencies."""

    def test_rate_limit_configurations_exist(self):
        """Test that all rate limit configurations are defined."""
        assert "archive" in RATE_LIMITS
        assert "batch" in RATE_LIMITS
        assert "status" in RATE_LIMITS
        assert "download" in RATE_LIMITS
        assert "admin" in RATE_LIMITS

        # Verify archive limits (10/minute)
        assert RATE_LIMITS["archive"]["limit"] == 10
        assert RATE_LIMITS["archive"]["window"] == 60

        # Verify batch limits (5/minute)
        assert RATE_LIMITS["batch"]["limit"] == 5
        assert RATE_LIMITS["batch"]["window"] == 60

        # Verify status limits (1000/minute)
        assert RATE_LIMITS["status"]["limit"] == 1000
        assert RATE_LIMITS["status"]["window"] == 60

    @pytest.mark.asyncio
    async def test_rate_limit_dependency_allows_within_limit(self):
        """Test that rate limit dependency allows requests within limit."""
        with patch("shared.rate_limit.get_rate_limiter") as mock_get_limiter:
            # Mock rate limiter to allow request
            mock_limiter = MagicMock()
            mock_limiter.check_limit.return_value = (
                True,
                {"limit": 10, "remaining": 5, "reset_at": 1000, "retry_after": 30},
            )
            mock_get_limiter.return_value = mock_limiter

            # Create dependency
            check_func = create_rate_limit_dependency("archive")

            # Mock request and response
            mock_request = Mock()
            mock_response = Mock()
            mock_response.headers = {}

            # Call dependency
            api_key = await check_func(mock_request, mock_response, api_key="test-key")

            # Verify it returns the API key
            assert api_key == "test-key"

            # Verify headers were set
            assert mock_response.headers["X-RateLimit-Limit"] == "10"
            assert mock_response.headers["X-RateLimit-Remaining"] == "5"
            assert mock_response.headers["X-RateLimit-Reset"] == "1000"

    @pytest.mark.asyncio
    async def test_rate_limit_dependency_blocks_over_limit(self):
        """Test that rate limit dependency blocks requests over limit."""
        from fastapi import HTTPException

        with patch("shared.rate_limit.get_rate_limiter") as mock_get_limiter:
            # Mock rate limiter to block request
            mock_limiter = MagicMock()
            mock_limiter.check_limit.return_value = (
                False,
                {"limit": 10, "remaining": 0, "reset_at": 1000, "retry_after": 30},
            )
            mock_get_limiter.return_value = mock_limiter

            # Create dependency
            check_func = create_rate_limit_dependency("archive")

            # Mock request and response
            mock_request = Mock()
            mock_response = Mock()
            mock_response.headers = {}

            # Call dependency - should raise HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await check_func(mock_request, mock_response, api_key="test-key")

            # Verify exception details
            assert exc_info.value.status_code == 429
            assert "RATE_LIMIT_EXCEEDED" in str(exc_info.value.detail)
            assert "Retry-After" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_rate_limit_dependency_uses_correct_limits_per_endpoint(self):
        """Test that different endpoint types use different rate limits."""
        with patch("shared.rate_limit.get_rate_limiter") as mock_get_limiter:
            mock_limiter = MagicMock()
            mock_limiter.check_limit.return_value = (
                True,
                {"limit": 10, "remaining": 5, "reset_at": 1000, "retry_after": 30},
            )
            mock_get_limiter.return_value = mock_limiter

            mock_request = Mock()
            mock_response = Mock()
            mock_response.headers = {}

            # Test archive endpoint (10/minute)
            archive_func = create_rate_limit_dependency("archive")
            await archive_func(mock_request, mock_response, api_key="test-key")
            mock_limiter.check_limit.assert_called_with(
                key="api:test-key", limit=10, window_seconds=60
            )

            # Test batch endpoint (5/minute)
            batch_func = create_rate_limit_dependency("batch")
            await batch_func(mock_request, mock_response, api_key="test-key")
            mock_limiter.check_limit.assert_called_with(
                key="api:test-key", limit=5, window_seconds=60
            )

            # Test status endpoint (1000/minute)
            status_func = create_rate_limit_dependency("status")
            await status_func(mock_request, mock_response, api_key="test-key")
            mock_limiter.check_limit.assert_called_with(
                key="api:test-key", limit=1000, window_seconds=60
            )


class TestRateLimitMiddleware:
    """Tests for rate limit middleware."""

    @pytest.mark.asyncio
    async def test_middleware_passes_through_non_http_requests(self):
        """Test that middleware passes through non-HTTP requests."""
        from shared.rate_limit import RateLimitMiddleware

        mock_app = Mock()
        middleware = RateLimitMiddleware(mock_app)

        scope = {"type": "websocket"}
        receive = Mock()
        send = Mock()

        await middleware(scope, receive, send)

        # Should call app directly
        mock_app.assert_called_once()


class TestRateLimitIntegration:
    """Integration tests for rate limiting with FastAPI."""

    def test_rate_limits_are_applied_to_endpoints(self):
        """Test that rate limits are configured on API endpoints."""
        # This is a smoke test to ensure imports work
        from shared.rate_limit import (
            rate_limit_archive,
            rate_limit_batch,
            rate_limit_status,
            rate_limit_download,
            rate_limit_admin,
        )

        # Verify all pre-configured dependencies exist
        assert rate_limit_archive is not None
        assert rate_limit_batch is not None
        assert rate_limit_status is not None
        assert rate_limit_download is not None
        assert rate_limit_admin is not None


class TestSlowAPIIntegration:
    """Tests for SlowAPI fallback rate limiter."""

    def test_slowapi_limiter_is_configured(self):
        """Test that SlowAPI limiter is properly configured."""
        from shared.rate_limit import slowapi_limiter

        assert slowapi_limiter is not None
        assert slowapi_limiter.default_limits == ["1000/minute"]

    def test_slowapi_key_function_uses_remote_address(self):
        """Test that SlowAPI uses remote address for IP-based limiting."""
        from shared.rate_limit import slowapi_limiter
        from slowapi.util import get_remote_address

        # Verify key function is set correctly
        assert slowapi_limiter.key_func == get_remote_address
