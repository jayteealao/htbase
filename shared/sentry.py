"""
Sentry error tracking initialization for HTBase services.

Provides centralized Sentry configuration with appropriate integrations
for FastAPI and Celery services.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _filter_sensitive_data(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Filter sensitive data from Sentry events before sending.

    Args:
        event: Sentry event dict
        hint: Additional context about the event

    Returns:
        Filtered event or None to drop
    """
    # Filter sensitive headers
    if "request" in event:
        request = event["request"]
        if "headers" in request:
            headers = request["headers"]
            sensitive_headers = ["authorization", "x-api-key", "cookie", "x-auth-token"]
            for header in sensitive_headers:
                if header in headers:
                    headers[header] = "[Filtered]"

    # Filter sensitive query params
    if "request" in event and "query_string" in event["request"]:
        qs = event["request"]["query_string"]
        if "api_key" in qs.lower() or "token" in qs.lower():
            event["request"]["query_string"] = "[Filtered]"

    return event


def init_sentry_fastapi(
    dsn: Optional[str],
    environment: str,
    version: str,
    service_name: str,
    traces_sample_rate: float = 0.1,
) -> bool:
    """Initialize Sentry for FastAPI applications.

    Args:
        dsn: Sentry DSN (None to skip initialization)
        environment: Environment name (development, staging, production)
        version: Application version
        service_name: Service name for tagging
        traces_sample_rate: Performance tracing sample rate

    Returns:
        True if Sentry was initialized, False otherwise
    """
    if not dsn:
        logger.info("Sentry DSN not configured, skipping initialization")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=f"htbase@{version}",
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
            ],
            traces_sample_rate=traces_sample_rate,
            before_send=_filter_sensitive_data,
            send_default_pii=False,
        )

        # Set service tag
        sentry_sdk.set_tag("service", service_name)

        logger.info(
            f"Sentry initialized for {service_name}",
            extra={
                "environment": environment,
                "version": version,
                "traces_sample_rate": traces_sample_rate,
            },
        )
        return True

    except ImportError:
        logger.warning("sentry-sdk not installed, skipping Sentry initialization")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def init_sentry_celery(
    dsn: Optional[str],
    environment: str,
    version: str,
    service_name: str,
    traces_sample_rate: float = 0.1,
) -> bool:
    """Initialize Sentry for Celery workers.

    Args:
        dsn: Sentry DSN (None to skip initialization)
        environment: Environment name (development, staging, production)
        version: Application version
        service_name: Service name for tagging
        traces_sample_rate: Performance tracing sample rate

    Returns:
        True if Sentry was initialized, False otherwise
    """
    if not dsn:
        logger.info("Sentry DSN not configured, skipping initialization")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=f"htbase@{version}",
            integrations=[
                CeleryIntegration(),
            ],
            traces_sample_rate=traces_sample_rate,
            before_send=_filter_sensitive_data,
            send_default_pii=False,
        )

        # Set service tag
        sentry_sdk.set_tag("service", service_name)

        logger.info(
            f"Sentry initialized for {service_name}",
            extra={
                "environment": environment,
                "version": version,
                "traces_sample_rate": traces_sample_rate,
            },
        )
        return True

    except ImportError:
        logger.warning("sentry-sdk not installed, skipping Sentry initialization")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False
