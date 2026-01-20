"""Wide-event observability for HTBase microservices.

Provides canonical log lines with tail sampling for context-rich, queryable observability.
"""

from .events import (
    WideEvent,
    APIRequestEvent,
    ArchiveProcessingEvent,
    SummarizationEvent,
    Outcome,
    ErrorDetails,
    AuthContext,
    ArticleContext,
    ArchiveRequestContext,
    emit_wide_event,
)
from .correlation import (
    get_correlation_id,
    set_correlation_id,
    get_request_id,
    set_request_id,
    generate_request_id,
    get_or_create_request_id,
    get_or_create_correlation_id,
)
from .sampling import should_sample, configure_sampling
from .middleware import (
    CorrelationMiddleware,
    WideEventMiddleware,
    enrich_api_event,
)
from .celery_integration import (
    setup_celery_signals,
    ArchiveTaskContext,
    SummarizationTaskContext,
)
from .prometheus import (
    PrometheusMiddleware,
    get_metrics_response,
)

__all__ = [
    # Event types
    "WideEvent",
    "APIRequestEvent",
    "ArchiveProcessingEvent",
    "SummarizationEvent",
    "Outcome",
    "ErrorDetails",
    "AuthContext",
    "ArticleContext",
    "ArchiveRequestContext",
    "emit_wide_event",
    # Correlation
    "get_correlation_id",
    "set_correlation_id",
    "get_request_id",
    "set_request_id",
    "generate_request_id",
    "get_or_create_request_id",
    "get_or_create_correlation_id",
    # Sampling
    "should_sample",
    "configure_sampling",
    # Middleware
    "CorrelationMiddleware",
    "WideEventMiddleware",
    "enrich_api_event",
    # Celery integration
    "setup_celery_signals",
    "ArchiveTaskContext",
    "SummarizationTaskContext",
    # Prometheus
    "PrometheusMiddleware",
    "get_metrics_response",
]
