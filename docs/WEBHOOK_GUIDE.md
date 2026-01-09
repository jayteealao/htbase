# Webhook Guide

This guide explains how to use webhook notifications for asynchronous task completion in HTBase.

## Overview

HTBase supports HTTP webhook callbacks to notify your application when archive tasks complete. This eliminates the need for polling the task status endpoint, resulting in:

- More efficient resource usage
- Lower latency for receiving completion notifications
- Better integration with event-driven architectures
- Reduced API load

## Quick Start

### 1. Set Up a Webhook Endpoint

Create an endpoint in your application to receive webhook notifications:

```python
from fastapi import FastAPI, Request, HTTPException
import hmac
import hashlib
import json

app = FastAPI()

WEBHOOK_SECRET = "your-webhook-secret-here"

@app.post("/webhooks/htbase")
async def handle_htbase_webhook(request: Request):
    """Handle webhook from HTBase."""

    # Get signature from headers
    signature = request.headers.get("X-HTBase-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    # Get payload
    payload = await request.json()

    # Verify signature
    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Process webhook
    event = payload["event"]
    task_id = payload["task_id"]
    status = payload["status"]

    print(f"Task {task_id} completed with status: {status}")

    # Handle based on event type
    if event == "task.completed":
        for item in payload["items"]:
            print(f"  - {item['archiver']}: {item['status']}")

    return {"status": "ok"}


def verify_webhook_signature(payload: dict, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = hmac.new(
        secret.encode('utf-8'),
        json.dumps(payload, sort_keys=True).encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(f"sha256={expected}", signature)
```

### 2. Make Archive Request with Webhook

Include `webhook_url` and `webhook_secret` in your archive request:

```python
import httpx

response = httpx.post(
    "https://htbase.example.com/save",
    json={
        "url": "https://example.com/article",
        "id": "article-123",
        "archivers": ["readability", "screenshot"],
        "webhook_url": "https://your-app.com/webhooks/htbase",
        "webhook_secret": "your-webhook-secret-here"
    }
)

task = response.json()
print(f"Task submitted: {task['task_id']}")
# Your webhook will be called when the task completes
```

## Webhook Payload Format

### Task Completed Event

```json
{
  "event": "task.completed",
  "task_id": "a1b2c3d4e5f6",
  "status": "completed",
  "items": [
    {
      "url": "https://example.com/article",
      "id": "article-123",
      "archiver": "readability",
      "status": "success",
      "exit_code": 0,
      "saved_path": "/data/article-123/readability/output.json"
    },
    {
      "url": "https://example.com/article",
      "id": "article-123",
      "archiver": "screenshot",
      "status": "success",
      "exit_code": 0,
      "saved_path": "/data/article-123/screenshot/screenshot.png"
    }
  ],
  "timestamp": "2026-01-09T12:34:56Z"
}
```

### Task Failed Event

```json
{
  "event": "task.completed",
  "task_id": "a1b2c3d4e5f6",
  "status": "failed",
  "items": [
    {
      "url": "https://example.com/article",
      "id": "article-123",
      "archiver": "readability",
      "status": "failed",
      "exit_code": 1,
      "saved_path": null
    }
  ],
  "timestamp": "2026-01-09T12:34:56Z"
}
```

### Partial Success Event

```json
{
  "event": "task.completed",
  "task_id": "a1b2c3d4e5f6",
  "status": "partial",
  "items": [
    {
      "url": "https://example.com/article",
      "id": "article-123",
      "archiver": "readability",
      "status": "success",
      "exit_code": 0,
      "saved_path": "/data/article-123/readability/output.json"
    },
    {
      "url": "https://example.com/article",
      "id": "article-123",
      "archiver": "screenshot",
      "status": "failed",
      "exit_code": 1,
      "saved_path": null
    }
  ],
  "timestamp": "2026-01-09T12:34:56Z"
}
```

## Webhook Headers

HTBase includes the following headers in webhook requests:

| Header | Description | Example |
|--------|-------------|---------|
| `Content-Type` | Always `application/json` | `application/json` |
| `X-HTBase-Signature` | HMAC-SHA256 signature (if secret provided) | `sha256=abc123...` |
| `X-HTBase-Event` | Event type | `task.completed` |
| `User-Agent` | HTBase webhook identifier | `HTBase-Webhook/1.0` |

## Security Best Practices

### Always Verify Signatures

**CRITICAL:** Always verify webhook signatures to prevent spoofing attacks:

```python
import hmac
import hashlib
import json

def verify_webhook_signature(payload: dict, signature: str, secret: str) -> bool:
    """
    Verify HMAC-SHA256 signature.

    Args:
        payload: The webhook payload (dict)
        signature: The signature from X-HTBase-Signature header
        secret: Your webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    # Reconstruct the signature
    payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
    expected_sig = hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison
    return hmac.compare_digest(f"sha256={expected_sig}", signature)
```

### Use HTTPS for Webhook URLs

Always use HTTPS URLs for webhooks to ensure:
- Encryption in transit
- Protection against man-in-the-middle attacks
- Secure transmission of sensitive data

```python
# Good
webhook_url = "https://your-app.com/webhooks/htbase"

# Bad - Never use HTTP
webhook_url = "http://your-app.com/webhooks/htbase"
```

### Store Secrets Securely

Never hardcode webhook secrets in your code:

```python
import os

# Good - Use environment variables
WEBHOOK_SECRET = os.environ["HTBASE_WEBHOOK_SECRET"]

# Bad - Don't hardcode secrets
WEBHOOK_SECRET = "my-secret-123"  # Don't do this!
```

### Validate Webhook Payload

Always validate the webhook payload structure:

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class WebhookItem(BaseModel):
    url: str
    id: str
    archiver: str
    status: Literal["success", "failed"]
    exit_code: int
    saved_path: str | None

class WebhookPayload(BaseModel):
    event: str
    task_id: str
    status: Literal["completed", "failed", "partial"]
    items: List[WebhookItem]
    timestamp: str

@app.post("/webhooks/htbase")
async def handle_webhook(request: Request):
    payload_dict = await request.json()

    # Verify signature first
    signature = request.headers.get("X-HTBase-Signature")
    if not verify_webhook_signature(payload_dict, signature, WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid signature")

    # Validate payload structure
    try:
        payload = WebhookPayload(**payload_dict)
    except Exception as e:
        raise HTTPException(400, f"Invalid payload: {e}")

    # Process webhook
    # ...
```

## Event Types

HTBase currently supports the following webhook events:

| Event | Description | When Triggered |
|-------|-------------|----------------|
| `task.completed` | Task finished (success, failure, or partial) | When all archive operations complete |
| `task.failed` | Task failed entirely | When all archive operations fail |
| `task.created` | Task created (future) | When task is first accepted |

## Status Values

The `status` field in the webhook payload can have the following values:

| Status | Description |
|--------|-------------|
| `completed` | All archive operations succeeded |
| `failed` | All archive operations failed |
| `partial` | Some operations succeeded, some failed |
| `unknown` | Status could not be determined (rare) |

## Retry Behavior

HTBase automatically retries failed webhook deliveries with exponential backoff:

- **Max Retries:** 5 attempts
- **Initial Delay:** 60 seconds
- **Backoff:** Exponential with jitter
- **Max Backoff:** 10 minutes
- **Timeout:** 10 seconds per request

### Retry Conditions

Webhooks are retried for:
- ✅ 5xx server errors
- ✅ Network timeouts
- ✅ Connection errors
- ❌ 4xx client errors (not retried)

### Example Retry Sequence

```
Attempt 1: Immediate
Attempt 2: ~60 seconds later
Attempt 3: ~120 seconds later
Attempt 4: ~240 seconds later
Attempt 5: ~480 seconds later
Final failure: Logged and abandoned
```

## Error Handling

### Handle Webhook Errors Gracefully

Your webhook endpoint should:
1. Return 2xx status codes for successful processing
2. Return 4xx for permanent errors (HTBase won't retry)
3. Return 5xx for temporary errors (HTBase will retry)

```python
@app.post("/webhooks/htbase")
async def handle_webhook(request: Request):
    try:
        # Verify signature
        signature = request.headers.get("X-HTBase-Signature")
        payload = await request.json()

        if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
            # Permanent error - don't retry
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid signature"}
            )

        # Process webhook
        process_archive_completion(payload)

        # Success
        return {"status": "ok"}

    except DatabaseConnectionError:
        # Temporary error - HTBase will retry
        return JSONResponse(
            status_code=503,
            content={"error": "Database temporarily unavailable"}
        )
    except ValueError as e:
        # Permanent error - don't retry
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid payload: {e}"}
        )
```

## Advanced Usage

### Multiple Webhooks per Request

Currently, HTBase supports one webhook URL per request. To send to multiple endpoints, implement a fan-out pattern in your webhook handler:

```python
@app.post("/webhooks/htbase")
async def handle_webhook(request: Request):
    payload = await request.json()

    # Verify signature
    # ...

    # Fan out to multiple handlers
    await asyncio.gather(
        notify_slack(payload),
        update_database(payload),
        trigger_downstream_workflow(payload),
    )

    return {"status": "ok"}
```

### Webhook with Workflow Endpoint

The `/workflow` endpoint also supports webhooks via query parameters:

```python
response = httpx.post(
    "https://htbase.example.com/workflow",
    params={
        "webhook_url": "https://your-app.com/webhooks/htbase",
        "webhook_secret": "your-secret"
    },
    json={
        "url": "https://example.com/article",
        "item_id": "article-123",
        "archivers": ["all"],
        "summarize": True,
        "upload_to_storage": True
    }
)
```

### Batch Operations with Webhooks

For batch operations, use query parameters:

```python
response = httpx.post(
    "https://htbase.example.com/save/batch",
    params={
        "webhook_url": "https://your-app.com/webhooks/htbase",
        "webhook_secret": "your-secret"
    },
    json={
        "items": [
            {"url": "https://example.com/article1", "id": "article-1"},
            {"url": "https://example.com/article2", "id": "article-2"},
        ]
    }
)
```

## Language-Specific Examples

### Python (FastAPI)

See the examples above.

### Node.js (Express)

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

const WEBHOOK_SECRET = process.env.HTBASE_WEBHOOK_SECRET;

app.post('/webhooks/htbase', (req, res) => {
  const signature = req.headers['x-htbase-signature'];
  const payload = req.body;

  // Verify signature
  if (!verifySignature(payload, signature, WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Process webhook
  console.log(`Task ${payload.task_id} completed: ${payload.status}`);

  res.json({ status: 'ok' });
});

function verifySignature(payload, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload, Object.keys(payload).sort()))
    .digest('hex');

  const expectedSig = `sha256=${expected}`;

  // Constant-time comparison
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expectedSig)
  );
}

app.listen(3000);
```

### Go

```go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "net/http"
    "os"
    "sort"
)

type WebhookPayload struct {
    Event     string `json:"event"`
    TaskID    string `json:"task_id"`
    Status    string `json:"status"`
    Items     []Item `json:"items"`
    Timestamp string `json:"timestamp"`
}

type Item struct {
    URL        string  `json:"url"`
    ID         string  `json:"id"`
    Archiver   string  `json:"archiver"`
    Status     string  `json:"status"`
    ExitCode   int     `json:"exit_code"`
    SavedPath  *string `json:"saved_path"`
}

func handleWebhook(w http.ResponseWriter, r *http.Request) {
    signature := r.Header.Get("X-HTBase-Signature")

    var payload WebhookPayload
    if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
        http.Error(w, "Invalid payload", http.StatusBadRequest)
        return
    }

    // Verify signature
    secret := os.Getenv("HTBASE_WEBHOOK_SECRET")
    if !verifySignature(payload, signature, secret) {
        http.Error(w, "Invalid signature", http.StatusUnauthorized)
        return
    }

    // Process webhook
    // ...

    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func verifySignature(payload interface{}, signature, secret string) bool {
    // Sort keys for consistency
    payloadBytes, _ := json.Marshal(payload)

    mac := hmac.New(sha256.New, []byte(secret))
    mac.Write(payloadBytes)
    expected := "sha256=" + hex.EncodeToString(mac.Sum(nil))

    return hmac.Equal([]byte(signature), []byte(expected))
}

func main() {
    http.HandleFunc("/webhooks/htbase", handleWebhook)
    http.ListenAndServe(":8080", nil)
}
```

## Troubleshooting

### Webhook Not Received

1. **Check webhook URL is accessible:**
   ```bash
   curl -X POST https://your-app.com/webhooks/htbase \
     -H "Content-Type: application/json" \
     -d '{"test": "data"}'
   ```

2. **Check firewall rules** allow incoming connections from HTBase

3. **Verify HTTPS certificate** is valid (HTBase won't follow redirects)

4. **Check logs** in HTBase for webhook delivery errors

### Signature Verification Fails

1. **Ensure you're using the correct secret** (check environment variables)

2. **Verify JSON serialization** uses `sort_keys=True`:
   ```python
   # Correct
   json.dumps(payload, sort_keys=True)

   # Wrong - keys not sorted
   json.dumps(payload)
   ```

3. **Check for whitespace** in the signature or secret

4. **Use constant-time comparison:**
   ```python
   # Correct
   hmac.compare_digest(signature1, signature2)

   # Wrong - vulnerable to timing attacks
   signature1 == signature2
   ```

### Webhooks Timing Out

1. **Process webhooks asynchronously:**
   ```python
   @app.post("/webhooks/htbase")
   async def handle_webhook(request: Request):
       payload = await request.json()

       # Verify signature
       # ...

       # Queue for async processing
       await queue.enqueue(process_webhook, payload)

       # Return immediately
       return {"status": "ok"}
   ```

2. **Keep webhook handlers fast** (< 1 second)

3. **Use background tasks** for heavy processing

## API Reference

### SaveRequest Model

```python
class SaveRequest(BaseModel):
    url: HttpUrl
    id: str
    archivers: Optional[List[str]] = None
    priority: int = 0
    webhook_url: Optional[HttpUrl] = None  # NEW
    webhook_secret: Optional[str] = None   # NEW
```

### Webhook Payload Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["event", "task_id", "status", "items", "timestamp"],
  "properties": {
    "event": {
      "type": "string",
      "enum": ["task.created", "task.completed", "task.failed"]
    },
    "task_id": {
      "type": "string"
    },
    "status": {
      "type": "string",
      "enum": ["completed", "failed", "partial", "unknown"]
    },
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["url", "id", "archiver", "status", "exit_code"],
        "properties": {
          "url": {"type": "string"},
          "id": {"type": "string"},
          "archiver": {"type": "string"},
          "status": {"type": "string", "enum": ["success", "failed"]},
          "exit_code": {"type": "integer"},
          "saved_path": {"type": ["string", "null"]}
        }
      }
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

## Related Documentation

- [API Documentation](./API.md)
- [Architecture Overview](../REARCHITECTURE_PLAN.md)
- [Agent-Native Architecture](../.claude/skills/agent-native-architecture/references/architecture-patterns.md)

## Support

For webhook-related issues:
1. Check the [Troubleshooting](#troubleshooting) section above
2. Review the [webhook best practices](https://webhooks.fyi/)
3. File an issue on GitHub with:
   - Webhook URL (sanitized)
   - Request payload (without secrets)
   - Error messages from logs
   - Expected vs actual behavior
