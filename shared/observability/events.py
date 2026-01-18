"""Wide-event data structures for HTBase microservices.

Provides canonical event types for API requests, archive processing, and summarization.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from enum import Enum

logger = logging.getLogger(__name__)


class Outcome(str, Enum):
    """Event outcome status."""

    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ErrorDetails:
    """Error information for wide events."""

    type: str  # Error class name
    message: str  # Error message
    code: str  # Application error code
    retriable: bool = False  # Can this be retried?
    provider_code: Optional[str] = None  # External provider error code
    command_exit_code: Optional[int] = None  # For command execution errors


@dataclass
class WideEvent:
    """Base wide event with common fields.

    This is the foundation for all wide events in HTBase.
    """

    # Correlation
    timestamp: str
    request_id: str
    correlation_id: Optional[str] = None

    # Service context
    service: str = "htbase"
    version: str = "unknown"
    deployment_id: str = "local"

    # Outcome
    outcome: Outcome = Outcome.SUCCESS
    duration_ms: Optional[int] = None

    # Error details (if outcome == ERROR)
    error: Optional[ErrorDetails] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for logging.

        Returns:
            Dictionary representation with proper serialization
        """
        data = asdict(self)

        # Convert enums to values
        if "outcome" in data:
            data["outcome"] = data["outcome"].value if isinstance(data["outcome"], Enum) else data["outcome"]

        # Remove None values for cleaner logs
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class AuthContext:
    """Authentication context for API requests."""

    api_key_id: Optional[str] = None  # Hashed API key ID
    user_id: Optional[str] = None
    tier: Literal["free", "premium", "enterprise"] = "free"
    authenticated: bool = False


@dataclass
class ArticleContext:
    """Article information context."""

    id: str
    url: str  # Must be sanitized before logging
    exists: Optional[bool] = None  # Was this a new submission or update?
    title: Optional[str] = None


@dataclass
class ArchiveRequestContext:
    """Archive request details."""

    archivers_requested: List[str] = field(default_factory=list)
    celery_task_ids: Dict[str, str] = field(default_factory=dict)


@dataclass
class APIRequestEvent(WideEvent):
    """Wide event for API Gateway HTTP requests.

    Represents one complete HTTP request/response cycle.
    """

    # HTTP details
    method: str = "GET"
    path: str = "/"
    status_code: int = 200

    # Authentication
    auth: Optional[AuthContext] = None

    # Business context
    article: Optional[ArticleContext] = None
    archive_request: Optional[ArchiveRequestContext] = None

    # Request metadata
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class CommandExecution:
    """Command execution metrics."""

    exit_code: int
    duration_ms: int
    timeout_ms: int


@dataclass
class StorageMetrics:
    """Storage operation metrics."""

    gcs_path: str
    file_size_bytes: int
    upload_duration_ms: int


@dataclass
class WebhookContext:
    """Webhook notification details."""

    sent: bool
    workflow_id: str
    event: str  # e.g., "archive.completed"
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None


@dataclass
class ProcessingContext:
    """Archive processing details."""

    duration_ms: int
    outcome: Outcome
    retry_attempt: int = 0
    max_retries: int = 3

    command: Optional[CommandExecution] = None
    storage: Optional[StorageMetrics] = None


@dataclass
class ArchiveProcessingEvent(WideEvent):
    """Wide event for Archive Worker task processing.

    Represents one complete archive task execution.
    """

    # Task context
    task_id: str = ""  # Celery task ID
    archiver: str = "unknown"  # singlefile, screenshot, pdf, etc.

    # Article context
    article: Optional[ArticleContext] = None

    # Processing details
    processing: Optional[ProcessingContext] = None

    # Webhook notification (if triggered)
    webhook: Optional[WebhookContext] = None


@dataclass
class SummarizationMetrics:
    """Summarization processing metrics."""

    provider: str  # openai, huggingface
    model: str  # gpt-4o-mini, etc.
    duration_ms: int
    outcome: Outcome
    retry_attempt: int = 0

    # Generation metrics
    tokens_used: Optional[int] = None
    summary_length_chars: Optional[int] = None
    entities_extracted: Optional[int] = None
    tags_generated: Optional[int] = None


@dataclass
class CostContext:
    """Cost tracking for AI workloads."""

    provider_cost_usd: Optional[float] = None
    tokens_charged: Optional[int] = None


@dataclass
class ContentContext:
    """Content being summarized."""

    source: str  # Which archive was used: readability, singlefile, etc.
    content_length_chars: int
    word_count: Optional[int] = None


@dataclass
class SummarizationEvent(WideEvent):
    """Wide event for Summarization Worker processing.

    Represents one complete summarization task.
    """

    # Task context
    task_id: str = ""  # Celery task ID

    # Article context
    article: Optional[ArticleContext] = None

    # Content being summarized
    content: Optional[ContentContext] = None

    # AI/ML processing
    summarization: Optional[SummarizationMetrics] = None

    # Cost tracking
    cost: Optional[CostContext] = None


def emit_wide_event(event: WideEvent) -> None:
    """Emit a wide event to logging system.

    Args:
        event: The wide event to emit
    """
    from .sampling import should_sample

    # Apply tail sampling
    if not should_sample(event):
        return

    # Convert to dict and log
    event_dict = event.to_dict()

    # Use appropriate log level based on outcome
    if event.outcome == Outcome.ERROR:
        logger.error("wide_event", extra=event_dict)
    else:
        logger.info("wide_event", extra=event_dict)
