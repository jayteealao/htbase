# Observability Review Report

**Project:** HTBase - Microservices Archiving Platform
**Scope:** Full codebase - API Gateway, Archive Workers, Summarization Workers
**Date:** 2026-01-20
**Reviewer:** Claude Code

---

## Summary

- **Total Findings:** 7
- **BLOCKER:** 0 | **HIGH:** 4 | **MED:** 3 | **LOW:** 0 | **NIT:** 0

**Category Breakdown:**
- Logs (Wide Events): ✅ **Excellent** - Full implementation with tail sampling
- Metrics (Golden Signals): ❌ **Missing** - No instrumentation (4 HIGH findings)
- Tracing (Distributed): ⚠️ **Partial** - Correlation IDs present, no OpenTelemetry spans (1 MED)
- Error Reporting: ❌ **Missing** - No Sentry/error tracking service (1 HIGH)
- Alertability: ❌ **Missing** - No automated alerting (1 MED)
- Runbooks: ❌ **Missing** - No incident response documentation (1 MED)

---

## Observability Posture

### Critical Paths Reviewed

| Endpoint | Logs | Metrics | Tracing | Errors | Alerts | Runbooks |
|----------|------|---------|---------|--------|--------|----------|
| `POST /api/v1/archives` | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| `GET /api/v1/archives/{id}` | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| `DELETE /api/v1/archives/{id}` | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| `GET /api/v1/system/stats` | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| `GET /api/v1/tasks/queue-stats` | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| Archive Worker Tasks | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |
| Summarization Tasks | ✅ | ❌ | ⚠️ | ❌ | ❌ | ❌ |

**Legend:**
- ✅ Complete (has business context, golden signals, etc.)
- ⚠️ Partial (correlation IDs present, but missing spans/metrics)
- ❌ Missing (no instrumentation)

---

## Key Strengths

### 1. Excellent Wide-Event Logging Implementation ✅

The codebase has a **production-grade wide-event logging system** that follows best practices from loggingsucks.com:

**Strengths:**
- **Canonical log lines**: One log per request/task with full context
- **Business context**: Includes article IDs, URLs, archivers, user context
- **Correlation IDs**: Request and correlation IDs for distributed tracing
- **Tail sampling**: Intelligent sampling (100% errors, slow requests, VIPs; 5% normal traffic)
- **Structured events**: Well-designed dataclasses for API, archive, and summarization events
- **Middleware integration**: Automatic enrichment via FastAPI middleware

**Files:**
- `shared/observability/events.py` - Event data structures (APIRequestEvent, ArchiveProcessingEvent, SummarizationEvent)
- `shared/observability/middleware.py` - WideEventMiddleware for automatic event emission
- `shared/observability/sampling.py` - Tail sampling logic
- `shared/observability/celery_integration.py` - Task context managers

**Example from archive worker:**
```python
# services/archive-worker/app/celery_tasks.py:223
with ArchiveTaskContext(
    task_id=self.request.id,
    archiver=archiver_name,
    item_id=item_id,
    url=sanitize_url_for_logging(url),
    service_name="archive-worker",
    version="2.0.0",
) as ctx:
    result = _execute_archive_task(...)
    ctx.mark_success(
        exit_code=result.get("exit_code", 0),
        gcs_path=result.get("gcs_path"),
        file_size_bytes=result.get("file_size"),
    )
```

This implementation is **far ahead of industry standard** for logging. Most companies don't have this level of sophistication.

---

## Key Gaps

### Category: Metrics (Golden Signals) - ❌ CRITICAL GAP

**Summary:** No metrics instrumentation found. Cannot detect latency spikes, error rates, or saturation issues.

---

## Findings

### OBS-1: No Metrics for API Gateway Endpoints (Can't Detect Latency Spikes) [HIGH]

**Evidence:**
**File:** `services/api-gateway/app/routes/archives.py:72`
```python
@router.post("/archives", response_model=TaskAccepted)
async def create_archive(
    req: Request,
    response: Response,
    request: CreateArchiveRequest,
    api_key: str = Depends(rate_limit_archive),
    article_repo: ArticleRepoType = None,
):
    # ❌ No metrics tracked
    # Dispatch Celery tasks
    result = group(all_tasks).apply_async()
    return TaskAccepted(task_id=request_id, count=total_tasks)
```

**Observability Gap:**
No metrics tracked for archive endpoint:
- **No latency histogram** (can't see p95, p99)
- **No error counter** (can't see error rate)
- **No traffic counter** (can't see requests/sec)
- **No task dispatch metrics** (can't see queue backlog)

**Can't answer:**
- "Is the archive endpoint getting slower?"
- "What's the error rate for archive requests?"
- "Are we handling more traffic than usual?"
- "How many tasks are queued vs. processing?"

**Impact:**
- **Detection**: Can't detect latency regressions automatically
- **Alerting**: No alerts for performance degradation
- **Dashboards**: No visibility into API health

**Severity:** HIGH
**Category:** Metrics (Golden Signals)
**Confidence:** High

**Remediation:**

Add Prometheus metrics to API Gateway. First, create `shared/metrics.py`:

```python
"""Prometheus metrics for HTBase services."""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import os

# Use custom registry to avoid conflicts
registry = CollectorRegistry()

# API Gateway metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint', 'status_code'],
    registry=registry,
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

celery_tasks_dispatched_total = Counter(
    'celery_tasks_dispatched_total',
    'Total Celery tasks dispatched',
    ['task_name', 'queue'],
    registry=registry,
)

celery_queue_depth = Gauge(
    'celery_queue_depth',
    'Number of tasks in queue',
    ['queue'],
    registry=registry,
)

# Archive worker metrics
archive_tasks_total = Counter(
    'archive_tasks_total',
    'Total archive tasks',
    ['archiver', 'status'],
    registry=registry,
)

archive_task_duration_seconds = Histogram(
    'archive_task_duration_seconds',
    'Archive task duration',
    ['archiver', 'status'],
    registry=registry,
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

archive_file_size_bytes = Histogram(
    'archive_file_size_bytes',
    'Archive file size',
    ['archiver'],
    registry=registry,
    buckets=[1024, 10240, 102400, 1024000, 10240000, 102400000],
)
```

Then instrument the archive endpoint in `services/api-gateway/app/routes/archives.py`:

```python
# ✅ AFTER: With metrics
import time
from shared.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    celery_tasks_dispatched_total,
)

@router.post("/archives", response_model=TaskAccepted)
async def create_archive(
    req: Request,
    response: Response,
    request: CreateArchiveRequest,
    api_key: str = Depends(rate_limit_archive),
    article_repo: ArticleRepoType = None,
):
    start_time = time.time()
    status = "success"

    try:
        # ... existing code ...

        # Track task dispatch metrics
        for archiver in archivers:
            celery_tasks_dispatched_total.labels(
                task_name=f"archive_{archiver}",
                queue=f"archive.{archiver}",
            ).inc(len(request.items))

        return TaskAccepted(task_id=request_id, count=total_tasks)

    except Exception as e:
        status = "error"
        raise
    finally:
        # Track request metrics
        duration = time.time() - start_time

        http_requests_total.labels(
            method="POST",
            endpoint="/api/v1/archives",
            status_code=response.status_code if status == "success" else 500,
        ).inc()

        http_request_duration_seconds.labels(
            method="POST",
            endpoint="/api/v1/archives",
            status_code=response.status_code if status == "success" else 500,
        ).observe(duration)
```

Add Prometheus endpoint to `services/api-gateway/app/main.py`:

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from shared.metrics import registry

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )
```

**Why This Fix:**

**Metrics enable:**

1. **Latency monitoring:**
```promql
# p95 latency for archive endpoint
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{endpoint="/api/v1/archives"}[5m])
)
```

2. **Error rate monitoring:**
```promql
# Error rate (%)
sum(rate(http_requests_total{endpoint="/api/v1/archives",status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total{endpoint="/api/v1/archives"}[5m]))
```

3. **Queue depth monitoring:**
```promql
# Queue depth by archiver type
celery_queue_depth
```

---

### OBS-2: No Metrics for Archive Worker Tasks (Can't Measure Task Performance) [HIGH]

**Evidence:**
**File:** `services/archive-worker/app/celery_tasks.py:232`
```python
def archiver_task(self, item_id: str, url: str, **kwargs) -> dict:
    with ArchiveTaskContext(...) as ctx:
        result = _execute_archive_task(...)
        ctx.mark_success(...)  # ❌ Only logs, doesn't track metrics
        return result
```

**Observability Gap:**
Archive tasks emit wide events but don't track metrics:
- **No task duration histogram** (can't see p95, p99 by archiver)
- **No success/failure counters** (can't see error rate by archiver)
- **No file size histogram** (can't see storage patterns)
- **No command execution metrics** (can't see browser/tool performance)

**Can't answer:**
- "Which archiver is slowest?"
- "What's the success rate for singlefile vs. readability?"
- "Are we experiencing a spike in failures?"
- "How much storage are we using per archiver?"

**Impact:**
- **Performance**: Can't identify slow archivers
- **Reliability**: Can't detect archiver-specific issues
- **Capacity**: Can't predict storage growth

**Severity:** HIGH
**Category:** Metrics (Golden Signals)
**Confidence:** High

**Remediation:**

Instrument archive worker tasks in `services/archive-worker/app/celery_tasks.py`:

```python
# ✅ AFTER: With metrics
import time
from shared.metrics import (
    archive_tasks_total,
    archive_task_duration_seconds,
    archive_file_size_bytes,
)

def archiver_task(self, item_id: str, url: str, **kwargs) -> dict:
    start_time = time.time()

    with ArchiveTaskContext(...) as ctx:
        try:
            result = _execute_archive_task(...)

            # Track success metrics
            archive_tasks_total.labels(
                archiver=archiver_name,
                status="success",
            ).inc()

            # Track duration
            duration = time.time() - start_time
            archive_task_duration_seconds.labels(
                archiver=archiver_name,
                status="success",
            ).observe(duration)

            # Track file size
            if result.get("file_size"):
                archive_file_size_bytes.labels(
                    archiver=archiver_name,
                ).observe(result["file_size"])

            ctx.mark_success(...)
            return result

        except Exception as e:
            # Track failure metrics
            archive_tasks_total.labels(
                archiver=archiver_name,
                status="error",
            ).inc()

            duration = time.time() - start_time
            archive_task_duration_seconds.labels(
                archiver=archiver_name,
                status="error",
            ).observe(duration)

            ctx.mark_error(...)
            raise
```

**Why This Fix:**

**Query examples:**
```promql
# Average task duration by archiver
avg(rate(archive_task_duration_seconds_sum[5m])) by (archiver)
/ avg(rate(archive_task_duration_seconds_count[5m])) by (archiver)

# Success rate by archiver
sum(rate(archive_tasks_total{status="success"}[5m])) by (archiver)
/
sum(rate(archive_tasks_total[5m])) by (archiver)

# Storage growth rate
rate(archive_file_size_bytes_sum[1h])
```

---

### OBS-3: No Metrics for Queue Depth (Can't Detect Saturation) [HIGH]

**Evidence:**
**File:** `services/api-gateway/app/routes/tasks.py:76`
```python
def _get_queue_length(queue_name: str) -> int:
    """Get approximate queue length from Redis."""
    try:
        r = redis.from_url(settings.redis.url())
        return r.llen(queue_name)  # ❌ Only for API response, not tracked as metric
    except Exception:
        return -1
```

**Observability Gap:**
Queue lengths are only exposed via API endpoint, not as metrics:
- **No queue depth gauge** (can't alert on backlog)
- **No worker concurrency metrics** (can't see if workers are saturated)
- **No task wait time histogram** (can't measure queueing delay)

**Can't answer:**
- "Are we experiencing queue backlog?"
- "Do we need to scale up workers?"
- "How long do tasks wait before processing?"

**Impact:**
- **Saturation**: Can't detect when system is overloaded
- **Capacity**: Can't predict when to scale workers
- **SLAs**: Can't measure end-to-end latency (queue time + processing time)

**Severity:** HIGH
**Category:** Metrics (Saturation)
**Confidence:** High

**Remediation:**

Add background job to track queue metrics in `services/api-gateway/app/main.py`:

```python
# ✅ AFTER: Track queue depth metrics
import asyncio
from shared.metrics import celery_queue_depth

async def update_queue_metrics():
    """Background task to update queue depth metrics."""
    while True:
        try:
            from shared.config import get_settings
            import redis

            settings = get_settings()
            r = redis.from_url(settings.redis.url())

            queues = [
                "archive.singlefile",
                "archive.monolith",
                "archive.readability",
                "archive.pdf",
                "archive.screenshot",
                "summarization",
            ]

            for queue in queues:
                depth = r.llen(queue)
                celery_queue_depth.labels(queue=queue).set(depth)

        except Exception as e:
            logger.error(f"Failed to update queue metrics: {e}")

        # Update every 10 seconds
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Start background queue metrics updater
    queue_metrics_task = asyncio.create_task(update_queue_metrics())

    yield

    # Cleanup
    queue_metrics_task.cancel()
```

**Why This Fix:**

**Alert examples:**
```yaml
# Alert when queue depth exceeds threshold
- alert: HighQueueDepth
  expr: celery_queue_depth > 100
  for: 5m
  annotations:
    summary: "Queue {{ $labels.queue }} has {{ $value }} tasks"

# Alert when queue growing rapidly
- alert: QueueGrowthRate
  expr: |
    rate(celery_queue_depth[5m]) > 10
  for: 5m
  annotations:
    summary: "Queue {{ $labels.queue }} growing at {{ $value }}/min"
```

---

### OBS-4: No Error Reporting Service (Errors Vanish) [HIGH]

**Evidence:**
**File:** `services/api-gateway/app/main.py:116`
```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
        extra={"path": request.url.path},
    )  # ❌ Only logged, no error tracking service
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
```

**Observability Gap:**
Errors are logged but not sent to error tracking service:
- **No error grouping** (can't see patterns)
- **No user context** (can't see affected users)
- **No breadcrumbs** (can't reproduce issues)
- **No release tracking** (can't correlate errors with deploys)
- **No stack traces** (only in logs, not centralized)

**Can't answer:**
- "How many users are affected by this error?"
- "What did the user do before hitting this error?"
- "Did this error start after a recent deploy?"
- "Is this error happening in production or staging?"

**Impact:**
- **MTTR**: 30+ minutes to gather context from logs
- **User impact**: Can't identify how many users affected
- **Debugging**: No breadcrumbs to reproduce issues

**Severity:** HIGH
**Category:** Error Reporting
**Confidence:** High

**Remediation:**

Add Sentry integration. First, add to `requirements.txt`:

```
sentry-sdk[fastapi]==2.0.0
```

Then integrate in `services/api-gateway/app/main.py`:

```python
# ✅ AFTER: With Sentry error tracking
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

def create_app() -> FastAPI:
    settings = get_settings()

    # Initialize Sentry
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=f"htbase@{settings.version}",
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                CeleryIntegration(),
            ],
            traces_sample_rate=0.1,  # 10% of requests
            profiles_sample_rate=0.1,  # 10% profiling
            before_send=_sentry_before_send,
        )

    app = FastAPI(...)

    # Exception handler enriches Sentry context
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # Set Sentry context
        sentry_sdk.set_context("request", {
            "url": str(request.url),
            "method": request.method,
            "headers": dict(request.headers),
        })

        # Set user context (if authenticated)
        if hasattr(request.state, "api_key"):
            sentry_sdk.set_user({"id": request.state.api_key})

        # Capture exception
        sentry_sdk.capture_exception(exc)

        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(...)

    return app

def _sentry_before_send(event, hint):
    """Filter sensitive data before sending to Sentry."""
    # Remove API keys from headers
    if "request" in event:
        headers = event["request"].get("headers", {})
        if "Authorization" in headers:
            headers["Authorization"] = "[Filtered]"

    return event
```

For archive worker, add to `services/archive-worker/app/celery_tasks.py`:

```python
class ArchiveTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # Set Sentry context
        sentry_sdk.set_context("task", {
            "task_id": task_id,
            "archiver": self.name.split("_")[-1],
            "item_id": kwargs.get("item_id"),
            "url": kwargs.get("url"),
        })

        # Capture exception
        sentry_sdk.capture_exception(exc)

        logger.error(f"Archive task failed: {exc}", exc_info=True)
```

**Why This Fix:**

**Sentry benefits:**
1. **Error grouping**: All "card_declined" errors grouped together
2. **User impact**: See "124 users affected by this error"
3. **Breadcrumbs**: "User clicked checkout → loaded cart → payment failed"
4. **Release tracking**: "This error started in release htbase@2.0.1"
5. **Stack traces**: Full stack trace with local variables

---

### OBS-5: No Distributed Tracing with OpenTelemetry Spans [MED]

**Evidence:**
**Files:** Wide events have correlation IDs but no OpenTelemetry spans

**Observability Gap:**
The codebase has excellent correlation IDs (request_id, correlation_id) but no distributed tracing spans:
- **Can trace** requests across services via correlation IDs in logs
- **Cannot visualize** request flow in trace UI (Jaeger, Tempo)
- **Cannot measure** operation-level latency (DB queries, external API calls)
- **Cannot identify** slow operations within a request

**Can't answer:**
- "Which operation is slow: Firestore write or GCS upload?"
- "How long does each archiver spend in browser automation vs. upload?"
- "What's the latency breakdown for archive tasks?"

**Impact:**
- **Performance**: Hard to identify bottlenecks within a request
- **Debugging**: Can't visualize request flow across services
- **Optimization**: Can't measure operation-level performance

**Severity:** MED (Correlation IDs provide basic distributed tracing via logs)
**Category:** Tracing (Distributed)
**Confidence:** High

**Remediation:**

Add OpenTelemetry instrumentation. First, add to `requirements.txt`:

```
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-instrumentation-fastapi==0.43b0
opentelemetry-instrumentation-celery==0.43b0
opentelemetry-exporter-otlp==1.22.0
```

Then instrument API Gateway in `services/api-gateway/app/main.py`:

```python
# ✅ AFTER: With OpenTelemetry tracing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def create_app() -> FastAPI:
    settings = get_settings()

    # Initialize OpenTelemetry
    if settings.otel_endpoint:
        provider = TracerProvider(
            resource=Resource.create({
                "service.name": "api-gateway",
                "service.version": "2.0.0",
                "deployment.environment": settings.environment,
            })
        )

        processor = BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_endpoint)
        )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    app = FastAPI(...)

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    return app
```

Then instrument archive operations:

```python
from opentelemetry import trace

def _execute_archive_task(archiver_name: str, url: str, item_id: str, task_id: str):
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "archive_task",
        attributes={
            "archiver": archiver_name,
            "item_id": item_id,
            "task_id": task_id,
        }
    ) as span:
        # Update status
        with tracer.start_as_current_span("firestore.update_status"):
            update_artifact(item_id=item_id, archiver=archiver_name, status="in_progress")

        # Perform archiving
        with tracer.start_as_current_span("archiver.execute") as archive_span:
            archiver = _get_archiver(archiver_name)
            result = archiver.archive_and_upload_to_gcs(url=url, item_id=item_id)

            archive_span.set_attributes({
                "exit_code": result.exit_code,
                "success": result.success,
            })

        # Upload to GCS (already spans in archiver)

        # Update final status
        with tracer.start_as_current_span("firestore.update_final"):
            update_artifact(item_id=item_id, archiver=archiver_name, status="success", ...)

        return result
```

**Why This Fix:**

**Trace visualization (Jaeger):**
```
archive_task [3500ms]
├─ firestore.update_status   [50ms]
├─ archiver.execute          [3200ms]
│  ├─ browser.launch         [800ms]
│  ├─ browser.navigate       [1200ms]
│  ├─ browser.capture        [900ms]
│  └─ browser.close          [300ms]
├─ gcs.upload                [200ms]
└─ firestore.update_final    [50ms]
```

**Note:** This is MED severity because correlation IDs already enable distributed tracing via log queries. OpenTelemetry adds visualization and operation-level timing, but isn't critical.

---

### OBS-6: No Automated Alerting (Rely on Users to Report Issues) [MED]

**Evidence:**
No Prometheus alert rules found in codebase

**Observability Gap:**
No automated alerting configured:
- **No error rate alerts** (don't know when error rate spikes)
- **No latency alerts** (don't know when API gets slow)
- **No queue depth alerts** (don't know when workers saturated)
- **No success rate alerts** (don't know when archivers failing)

**Current state:**
- Wait for users to complain
- Check logs manually
- React hours after issue starts

**Impact:**
- **MTTR**: Hours (wait for user reports)
- **User experience**: Customers leave after failures
- **Reputation**: Users lose trust after prolonged outages

**Severity:** MED (Can monitor manually via logs/Flower, but not proactive)
**Category:** Alertability
**Confidence:** High

**Remediation:**

Create Prometheus alert rules in `monitoring/alerts/htbase.yaml`:

```yaml
groups:
  - name: api_gateway_alerts
    interval: 1m
    rules:
      # Error rate > 5% for 5 minutes
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status_code=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "API error rate > 5%"
          description: |
            Current error rate: {{ $value | humanizePercentage }}

            **Impact:** Users experiencing failures

            **Check:**
            - Recent deploys: `kubectl rollout history deployment/api-gateway`
            - Error breakdown: Query logs for error types
            - Worker health: Check Flower dashboard

            **Runbook:** https://wiki.company.com/runbooks/api-errors

      # p95 latency > 2s
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 2.0
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "API p95 latency > 2s"
          description: |
            Current p95: {{ $value }}s

            **Check:**
            - Firestore latency
            - Redis latency
            - Worker queue depth

  - name: worker_alerts
    interval: 1m
    rules:
      # Archive task success rate < 80%
      - alert: LowArchiveSuccessRate
        expr: |
          (
            sum(rate(archive_tasks_total{status="success"}[10m])) by (archiver)
            /
            sum(rate(archive_tasks_total[10m])) by (archiver)
          ) < 0.8
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "{{ $labels.archiver }} success rate < 80%"
          description: |
            Current success rate: {{ $value | humanizePercentage }}
            Archiver: {{ $labels.archiver }}

            **Possible causes:**
            - Network issues
            - Target sites blocking
            - Browser crashes

      # Queue depth > 100 tasks for 5 minutes
      - alert: HighQueueDepth
        expr: celery_queue_depth > 100
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Queue {{ $labels.queue }} depth > 100"
          description: |
            Current depth: {{ $value }}

            **Action:** Scale up workers for this queue
```

Configure Alertmanager in `monitoring/alertmanager.yaml`:

```yaml
route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'slack-notifications'

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: '$SLACK_WEBHOOK_URL'
        channel: '#alerts-production'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

**Why This Fix:**

**Before (reactive):**
```
09:00 - Issue starts (error rate 20%)
10:00 - First user complaint
11:00 - Engineer investigates
12:00 - Issue fixed
---
Total: 3 hours downtime
```

**After (proactive):**
```
09:00 - Issue starts (error rate 20%)
09:05 - Alert fires in Slack
09:10 - Engineer opens runbook
09:20 - Issue fixed
---
Total: 20 minutes downtime
```

---

### OBS-7: No Runbooks for Common Failures [MED]

**Evidence:**
No runbook documentation found in codebase

**Observability Gap:**
No runbooks for common operational issues:
- **No debugging steps** for archive failures
- **No common failure modes** documented
- **No remediation actions** (how to fix issues)
- **No escalation paths** (who to contact)

**Impact:**
- **MTTR**: Oncall wastes time figuring out what to check
- **Consistency**: Different engineers debug differently
- **Knowledge loss**: Tribal knowledge not documented

**Severity:** MED
**Category:** Runbooks
**Confidence:** High

**Remediation:**

Create runbooks in `docs/runbooks/` directory:

**1. `docs/runbooks/api-errors.md`**

```markdown
# Runbook: API Gateway Errors

**Alert:** HighErrorRate
**Severity:** Critical
**Team:** Platform

## Symptoms
- Alert: "API error rate > 5%"
- Users reporting errors
- Dashboard shows spike in 5xx responses

## Impact
- Users cannot submit archive requests
- Existing archives may not process

## Diagnosis

### Step 1: Check error breakdown (5 min)

Query logs for error types:
```bash
# Via gcloud (if using Cloud Logging)
gcloud logging read 'resource.type="k8s_container" AND severity>=ERROR' --limit 50 --format json | jq '.[] | .jsonPayload.error.type' | sort | uniq -c
```

Common error types:
- `FirestoreError` → Firestore connectivity issues
- `RedisConnectionError` → Redis/Celery issues
- `ValidationError` → Bad client requests (not our issue)

### Step 2: Check infrastructure health (3 min)

```bash
# Check pod health
kubectl get pods -n htbase

# Check recent restarts
kubectl get pods -n htbase --sort-by='.status.containerStatuses[0].restartCount'

# Check pod logs for crashes
kubectl logs -n htbase deployment/api-gateway --tail=100
```

### Step 3: Check recent deploys (2 min)

```bash
# Check last 5 deployments
kubectl rollout history deployment/api-gateway -n htbase --limit=5

# If recent deploy suspicious, check diff
git diff <previous-sha> <current-sha>
```

### Step 4: Check dependencies (5 min)

```bash
# Check Redis
kubectl exec -it deployment/api-gateway -n htbase -- redis-cli -h redis ping

# Check Firestore (via health endpoint)
curl https://htbase.example.com/health
```

## Remediation

### Firestore Issues

**Diagnosis:** Logs show `FirestoreError: deadline exceeded`

**Action:**
1. Check Firestore quotas in GCP Console
2. If over quota, request increase or wait for reset
3. If not quota, check for slow queries:
   ```bash
   # Check recent slow queries
   gcloud firestore operations list --filter="done:false" --limit=10
   ```

### Redis Connection Issues

**Diagnosis:** Logs show `RedisConnectionError`

**Action:**
1. Check Redis pod health:
   ```bash
   kubectl logs -n htbase deployment/redis --tail=100
   ```
2. If Redis crashed, restart:
   ```bash
   kubectl rollout restart deployment/redis -n htbase
   ```
3. Check Redis memory usage:
   ```bash
   kubectl exec -it deployment/redis -n htbase -- redis-cli INFO memory
   ```

### Recent Deploy Issues

**Diagnosis:** Error spike correlates with recent deploy

**Action:**
1. Rollback to previous version:
   ```bash
   kubectl rollout undo deployment/api-gateway -n htbase
   kubectl rollout status deployment/api-gateway -n htbase
   ```
2. Verify error rate drops
3. Debug in staging, redeploy when fixed

## Prevention

- Add integration tests for Firestore and Redis connectivity
- Add circuit breakers for external dependencies
- Add canary deployments (5% → 50% → 100%)
- Add automated rollback on error rate spike

## Related

- **Dashboard:** https://grafana.company.com/d/htbase-api
- **Logs:** https://console.cloud.google.com/logs
- **Past Incidents:** https://wiki.company.com/incidents/htbase
```

**2. `docs/runbooks/archive-failures.md`**

```markdown
# Runbook: Archive Task Failures

**Alert:** LowArchiveSuccessRate
**Severity:** Warning
**Team:** Platform

## Symptoms
- Alert: "singlefile success rate < 80%"
- Flower shows high failure rate
- Users reporting archive tasks stuck

## Impact
- Archives not completing
- Users not receiving results

## Diagnosis

### Step 1: Check failure breakdown (5 min)

Query wide events for failure reasons:
```bash
# Check error types
gcloud logging read 'jsonPayload.service="archive-worker" AND jsonPayload.outcome="error"' --limit=50 --format json | jq '.[] | .jsonPayload.error.type' | sort | uniq -c
```

Common errors:
- `TimeoutError` → Archive taking too long
- `CommandExecutionError` → Browser/tool crashed
- `GCSUploadError` → GCS connectivity issues
- `FirestoreError` → Firestore write failed

### Step 2: Check worker health (3 min)

```bash
# Check archive worker pods
kubectl get pods -n htbase -l app=archive-worker-singlefile

# Check logs for specific archiver
kubectl logs -n htbase deployment/archive-worker-singlefile --tail=100
```

### Step 3: Check queue depth (2 min)

Check Flower dashboard or query Redis:
```bash
kubectl exec -it deployment/redis -n htbase -- redis-cli LLEN archive.singlefile
```

If queue depth high (>100), workers may be overloaded.

## Remediation

### Timeout Errors

**Diagnosis:** Logs show `TimeoutError: Archive took >300s`

**Action:**
1. Check if specific sites are slow:
   ```bash
   # Query wide events for slow sites
   gcloud logging read 'jsonPayload.service="archive-worker" AND jsonPayload.duration_ms>300000' --limit=20 --format json | jq '.[] | .jsonPayload.article.url'
   ```
2. If specific domains slow, add to blocklist or increase timeout
3. If all sites slow, check network latency

### Browser Crashes

**Diagnosis:** Logs show `CommandExecutionError: exit code 137` (OOM kill)

**Action:**
1. Check memory usage:
   ```bash
   kubectl top pods -n htbase -l app=archive-worker-singlefile
   ```
2. If memory high, increase worker memory limits:
   ```yaml
   # docker-compose.yml
   archive-worker-singlefile:
     deploy:
       resources:
         limits:
           memory: 6G  # Increase from 4G
   ```
3. Restart workers:
   ```bash
   kubectl rollout restart deployment/archive-worker-singlefile -n htbase
   ```

### GCS Upload Failures

**Diagnosis:** Logs show `GCSUploadError`

**Action:**
1. Check GCS bucket permissions
2. Check service account credentials
3. Check GCS bucket quotas in GCP Console

## Prevention

- Add retry logic with exponential backoff
- Add circuit breaker for GCS
- Monitor memory usage per archiver
- Set up alerts for high memory usage

## Related

- **Dashboard:** https://grafana.company.com/d/htbase-workers
- **Flower:** https://htbase.example.com/flower
```

**Why This Fix:**

Runbooks reduce MTTR by:
1. **Clear steps**: No guessing what to check
2. **Common patterns**: Document frequent issues
3. **Remediation**: How to fix, not just diagnose
4. **Prevention**: How to avoid in future

---

## Recommendations

### Immediate Actions (HIGH Priority)

These should be implemented in the next sprint:

1. **OBS-1**: Add Prometheus metrics for API Gateway endpoints
   - Effort: 4 hours
   - Impact: High (enables latency and error rate monitoring)

2. **OBS-2**: Add Prometheus metrics for archive worker tasks
   - Effort: 3 hours
   - Impact: High (enables per-archiver performance monitoring)

3. **OBS-3**: Add queue depth metrics
   - Effort: 2 hours
   - Impact: High (enables saturation monitoring)

4. **OBS-4**: Integrate Sentry for error tracking
   - Effort: 3 hours
   - Impact: High (enables error grouping and user impact tracking)

**Total effort:** ~12 hours (1.5 days)

### Short-term (MED Priority)

Implement within 1-2 sprints:

5. **OBS-5**: Add OpenTelemetry distributed tracing
   - Effort: 6 hours
   - Impact: Medium (improves debugging, but correlation IDs already enable basic tracing)

6. **OBS-6**: Set up Prometheus alerting
   - Effort: 4 hours
   - Impact: High (enables proactive incident detection)

7. **OBS-7**: Create runbooks
   - Effort: 6 hours
   - Impact: Medium (improves MTTR, but logs already provide good context)

**Total effort:** ~16 hours (2 days)

### Long-term

Consider for future work:

- Create SLO dashboards (availability, latency, error budget)
- Add canary analysis for deployments
- Implement cost tracking metrics (GCS storage, LLM API costs)
- Add business metrics (archives/day, success rate by domain)

---

## Observability Checklist (Use for Future PRs)

Before merging code that touches critical paths:

### Logs ✅
- [x] Wide event with business context (item_id, archiver, user)
- [x] Correlation IDs (request_id, correlation_id)
- [x] Tail sampling (100% errors/slow/VIPs, 5% normal)

### Metrics ❌
- [ ] Latency histogram (p50, p95, p99)
- [ ] Error counter (by endpoint, archiver, status)
- [ ] Traffic counter (requests/sec, tasks/sec)
- [ ] Saturation gauge (queue depth, memory, CPU)

### Tracing ⚠️
- [x] Correlation IDs for distributed tracing via logs
- [ ] OpenTelemetry spans for operations
- [ ] Business context in span attributes
- [ ] Trace sampling configured

### Error Reporting ❌
- [ ] Error tracking service (Sentry) integrated
- [ ] User context attached
- [ ] Breadcrumbs for actions
- [ ] Error grouping by code

### Alerts ❌
- [ ] Alert on error rate spike (> 5% for 5min)
- [ ] Alert on latency regression (p95 > 2s)
- [ ] Alert on saturation (queue depth > 100)
- [ ] Runbook link in alert

### Runbooks ❌
- [ ] Runbook created or updated
- [ ] Debugging queries documented
- [ ] Common failure modes documented
- [ ] Remediation steps documented

---

## Summary

**Strengths:**
- ✅ **Excellent** wide-event logging with tail sampling (rare in industry)
- ✅ Correlation IDs for distributed tracing via logs
- ✅ Structured events with business context

**Critical Gaps:**
- ❌ No metrics (can't detect latency/error spikes, saturation)
- ❌ No error tracking service (errors only in logs)
- ❌ No automated alerting (reactive, not proactive)

**Next Steps:**
1. Add Prometheus metrics (12 hours effort, HIGH impact)
2. Integrate Sentry error tracking (3 hours effort, HIGH impact)
3. Set up alerting rules (4 hours effort, HIGH impact)
4. Create runbooks (6 hours effort, MED impact)

**Overall Assessment:**

The codebase has a **strong observability foundation** with excellent wide-event logging. The logging implementation is production-grade and ahead of industry standard. However, the lack of metrics, error tracking, and alerting means the team is operating **reactively** rather than proactively.

After implementing the HIGH priority findings (metrics + Sentry), the observability posture will be **production-ready** and enable:
- **Proactive** incident detection (via alerts)
- **Fast** debugging (via metrics + error tracking)
- **Data-driven** capacity planning (via metrics trends)

**Risk Level:** MEDIUM (Can operate with current logging, but blind to latency/saturation issues)

**Report Location:** `.claude/reviews/review-observability-2026-01-20.md`
