# Wide-Event Logging & Observability for HTBase

**Status:** 🚧 Infrastructure Complete, Integration In Progress

## Overview

HTBase uses **wide events** (canonical log lines) with **tail sampling** to transform logging from "grep text files" to "query structured events with business context."

### What are Wide Events?

Wide events emit **ONE comprehensive event per request/task** containing:
- Technical metadata (timestamps, IDs, duration)
- Business context (article IDs, archiver types, AI model usage)
- Error details when applicable
- Complete request context in a single queryable event

### Why Wide Events?

**Traditional logging problems:**
- 40+ scattered log statements make debugging difficult
- Missing correlation across services (can't trace article_001 from API Gateway → Archive Worker → Summarization)
- No business context (can't filter by premium users or specific archivers)
- Can't query "all slow archive tasks for premium users in the last hour"

**Wide events solution:**
- 3 canonical event types (API Request, Archive Processing, Summarization)
- Correlation IDs link events across services
- Tail sampling keeps 100% of errors/slow requests while sampling noise
- Queryable structured data instead of string grep

---

## Architecture

### Event Types

HTBase emits 3 canonical wide events:

#### 1. **APIRequestEvent** (API Gateway)
Emitted for every HTTP request to the API Gateway.

```json
{
  "timestamp": "2026-01-18T10:23:45.123Z",
  "request_id": "req_abc123def456",
  "correlation_id": "corr_xyz789",

  "service": "api-gateway",
  "version": "1.0.0",
  "deployment_id": "deploy_prod_001",

  "method": "POST",
  "path": "/api/archives",
  "status_code": 201,
  "duration_ms": 245,
  "outcome": "success",

  "auth": {
    "api_key_id": "key_abc",
    "user_id": "user_123",
    "tier": "premium",
    "authenticated": true
  },

  "article": {
    "id": "article_001",
    "url": "https://example.com/article",
    "exists": false
  },

  "archive_request": {
    "archivers_requested": ["singlefile", "screenshot", "pdf"],
    "celery_task_ids": {
      "singlefile": "task_abc",
      "screenshot": "task_def"
    }
  }
}
```

#### 2. **ArchiveProcessingEvent** (Archive Worker)
Emitted for every archive task execution.

```json
{
  "timestamp": "2026-01-18T10:23:50.456Z",
  "request_id": "req_abc123def456",
  "correlation_id": "corr_xyz789",
  "task_id": "task_abc",

  "service": "archive-worker",
  "archiver": "singlefile",
  "version": "1.0.0",

  "article": {
    "id": "article_001",
    "url": "https://example.com/article"
  },

  "processing": {
    "duration_ms": 4500,
    "outcome": "success",
    "retry_attempt": 0,
    "max_retries": 3,

    "command": {
      "exit_code": 0,
      "duration_ms": 4200,
      "timeout_ms": 60000
    },

    "storage": {
      "gcs_path": "gs://bucket/archives/article_001/singlefile.html",
      "file_size_bytes": 125000,
      "upload_duration_ms": 300
    }
  },

  "webhook": {
    "sent": true,
    "workflow_id": "workflow_123",
    "event": "archive.completed",
    "status_code": 200,
    "duration_ms": 150
  }
}
```

#### 3. **SummarizationEvent** (Summarization Worker)
Emitted for every summarization task.

```json
{
  "timestamp": "2026-01-18T10:24:10.789Z",
  "request_id": "req_abc123def456",
  "task_id": "task_xyz",

  "service": "summarization-worker",
  "version": "1.0.0",

  "article": {
    "id": "article_001"
  },

  "content": {
    "source": "readability",
    "content_length_chars": 15000,
    "word_count": 2500
  },

  "summarization": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "duration_ms": 2300,
    "outcome": "success",
    "retry_attempt": 0,

    "tokens_used": 450,
    "summary_length_chars": 500,
    "entities_extracted": 12,
    "tags_generated": 5
  },

  "cost": {
    "provider_cost_usd": 0.0023,
    "tokens_charged": 450
  }
}
```

---

## Tail Sampling Strategy

**Sampling happens AFTER processing completes**, keeping 100% of signal while sampling noise:

### Always Keep (100%)
- ✅ Errors (status_code >= 500 or outcome == "error")
- ✅ Slow requests (duration_ms > 2000ms)
- ✅ VIP users (tier == "premium" or "enterprise")

### Sample (5%)
- 📊 Successful fast requests from regular users

### Configuration

```python
from shared.observability import configure_sampling

# Customize sampling thresholds
configure_sampling(
    slow_threshold_ms=3000,  # Consider slow if > 3 seconds
    sample_rate=0.10,        # Keep 10% of normal traffic
    vip_tiers={"enterprise"}  # Only keep enterprise, not premium
)
```

---

## Usage Examples

### API Gateway Integration

```python
# services/api-gateway/app/main.py
from fastapi import FastAPI
from shared.observability import CorrelationMiddleware, WideEventMiddleware

app = FastAPI()

# Install middleware (ORDER MATTERS!)
app.add_middleware(
    WideEventMiddleware,
    service_name="api-gateway",
    version="1.0.0",
    deployment_id="prod",
)
app.add_middleware(CorrelationMiddleware)

# In route handlers, enrich the wide event
from shared.observability import enrich_api_event, ArticleContext, AuthContext

@app.post("/api/archives")
async def create_archive(request: Request, article: ArchiveRequest):
    # Enrich wide event with business context
    enrich_api_event(
        request,
        auth=AuthContext(
            api_key_id=hash_api_key(request.headers.get("x-api-key")),
            user_id=current_user.id,
            tier=current_user.tier,
            authenticated=True,
        ),
        article=ArticleContext(
            id=article_id,
            url=sanitize_url_for_logging(article.url),
            exists=article_exists,
        ),
    )

    # ... rest of handler logic
```

### Archive Worker Integration

```python
# services/archive-worker/app/tasks.py
from shared.observability import ArchiveTaskContext
from shared.logging_utils import sanitize_url_for_logging

@celery_app.task(bind=True)
def archive_article(self, item_id: str, url: str, archiver_name: str, **kwargs):
    # Create wide-event context
    with ArchiveTaskContext(
        task_id=self.request.id,
        archiver=archiver_name,
        item_id=item_id,
        url=sanitize_url_for_logging(url),
        service_name="archive-worker",
        version="1.0.0",
    ) as ctx:
        try:
            # Execute archiving
            result = run_archiver(archiver_name, url)

            # Mark success with metrics
            ctx.mark_success(
                exit_code=result.exit_code,
                gcs_path=result.gcs_path,
                file_size_bytes=result.file_size,
                upload_duration_ms=result.upload_time,
                command_duration_ms=result.execution_time,
            )

            return result

        except CommandTimeoutError as e:
            ctx.mark_error(
                error=e,
                error_code="cmd_timeout",
                retriable=True,
            )
            raise
```

### Summarization Worker Integration

```python
# services/summarization-worker/app/tasks.py
from shared.observability import SummarizationTaskContext

@celery_app.task(bind=True)
def summarize_article(self, item_id: str, **kwargs):
    with SummarizationTaskContext(
        task_id=self.request.id,
        item_id=item_id,
        service_name="summarization-worker",
        version="1.0.0",
    ) as ctx:
        try:
            # Get content
            content = get_article_content(item_id, source="readability")
            ctx.set_content_context(
                source="readability",
                content_length_chars=len(content),
                word_count=len(content.split()),
            )

            # Generate summary
            result = call_openai_api(content, model="gpt-4o-mini")

            # Mark success with metrics
            ctx.mark_success(
                provider="openai",
                model="gpt-4o-mini",
                tokens_used=result.tokens_used,
                summary_length_chars=len(result.summary),
                entities_extracted=len(result.entities),
                tags_generated=len(result.tags),
            )

            return result

        except openai.RateLimitError as e:
            ctx.mark_error(
                error=e,
                error_code="quota_exceeded",
                retriable=True,
                provider_error_code="rate_limit_exceeded",
            )
            raise
```

---

## Query Examples

### Example 1: Trace a Request Across Services

**Question:** What happened to article_001 from submission to completion?

```sql
-- CloudWatch Insights / DataDog / Elasticsearch
SELECT *
FROM logs
WHERE article.id = 'article_001'
  OR request_id IN (
    SELECT DISTINCT request_id
    FROM logs
    WHERE article.id = 'article_001'
  )
ORDER BY timestamp ASC
```

**Result:** Complete journey showing:
1. API Gateway received POST /api/archives
2. Archive Worker processed singlefile, screenshot, pdf tasks
3. Summarization Worker generated summary
4. All with timing, errors, and business context

---

### Example 2: Archive Failures by Archiver Type

**Question:** Which archivers are failing most often in the last 24 hours?

```sql
SELECT
  archiver,
  COUNT(*) as failure_count,
  AVG(processing.duration_ms) as avg_duration_ms,
  ARRAY_AGG(DISTINCT error.code) as error_codes
FROM logs
WHERE
  service = 'archive-worker'
  AND outcome = 'error'
  AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY archiver
ORDER BY failure_count DESC
```

**Insight:** Identify problematic archivers (e.g., "screenshot has 45 timeout errors").

---

### Example 3: Slow Archive Tasks

**Question:** What archive tasks are taking longer than 5 seconds?

```sql
SELECT
  article.id,
  archiver,
  processing.duration_ms,
  processing.command.exit_code,
  processing.storage.file_size_bytes,
  timestamp
FROM logs
WHERE
  service = 'archive-worker'
  AND processing.duration_ms > 5000
  AND timestamp > NOW() - INTERVAL '1 hour'
ORDER BY processing.duration_ms DESC
LIMIT 100
```

**Insight:** Find slow tasks and correlate with file size or archiver type.

---

### Example 4: Summarization Cost Analysis

**Question:** How much are we spending on OpenAI for summarization?

```sql
SELECT
  DATE_TRUNC('day', timestamp) as date,
  summarization.model,
  SUM(cost.provider_cost_usd) as total_cost_usd,
  SUM(summarization.tokens_used) as total_tokens,
  COUNT(*) as request_count
FROM logs
WHERE
  service = 'summarization-worker'
  AND outcome = 'success'
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY date, summarization.model
ORDER BY date DESC
```

**Insight:** Track AI costs over time and identify cost optimizations.

---

### Example 5: Premium User Experience

**Question:** Are premium users experiencing errors?

```sql
SELECT
  auth.tier,
  outcome,
  COUNT(*) as request_count,
  AVG(duration_ms) as avg_duration_ms,
  PERCENTILE(duration_ms, 95) as p95_duration_ms
FROM logs
WHERE
  service = 'api-gateway'
  AND auth.tier IN ('premium', 'enterprise')
  AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY auth.tier, outcome
```

**Insight:** Compare premium vs enterprise user experience.

---

### Example 6: Feature Rollout Monitoring

**Question:** (Future) How is the new singlefile v2 archiver performing vs v1?

```sql
SELECT
  feature_flags.singlefile_v2 as using_new_version,
  AVG(processing.duration_ms) as avg_duration,
  SUM(CASE WHEN outcome = 'error' THEN 1 ELSE 0 END) / COUNT(*) as error_rate
FROM logs
WHERE
  service = 'archive-worker'
  AND archiver = 'singlefile'
  AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY using_new_version
```

**Insight:** A/B test new features by comparing cohorts.

---

## Migration Strategy

### Phase 1: Infrastructure (✅ Complete)
- [x] Create `shared/observability/` package
- [x] Implement correlation ID utilities
- [x] Implement wide-event data classes
- [x] Implement tail sampling logic
- [x] Create FastAPI middleware
- [x] Create Celery integration

### Phase 2: API Gateway Integration (🚧 In Progress)
- [ ] Install middleware in `services/api-gateway/app/main.py`
- [ ] Enrich events in archive routes
- [ ] Enrich events in artifact routes
- [ ] Enrich events in system routes
- [ ] Verify wide events in logs

### Phase 3: Worker Integration (📋 Planned)
- [ ] Integrate ArchiveTaskContext in archive worker
- [ ] Integrate SummarizationTaskContext in summarization worker
- [ ] Add Celery signal handlers
- [ ] Pass correlation IDs from API Gateway to workers

### Phase 4: Validation & Cleanup (📋 Planned)
- [ ] Verify correlation across services works
- [ ] Test tail sampling (confirm 100% of errors kept)
- [ ] Document example queries for runbooks
- [ ] Gradually remove scattered log statements

---

## Configuration

### Environment Variables

```bash
# Sampling configuration
OBSERVABILITY_SLOW_THRESHOLD_MS=2000
OBSERVABILITY_SAMPLE_RATE=0.05
OBSERVABILITY_VIP_TIERS=premium,enterprise

# Service metadata
SERVICE_VERSION=1.0.0
DEPLOYMENT_ID=prod_us_east_1
```

### Logging Format

Wide events require JSON logging to be enabled:

```python
# In shared/config.py
log_format: str = Field(default="json")  # Must be "json", not "text"
```

---

## Security Considerations

### URL Sanitization

**Always sanitize URLs before logging:**

```python
from shared.logging_utils import sanitize_url_for_logging

# ❌ NEVER log raw URLs
article=ArticleContext(
    id=article_id,
    url=article.url,  # MAY CONTAIN API KEYS IN QUERY PARAMS!
)

# ✅ ALWAYS sanitize URLs
article=ArticleContext(
    id=article_id,
    url=sanitize_url_for_logging(article.url),  # Redacts sensitive params
)
```

### PII Redaction

The wide-event infrastructure does NOT log:
- Raw API keys (only hashed `api_key_id`)
- Passwords
- Credit card numbers
- Email addresses (use `user_id` instead)

### Sensitive Fields

If adding custom fields to events, ensure they don't contain:
- Full request bodies
- Authorization headers
- Database credentials
- Secrets from environment variables

---

## Performance Impact

### Before Wide Events
- **Log volume:** ~40-45 log statements per article workflow
- **Context:** Scattered across files, difficult to correlate
- **Sampling:** None (log everything)

### After Wide Events
- **Log volume:** 3 canonical events per article workflow
- **Context:** Complete business context in queryable structure
- **Sampling:** ~90-95% reduction via tail sampling (keeps 100% of signal)

### Cost Savings

With tail sampling:
- Errors/slow requests: 100% kept (assume 5% of traffic)
- VIP users: 100% kept (assume 10% of traffic)
- Normal traffic: 5% sampled (85% of traffic → 4.25% kept)

**Total reduction:** ~85% fewer logs while keeping all debugging signal.

---

## Troubleshooting

### Issue: "No wide event found on request"

**Cause:** Middleware not installed or installed in wrong order.

**Solution:**
```python
# Correct order (from outermost to innermost):
app.add_middleware(WideEventMiddleware, ...)  # Install first
app.add_middleware(CorrelationMiddleware)      # Install second
```

### Issue: "Can't correlate events across services"

**Cause:** Correlation IDs not being passed to Celery tasks.

**Solution:** Add correlation IDs to task kwargs:
```python
from shared.observability import get_request_id, get_correlation_id

archive_task.delay(
    item_id=item_id,
    url=url,
    request_id=get_request_id(),        # Pass correlation
    correlation_id=get_correlation_id(),  # Pass correlation
)
```

### Issue: "Not seeing any wide events in logs"

**Cause:** Log format is "text" instead of "json", or events are being sampled.

**Solution:**
1. Check `shared/config.py`: `log_format` must be `"json"`
2. Check if events have errors (should always be logged)
3. Disable sampling temporarily: `configure_sampling(sample_rate=1.0)`

---

## Future Enhancements

- [ ] Add OpenTelemetry integration (spans with wide-event attributes)
- [ ] Add feature flag context (for A/B testing)
- [ ] Add client-side wide events (React/frontend)
- [ ] Add custom CloudWatch/Datadog dashboards
- [ ] Add alerting based on wide-event metrics
- [ ] Add distributed tracing with trace_id/span_id

---

## References

- [Logging Sucks - Canonical Log Lines](https://loggingsucks.com/)
- [Tail-Based Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [Structured Logging Best Practices](https://www.structlog.org/)
- HTBase Architecture: `docs/architecture.md`
- Codebase Logging Analysis: `.claude/skills/wide-event-observability/SKILL.md`
