"""Wide-event observability for HTBase microservices.

Provides canonical log lines with tail sampling for context-rich, queryable observability.
"""

from .events import (
    WideEvent,
    APIRequestEvent,
    ArchiveProcessingEvent,
    SummarizationEvent,
    emit_wide_event,
)
from .correlation import (
    get_correlation_id,
    set_correlation_id,
    get_request_id,
    set_request_id,
    generate_request_id,
)
from .sampling import should_sample
from .middleware import correlation_middleware, wide_event_middleware

__all__ = [
    # Event types
    "WideEvent",
    "APIRequestEvent",
    "ArchiveProcessingEvent",
    "SummarizationEvent",
    "emit_wide_event",
    # Correlation
    "get_correlation_id",
    "set_correlation_id",
    "get_request_id",
    "set_request_id",
    "generate_request_id",
    # Sampling
    "should_sample",
    # Middleware
    "correlation_middleware",
    "wide_event_middleware",
]
