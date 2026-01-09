# HTBase Webhooks Guide

> **Current Status:** Webhooks are **not yet implemented**. This document describes the planned implementation based on [Issue #008](../.claude/todos/008-pending-p2-webhook-system-not-implemented.md).

---

## Overview

Webhooks provide real-time notifications when archiving operations complete, eliminating the need for polling. When implemented, HTBase will POST event data to your specified webhook URL.

**Timeline:** P2 priority - important for production agents but not blocking deployment.

**Benefits:**
- No polling overhead
- Real-time notifications (sub-second latency)
- Reduced API calls (more efficient)
- Better resource utilization

---

## Why Webhooks?

### Without Webhooks (Current - Polling)

```python
# Inefficient: Poll every 5 seconds
task_id = archive_url(url, item_id)

while True:
    status = get_task_status(task_id)
    if status["status"] in ["success", "failed"]:
        break
    time.sleep(5)  # Wait 5 seconds

# Could take 30-60 polls for slow archivers
```

**Problems:**
- Wastes API quota
- Adds latency (up to polling interval)
- Keeps connection open
- Scales poorly (100 tasks = 100 polling loops)

---

### With Webhooks (Planned)

```python
# Efficient: Get notified when done
task_id = archive_url(url, item_id, webhook_url="https://your-agent.com/webhook")

# Your webhook receives POST immediately when done:
# POST https://your-agent.com/webhook
# {"task_id": "...", "status": "success", "saved_path": "...", ...}
```

**Benefits:**
- Zero polling
- Instant notification
- Scales to thousands of concurrent tasks
- Lower costs

---

## Planned API

### Register Webhook with Archive Request

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "article-123",
    "url": "https://example.com",
    "webhook_url": "https://your-agent.com/webhook",
    "webhook_secret": "your-secret-key"  # Optional for verification
  }'
```

**Response:**
```json
{
  "ok": true,
  "task_id": "abc123",
  "webhook_registered": true
}
```

---

### Webhook Payload

When the archive completes, HTBase will POST to your webhook URL:

**Successful Archive:**
```json
{
  "event": "archive.completed",
  "task_id": "abc123",
  "item_id": "article-123",
  "url": "https://example.com",
  "archiver": "readability",
  "status": "success",
  "exit_code": 0,
  "saved_path": "/data/article-123/readability/output.html",
  "db_rowid": 42,
  "size_bytes": 45678,
  "duration_seconds": 8.5,
  "completed_at": "2026-01-09T12:00:00Z",
  "metadata": {
    "title": "Example Article",
    "author": "John Doe",
    "excerpt": "This is an example..."
  }
}
```

**Failed Archive:**
```json
{
  "event": "archive.failed",
  "task_id": "abc123",
  "item_id": "article-123",
  "url": "https://example.com",
  "archiver": "readability",
  "status": "failed",
  "exit_code": 404,
  "error_message": "URL returned 404 Not Found",
  "completed_at": "2026-01-09T12:00:00Z"
}
```

---

## Webhook Implementation

### Setting Up Your Webhook Endpoint

#### Python (Flask)

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)
WEBHOOK_SECRET = "your-secret-key"

def verify_signature(payload, signature, secret):
    """Verify webhook signature using HMAC-SHA256."""
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

@app.route('/webhook', methods=['POST'])
def webhook():
    # Verify signature
    signature = request.headers.get('X-HTBase-Signature')
    if signature:
        if not verify_signature(request.data.decode(), signature, WEBHOOK_SECRET):
            return jsonify({"error": "Invalid signature"}), 401

    # Process webhook
    data = request.json
    event = data.get("event")

    if event == "archive.completed":
        handle_archive_completed(data)
    elif event == "archive.failed":
        handle_archive_failed(data)

    return jsonify({"status": "received"}), 200

def handle_archive_completed(data):
    print(f"Archive completed: {data['item_id']}")
    print(f"Saved to: {data['saved_path']}")
    # Your logic here

def handle_archive_failed(data):
    print(f"Archive failed: {data['item_id']}")
    print(f"Error: {data['error_message']}")
    # Your logic here

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

#### JavaScript (Express)

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = 'your-secret-key';

app.use(express.json());

function verifySignature(payload, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload))
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}

app.post('/webhook', (req, res) => {
  // Verify signature
  const signature = req.headers['x-htbase-signature'];
  if (signature) {
    if (!verifySignature(req.body, signature, WEBHOOK_SECRET)) {
      return res.status(401).json({ error: 'Invalid signature' });
    }
  }

  // Process webhook
  const { event, item_id, status } = req.body;

  if (event === 'archive.completed') {
    console.log(`Archive completed: ${item_id}`);
    // Your logic here
  } else if (event === 'archive.failed') {
    console.log(`Archive failed: ${item_id}`);
    // Your logic here
  }

  res.json({ status: 'received' });
});

app.listen(5000, () => {
  console.log('Webhook server listening on port 5000');
});
```

---

#### Python (FastAPI)

```python
from fastapi import FastAPI, Request, HTTPException
import hmac
import hashlib

app = FastAPI()
WEBHOOK_SECRET = "your-secret-key"

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature using HMAC-SHA256."""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

@app.post("/webhook")
async def webhook(request: Request):
    # Verify signature
    signature = request.headers.get("X-HTBase-Signature")
    if signature:
        body = await request.body()
        if not verify_signature(body, signature, WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Process webhook
    data = await request.json()
    event = data.get("event")

    if event == "archive.completed":
        await handle_archive_completed(data)
    elif event == "archive.failed":
        await handle_archive_failed(data)

    return {"status": "received"}

async def handle_archive_completed(data: dict):
    print(f"Archive completed: {data['item_id']}")
    # Your async logic here

async def handle_archive_failed(data: dict):
    print(f"Archive failed: {data['item_id']}")
    # Your async logic here
```

---

## Security

### Signature Verification

HTBase will sign webhook payloads using HMAC-SHA256:

**Headers:**
```
X-HTBase-Signature: 3a7f8b2c9d1e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a
X-HTBase-Timestamp: 1704811200
```

**Signature Algorithm:**
```python
signature = hmac.new(
    webhook_secret.encode(),
    f"{timestamp}.{json_payload}".encode(),
    hashlib.sha256
).hexdigest()
```

**Verification:**
1. Extract signature from `X-HTBase-Signature` header
2. Extract timestamp from `X-HTBase-Timestamp` header
3. Reconstruct payload: `"{timestamp}.{json_body}"`
4. Compute HMAC-SHA256 with your secret
5. Compare signatures using constant-time comparison

---

### Timestamp Validation

Prevent replay attacks by validating timestamps:

```python
import time

def is_recent_timestamp(timestamp: int, max_age: int = 300) -> bool:
    """Check if timestamp is within max_age seconds (default 5 minutes)."""
    now = int(time.time())
    return abs(now - timestamp) <= max_age

# Usage
timestamp = int(request.headers.get("X-HTBase-Timestamp"))
if not is_recent_timestamp(timestamp):
    raise HTTPException(status_code=401, detail="Webhook too old")
```

---

### IP Allowlisting (Optional)

Restrict webhook delivery to known HTBase server IPs:

```python
ALLOWED_IPS = ["203.0.113.10", "203.0.113.11"]

@app.before_request
def check_ip():
    if request.remote_addr not in ALLOWED_IPS:
        abort(403)
```

---

## Retry Logic

### HTBase Retry Behavior (Planned)

If webhook delivery fails, HTBase will retry with exponential backoff:

| Attempt | Delay | Total Time |
|---------|-------|------------|
| 1 | Immediate | 0s |
| 2 | 5s | 5s |
| 3 | 15s | 20s |
| 4 | 45s | 1m 5s |
| 5 | 2m | 3m 5s |

After 5 failed attempts, the webhook is marked as failed and logged.

---

### Webhook Response Requirements

Your endpoint must:
1. Respond within 10 seconds
2. Return HTTP 2xx status code
3. Handle idempotency (same webhook may be delivered multiple times)

**Good Response:**
```python
return jsonify({"status": "received"}), 200  # ✅ Fast, 2xx
```

**Bad Response:**
```python
time.sleep(15)  # ❌ Too slow (>10s timeout)
return jsonify({}), 500  # ❌ Non-2xx status code
```

---

## Idempotency

Webhooks may be delivered more than once. Design your handler to be idempotent:

```python
# Bad: Not idempotent
def handle_archive_completed(data):
    db.insert_archive(data)  # ❌ Duplicate inserts possible

# Good: Idempotent using unique key
def handle_archive_completed(data):
    db.upsert_archive(
        key=data["task_id"],
        data=data
    )  # ✅ Duplicate delivery is safe
```

**Strategies:**
1. Use `task_id` or `db_rowid` as unique key
2. Check if record exists before creating
3. Use database UPSERT operations

---

## Testing Webhooks

### Local Testing with ngrok

Expose your local webhook endpoint:

```bash
# Start your webhook server
python webhook_server.py  # Listening on localhost:5000

# In another terminal, expose with ngrok
ngrok http 5000
```

**ngrok output:**
```
Forwarding: https://abc123.ngrok.io -> http://localhost:5000
```

Use the ngrok URL in your HTBase requests:

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "test",
    "url": "https://example.com",
    "webhook_url": "https://abc123.ngrok.io/webhook"
  }'
```

---

### Testing with Mock Server

Use a webhook testing service:

**Option 1: webhook.site**
```bash
# Get a test webhook URL
curl https://webhook.site/token

# Use the provided URL in requests
webhook_url="https://webhook.site/unique-id"
```

**Option 2: RequestBin**
```bash
# Create a bin at requestbin.com
# Use the provided URL
webhook_url="https://requestbin.com/r/abc123"
```

---

### Unit Tests

```python
import unittest
from unittest.mock import patch, Mock

class TestWebhookHandler(unittest.TestCase):
    def test_successful_archive_webhook(self):
        payload = {
            "event": "archive.completed",
            "task_id": "test123",
            "status": "success",
            "saved_path": "/data/test/readability/output.html"
        }

        with patch('requests.post') as mock_post:
            send_webhook("https://example.com/webhook", payload, "secret")
            mock_post.assert_called_once()
            args = mock_post.call_args
            self.assertEqual(args[0][0], "https://example.com/webhook")
            self.assertEqual(args[1]["json"], payload)
```

---

## Advanced Use Cases

### Webhook to Multiple Endpoints

Register multiple webhooks for redundancy:

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "article-123",
    "url": "https://example.com",
    "webhook_urls": [
      "https://primary.example.com/webhook",
      "https://backup.example.com/webhook"
    ]
  }'
```

---

### Conditional Webhooks

Only receive webhooks for specific events:

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "article-123",
    "url": "https://example.com",
    "webhook_url": "https://your-agent.com/webhook",
    "webhook_events": ["archive.failed"]  # Only notify on failures
  }'
```

---

### Webhook Transformations

Transform webhook payloads for third-party integrations:

**Example: Slack Notification**
```python
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if data["event"] == "archive.completed":
        # Send to Slack
        slack_message = {
            "text": f"✅ Archive completed: {data['item_id']}",
            "attachments": [{
                "fields": [
                    {"title": "URL", "value": data["url"]},
                    {"title": "Size", "value": f"{data['size_bytes']} bytes"},
                    {"title": "Duration", "value": f"{data['duration_seconds']}s"}
                ]
            }]
        }
        requests.post(SLACK_WEBHOOK_URL, json=slack_message)

    return {"status": "received"}
```

---

## Monitoring and Debugging

### Webhook Logs

HTBase will log webhook delivery attempts:

```
2026-01-09 12:00:05 INFO Webhook delivered: task=abc123 url=https://example.com/webhook status=200 duration=0.15s
2026-01-09 12:00:10 WARN Webhook failed: task=abc123 url=https://example.com/webhook error=timeout attempt=1/5
2026-01-09 12:00:15 INFO Webhook delivered: task=abc123 url=https://example.com/webhook status=200 duration=0.12s (retry)
```

---

### Webhook Status Endpoint (Planned)

Check webhook delivery status:

```bash
curl http://localhost:8000/api/webhooks/abc123
```

**Response:**
```json
{
  "task_id": "abc123",
  "webhook_url": "https://example.com/webhook",
  "status": "delivered",
  "attempts": 2,
  "last_attempt_at": "2026-01-09T12:00:15Z",
  "last_status_code": 200,
  "last_error": null
}
```

---

### Webhook Replay (Planned)

Manually replay a webhook:

```bash
curl -X POST http://localhost:8000/api/webhooks/abc123/replay
```

**Use cases:**
- Webhook endpoint was down
- Testing new webhook handler
- Recovering from processing errors

---

## Best Practices

### 1. Acknowledge Immediately, Process Asynchronously

```python
# Good: Fast response
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    # Queue for async processing
    await task_queue.enqueue(process_webhook, data)

    return {"status": "received"}  # Fast response

async def process_webhook(data):
    # Slow operations here (database, external APIs, etc.)
    pass
```

---

### 2. Log All Webhook Deliveries

```python
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    # Log for debugging
    logger.info(
        "Webhook received",
        extra={
            "event": data.get("event"),
            "task_id": data.get("task_id"),
            "status": data.get("status")
        }
    )

    # Process...
    return {"status": "received"}
```

---

### 3. Implement Health Checks

```python
@app.get("/webhook/health")
async def webhook_health():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "webhook_handler"}
```

HTBase can periodically check this endpoint to verify your webhook service is operational.

---

### 4. Use Dedicated Webhook Endpoints

```python
# Bad: Generic endpoint
@app.post("/api/callback")  # ❌ Not clear this is for HTBase webhooks

# Good: Specific endpoint
@app.post("/webhooks/htbase")  # ✅ Clear purpose
```

---

### 5. Monitor Webhook Latency

```python
import time

@app.post("/webhook")
async def webhook(request: Request):
    start = time.time()
    data = await request.json()

    # Process...

    duration = time.time() - start
    metrics.record("webhook_processing_time", duration)

    return {"status": "received"}
```

---

## Migration from Polling

### Step 1: Add Webhook Handler

Deploy your webhook endpoint:

```python
# webhook_server.py
@app.post("/webhooks/htbase")
async def htbase_webhook(request: Request):
    data = await request.json()
    # Handle webhook
    return {"status": "received"}
```

---

### Step 2: Update Clients

```python
# Before: Polling
def archive_url_polling(url, item_id):
    task_id = submit_archive(url, item_id)
    while True:
        status = get_status(task_id)
        if status["status"] in ["success", "failed"]:
            return status
        time.sleep(5)

# After: Webhooks
def archive_url_webhook(url, item_id):
    return submit_archive(
        url,
        item_id,
        webhook_url="https://your-agent.com/webhooks/htbase"
    )
    # Webhook handler receives completion notification
```

---

### Step 3: Gradual Rollout

Use feature flags to switch between polling and webhooks:

```python
if USE_WEBHOOKS:
    archive_url_webhook(url, item_id)
else:
    archive_url_polling(url, item_id)
```

---

## Implementation Timeline

Based on [Issue #008](../.claude/todos/008-pending-p2-webhook-system-not-implemented.md):

**Priority:** P2 (important but not blocking)

**Estimated Effort:** 2-3 days

**Planned Features:**
- [ ] Webhook registration in API
- [ ] HMAC signature generation
- [ ] Retry logic with exponential backoff
- [ ] Webhook delivery logging
- [ ] Status endpoint
- [ ] Replay functionality
- [ ] Multiple webhook URLs support
- [ ] Conditional webhooks (event filtering)

---

## FAQ

### Q: When will webhooks be available?
**A:** Webhooks are a P2 priority. Track progress in [Issue #008](../.claude/todos/008-pending-p2-webhook-system-not-implemented.md).

### Q: Can I use webhooks now?
**A:** No, webhooks are not yet implemented. Use polling with the `/api/tasks/{task_id}` endpoint.

### Q: What if my webhook endpoint is temporarily down?
**A:** HTBase will retry up to 5 times with exponential backoff. If all retries fail, check logs and use the replay endpoint.

### Q: Can I test webhooks locally?
**A:** Yes, use ngrok or similar tools to expose your local endpoint.

### Q: How do I secure my webhook endpoint?
**A:** Use HMAC signature verification, timestamp validation, and optionally IP allowlisting.

### Q: What happens if webhook delivery takes >10 seconds?
**A:** HTBase will timeout the request and mark it as failed. Respond quickly and process asynchronously.

### Q: Can I receive webhooks for batch operations?
**A:** Yes, each item in a batch will trigger a separate webhook when complete.

---

## Resources

- [Issue #008 - Webhook System Not Implemented](../.claude/todos/008-pending-p2-webhook-system-not-implemented.md)
- [API Quickstart](API_QUICKSTART.md)
- [Agent Best Practices](AGENT_GUIDE.md)
- [Error Codes Reference](ERROR_CODES.md)

---

**Questions?** Open an issue on GitHub.
