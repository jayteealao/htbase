# Webhook Quick Start

Get started with HTBase webhooks in 5 minutes.

## 1. Create Webhook Endpoint

```python
from fastapi import FastAPI, Request, HTTPException
import hmac, hashlib, json

app = FastAPI()
SECRET = "your-secret-here"

@app.post("/webhooks/htbase")
async def webhook(request: Request):
    # Verify signature
    sig = request.headers.get("X-HTBase-Signature")
    payload = await request.json()

    expected = "sha256=" + hmac.new(
        SECRET.encode(),
        json.dumps(payload, sort_keys=True).encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "Invalid signature")

    # Process webhook
    print(f"Task {payload['task_id']}: {payload['status']}")
    for item in payload["items"]:
        print(f"  {item['archiver']}: {item['status']}")

    return {"ok": True}
```

## 2. Make Archive Request

```python
import httpx

response = httpx.post(
    "https://htbase.example.com/save",
    json={
        "url": "https://example.com/article",
        "id": "article-123",
        "archivers": ["readability", "screenshot"],
        "webhook_url": "https://yourapp.com/webhooks/htbase",
        "webhook_secret": "your-secret-here"
    }
)

print(f"Task submitted: {response.json()['task_id']}")
```

## 3. Receive Webhook

```json
{
  "event": "task.completed",
  "task_id": "abc123",
  "status": "completed",
  "items": [
    {
      "url": "https://example.com/article",
      "id": "article-123",
      "archiver": "readability",
      "status": "success",
      "saved_path": "/data/article-123/readability/output.json"
    }
  ],
  "timestamp": "2026-01-09T12:34:56Z"
}
```

## Key Points

✅ **Always verify signatures** to prevent spoofing
✅ **Use HTTPS** for webhook URLs
✅ **Store secrets** in environment variables
✅ **Return quickly** from webhook handler (< 1s)
✅ **Return 2xx** for success, 5xx for retry, 4xx for permanent error

❌ **Never hardcode secrets** in your code
❌ **Never skip signature verification**
❌ **Never use HTTP** (always HTTPS)

## Signature Verification

```python
import hmac, hashlib, json

def verify(payload: dict, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        json.dumps(payload, sort_keys=True).encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

## Retry Behavior

- **Max retries:** 5
- **Initial delay:** 60s
- **Max backoff:** 10 minutes
- **Timeout:** 10s per request
- **Retries on:** 5xx, timeouts, network errors
- **No retry on:** 4xx client errors

## Next Steps

Read the [full Webhook Guide](./WEBHOOK_GUIDE.md) for:
- Event types
- Security best practices
- Language-specific examples
- Troubleshooting
- Advanced patterns
