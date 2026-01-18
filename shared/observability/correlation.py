"""Correlation ID and request ID management for distributed tracing.

Provides thread-local and context-aware correlation across services.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

# Context variables for async-safe correlation
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def generate_request_id() -> str:
    """Generate a new request ID.

    Returns:
        A unique request ID with 'req_' prefix
    """
    return f"req_{uuid.uuid4().hex[:16]}"


def generate_correlation_id() -> str:
    """Generate a new correlation ID.

    Returns:
        A unique correlation ID with 'corr_' prefix
    """
    return f"corr_{uuid.uuid4().hex[:16]}"


def get_request_id() -> Optional[str]:
    """Get the current request ID from context.

    Returns:
        The current request ID, or None if not set
    """
    return _request_id.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID in context.

    Args:
        request_id: The request ID to set
    """
    _request_id.set(request_id)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context.

    Returns:
        The current correlation ID, or None if not set
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in context.

    Args:
        correlation_id: The correlation ID to set
    """
    _correlation_id.set(correlation_id)


def get_or_create_request_id(header_value: Optional[str] = None) -> str:
    """Get existing request ID or create a new one.

    Args:
        header_value: Optional request ID from HTTP header

    Returns:
        The existing or newly created request ID
    """
    # Priority: header > context > generate new
    if header_value:
        set_request_id(header_value)
        return header_value

    existing = get_request_id()
    if existing:
        return existing

    new_id = generate_request_id()
    set_request_id(new_id)
    return new_id


def get_or_create_correlation_id(header_value: Optional[str] = None) -> str:
    """Get existing correlation ID or create a new one.

    Args:
        header_value: Optional correlation ID from HTTP header

    Returns:
        The existing or newly created correlation ID
    """
    # Priority: header > context > generate new
    if header_value:
        set_correlation_id(header_value)
        return header_value

    existing = get_correlation_id()
    if existing:
        return existing

    new_id = generate_correlation_id()
    set_correlation_id(new_id)
    return new_id
