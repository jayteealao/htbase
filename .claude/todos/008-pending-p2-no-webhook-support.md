---
status: pending
priority: p2
issue_id: "008"
tags: [code-review, feature, webhooks, agent-native, async]
dependencies: []
---

# No Webhook Support for Async Notifications

System requires agents to poll for task status instead of receiving push notifications, causing inefficiency.

## Problem Statement

The current architecture requires AI agents to continuously poll the `/tasks/{task_id}` endpoint to check task completion status. This is inefficient for long-running archive operations (up to 10 minutes) and wastes resources on both client and server sides.

**Impact:**
- Agents waste CPU/network polling for status
- Increased API load from status check requests
- Poor user experience for long-running tasks
- Cannot integrate with event-driven systems
- Higher cloud costs from unnecessary requests

## Findings

- **From Agent-Native Review:** Rated 0/10 - "Missing"
- **Architecture doc mentions webhooks** as "optional future enhancement" (REARCHITECTURE_PLAN.md:919)
- **No webhook_url field** in SaveRequest model
- **No callback mechanism** in Celery task chains
- **Polling-only architecture** forces inefficient patterns

**Current polling pattern:**
```python
# Agent must do this (inefficient)
task_id = submit_archive(url)
while True:
    status = check_status(task_id)
    if status in ['completed', 'failed']:
        break
    time.sleep(5)  # Waste resources waiting
```

## Proposed Solutions

### Option 1: HTTP Webhook Callbacks (Recommended)

**Approach:** Add webhook_url field to requests, POST results when task completes.

**Pros:**
- Industry standard pattern
- Efficient (no polling)
- Easy to implement with Celery
- Signature verification for security

**Cons:**
- Requires agents to host webhook endpoint
- Network failures need retry logic
- Agents behind firewalls can't use

**Effort:** 6-8 hours

**Risk:** Low

**Implementation:**
```python
# Update SaveRequest model
class SaveRequest(BaseModel):
    url: HttpUrl
    id: str
    archivers: Optional[List[str]] = None
    webhook_url: Optional[HttpUrl] = None
    webhook_secret: Optional[str] = Field(
        default=None,
        description="HMAC secret for signature verification"
    )

# Celery webhook task
@celery_app.task(bind=True, max_retries=5)
def notify_webhook(
    self,
    task_id: str,
    webhook_url: str,
    webhook_secret: str,
    status_data: dict
):
    """Send webhook notification when task completes."""
    import hmac
    import hashlib
    import httpx

    payload = {
        "event": "task.completed",
        "task_id": task_id,
        "status": status_data['status'],
        "items": status_data['items'],
        "timestamp": datetime.utcnow().isoformat()
    }

    # Sign payload with HMAC-SHA256
    signature = hmac.new(
        webhook_secret.encode(),
        json.dumps(payload, sort_keys=True).encode(),
        hashlib.sha256
    ).hexdigest()

    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={
                "X-HTBase-Signature": f"sha256={signature}",
                "X-HTBase-Event": "task.completed",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Webhook delivery failed: {e}")
        raise  # Retry via Celery

# Update save endpoint
@router.post("/save")
async def save_url(request: SaveRequest, ...):
    # ... existing code ...

    # Add webhook callback to workflow
    if request.webhook_url:
        workflow = chain(
            task_group,
            gather_status.s(task_id=workflow_id),
            notify_webhook.s(
                task_id=workflow_id,
                webhook_url=str(request.webhook_url),
                webhook_secret=request.webhook_secret or ""
            )
        )
    else:
        workflow = task_group

    workflow.apply_async()
```

---

### Option 2: WebSocket Push Notifications

**Approach:** Open WebSocket connection, push status updates in real-time.

**Pros:**
- Real-time updates
- Bidirectional communication
- Multiple events per task

**Cons:**
- More complex server infrastructure
- Requires WebSocket support in agents
- Stateful connections (scaling issues)

**Effort:** 15-20 hours

**Risk:** Medium

---

### Option 3: Server-Sent Events (SSE)

**Approach:** HTTP streaming connection for server-to-client events.

**Pros:**
- Simpler than WebSockets
- Works over HTTP
- Built-in reconnection

**Cons:**
- One-way only (server → client)
- Browser compatibility issues
- Connection management overhead

**Effort:** 10-12 hours

**Risk:** Low

## Recommended Action

**Implement Option 1 (HTTP Webhooks) for production, consider Option 3 (SSE) for web UI.**

1. Add webhook_url and webhook_secret to SaveRequest
2. Implement notify_webhook Celery task with retry logic
3. Add HMAC signature verification
4. Update API documentation with webhook format
5. Add webhook delivery dashboard
6. Support multiple webhook events (progress, completed, failed)

**Timeline:** P2 - Important for agent UX but not blocking

## Technical Details

**Affected files:**
- `shared/models/__init__.py` - Add webhook fields to SaveRequest
- `services/api-gateway/app/routes/saves.py` - Update workflow with callback
- `services/archive-worker/app/tasks.py` - Add webhook task (new)
- `shared/celery_config.py` - Configure webhook task routing

**Webhook events:**
```python
class WebhookEvent(str, Enum):
    TASK_CREATED = "task.created"
    TASK_PROGRESS = "task.progress"  # Optional
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    ARCHIVE_SUCCESS = "archive.success"  # Per-archiver
    ARCHIVE_FAILED = "archive.failed"
```

**Webhook payload format:**
```json
{
  "event": "task.completed",
  "task_id": "abc123def456",
  "status": "completed",
  "items": [
    {
      "url": "https://example.com",
      "id": "article-123",
      "archiver": "readability",
      "status": "success",
      "saved_path": "/data/article-123/readability/output.json"
    }
  ],
  "timestamp": "2026-01-09T12:34:56Z"
}
```

**Signature verification (client-side):**
```python
import hmac
import hashlib
import json

def verify_webhook(payload: dict, signature: str, secret: str) -> bool:
    """Verify webhook signature."""
    expected = hmac.new(
        secret.encode(),
        json.dumps(payload, sort_keys=True).encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)

# In webhook handler
@app.post("/webhook")
async def handle_webhook(request: Request):
    signature = request.headers.get("X-HTBase-Signature")
    payload = await request.json()

    if not verify_webhook(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid signature")

    # Process webhook
    print(f"Task {payload['task_id']} completed!")
```

**Retry logic:**
```python
@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,  # 1 minute
    retry_backoff=True,
    retry_jitter=True
)
def notify_webhook(self, ...):
    try:
        # Send webhook
        pass
    except httpx.HTTPError as e:
        # Retry on network errors, not 4xx client errors
        if e.response and 400 <= e.response.status_code < 500:
            logger.error(f"Webhook rejected (4xx): {e}")
            return  # Don't retry client errors
        raise self.retry(exc=e)
```

## Resources

- **PR:** #6
- **Agent-Native Review:** `AGENT_NATIVE_REVIEW.md` (lines 427-525)
- **Webhook best practices:** https://webhooks.fyi/
- **HMAC verification:** https://webhook.site/#!/

## Acceptance Criteria

- [ ] webhook_url field added to SaveRequest
- [ ] webhook_secret field for signature verification
- [ ] notify_webhook Celery task implemented
- [ ] HMAC-SHA256 signature in X-HTBase-Signature header
- [ ] Retry logic for failed deliveries (5 retries)
- [ ] Multiple event types supported (created, completed, failed)
- [ ] Webhook delivery logs stored in database
- [ ] Documentation with payload format and verification code
- [ ] Tests for webhook delivery and signature verification

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Agent-Native Reviewer)

**Actions:**
- Identified polling-only architecture
- Reviewed REARCHITECTURE_PLAN.md mention of webhooks
- Evaluated webhook vs WebSocket vs SSE patterns
- Drafted HTTP webhook implementation with signatures
- Documented payload format and events

**Learnings:**
- Polling is inefficient for 10-minute archive tasks
- Webhooks are industry standard for async APIs
- HMAC signatures required for security
- Celery supports callback chains well
- Important for agent UX but not blocking merge

## Notes

- P2 priority - Important but not blocking
- Industry-standard pattern for async APIs
- Improves agent efficiency significantly
- Signature verification prevents spoofing
- Retry logic handles transient failures
- Consider webhook delivery dashboard for debugging
- Document webhook timeout behavior (10 seconds)
