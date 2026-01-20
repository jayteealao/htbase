"""
Prometheus metrics for HTBase microservices.

Provides centralized metric definitions for HTTP requests, Celery tasks,
archive processing, and summarization.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, REGISTRY

# Use default registry for all metrics
registry = REGISTRY

# =============================================================================
# HTTP Request Metrics (API Gateway)
# =============================================================================

http_requests_total = Counter(
    'htbase_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    'htbase_http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    registry=registry,
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# =============================================================================
# Celery Task Metrics
# =============================================================================

celery_tasks_dispatched_total = Counter(
    'htbase_celery_tasks_dispatched_total',
    'Total Celery tasks dispatched',
    ['task_name', 'queue'],
    registry=registry,
)

celery_queue_depth = Gauge(
    'htbase_celery_queue_depth',
    'Number of tasks in Celery queue',
    ['queue'],
    registry=registry,
)

# =============================================================================
# Archive Worker Metrics
# =============================================================================

archive_tasks_total = Counter(
    'htbase_archive_tasks_total',
    'Total archive tasks by archiver and status',
    ['archiver', 'status'],
    registry=registry,
)

archive_task_duration_seconds = Histogram(
    'htbase_archive_task_duration_seconds',
    'Archive task duration in seconds',
    ['archiver', 'status'],
    registry=registry,
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

archive_file_size_bytes = Histogram(
    'htbase_archive_file_size_bytes',
    'Archive file size in bytes',
    ['archiver'],
    registry=registry,
    buckets=[1024, 10240, 102400, 1024000, 10240000, 102400000],
)

archive_command_duration_seconds = Histogram(
    'htbase_archive_command_duration_seconds',
    'Archive command execution duration in seconds',
    ['archiver'],
    registry=registry,
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

# =============================================================================
# Summarization Worker Metrics
# =============================================================================

summarization_tasks_total = Counter(
    'htbase_summarization_tasks_total',
    'Total summarization tasks by provider and status',
    ['provider', 'status'],
    registry=registry,
)

summarization_task_duration_seconds = Histogram(
    'htbase_summarization_task_duration_seconds',
    'Summarization task duration in seconds',
    ['provider'],
    registry=registry,
    buckets=[1, 2, 5, 10, 30, 60, 120],
)

summarization_tokens_used = Histogram(
    'htbase_summarization_tokens_used',
    'Tokens used per summarization request',
    ['provider', 'model'],
    registry=registry,
    buckets=[100, 500, 1000, 2000, 5000, 10000],
)

# =============================================================================
# GCS Storage Metrics
# =============================================================================

gcs_upload_duration_seconds = Histogram(
    'htbase_gcs_upload_duration_seconds',
    'GCS upload duration in seconds',
    ['archiver'],
    registry=registry,
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

gcs_upload_total = Counter(
    'htbase_gcs_upload_total',
    'Total GCS uploads by status',
    ['archiver', 'status'],
    registry=registry,
)

# =============================================================================
# Firestore Metrics
# =============================================================================

firestore_operations_total = Counter(
    'htbase_firestore_operations_total',
    'Total Firestore operations by type and status',
    ['operation', 'collection', 'status'],
    registry=registry,
)

firestore_operation_duration_seconds = Histogram(
    'htbase_firestore_operation_duration_seconds',
    'Firestore operation duration in seconds',
    ['operation', 'collection'],
    registry=registry,
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

# =============================================================================
# Webhook Metrics
# =============================================================================

webhook_deliveries_total = Counter(
    'htbase_webhook_deliveries_total',
    'Total webhook deliveries by status',
    ['status'],
    registry=registry,
)

webhook_delivery_duration_seconds = Histogram(
    'htbase_webhook_delivery_duration_seconds',
    'Webhook delivery duration in seconds',
    registry=registry,
    buckets=[0.1, 0.5, 1, 2, 5, 10],
)
