# API Rate Limiting

HTBase API Gateway implements comprehensive rate limiting to protect against abuse, ensure fair resource allocation, and prevent service degradation.

## Overview

Rate limiting is enforced at two levels:

1. **Redis-based per-API-key limits** (Primary) - Distributed rate limiting that tracks requests per API key across all gateway instances
2. **SlowAPI IP-based limits** (Fallback) - In-memory rate limiting based on client IP address

## Rate Limit Configuration

Different endpoint types have different rate limits based on their resource cost:

| Endpoint Type | Rate Limit | Window | Use Case |
|---------------|------------|--------|----------|
| **Archive** | 10 requests | 1 minute | Single URL archiving operations |
| **Batch** | 5 requests | 1 minute | Batch archiving (multiple URLs) |
| **Status** | 1000 requests | 1 minute | Task status checks and queries |
| **Download** | 100 requests | 1 minute | Artifact retrieval and downloads |
| **Admin** | 50 requests | 1 minute | Administrative operations |

### Rationale

- **Archive endpoints** (10/min): Expensive Chromium worker operations, LLM processing
- **Batch endpoints** (5/min): Very expensive - multiplies archive cost by number of URLs
- **Status endpoints** (1000/min): Cheap database queries, can handle high volume
- **Download endpoints** (100/min): Medium cost - file system/GCS access
- **Admin endpoints** (50/min): Moderate restrictions for management operations

## Rate Limit Headers

All API responses include rate limit information in the headers:

```http
X-RateLimit-Limit: 10          # Maximum requests allowed in window
X-RateLimit-Remaining: 7       # Requests remaining in current window
X-RateLimit-Reset: 1704801300  # Unix timestamp when limit resets
```

### 429 Too Many Requests

When rate limit is exceeded, the API returns a 429 status code with additional information:

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704801300
Retry-After: 45

{
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded for archive endpoints",
  "details": {
    "limit": "10/60s",
    "reset_at": 1704801300,
    "retry_after": 45
  }
}
```

**Important Headers:**
- `Retry-After`: Seconds to wait before retrying
- `X-RateLimit-Reset`: Unix timestamp when your limit resets

## Endpoint Rate Limits

### Archive Endpoints (10/minute)

Single URL archiving operations:

- `POST /api/v1/save` - Archive a single URL
- `POST /api/v1/workflow` - Execute complete archive workflow
- `POST /api/v1/archive/{archiver}` - Archive with specific archiver

**Example:**
```bash
curl -X POST https://api.htbase.com/api/v1/save \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "id": "article-123",
    "archivers": ["singlefile", "pdf"]
  }'
```

**Response includes rate limit headers:**
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 9
X-RateLimit-Reset: 1704801360
```

### Batch Endpoints (5/minute)

Batch operations that process multiple URLs:

- `POST /api/v1/save/batch` - Archive multiple URLs
- `POST /api/v1/archive/{archiver}/batch` - Batch archive with specific archiver

**Why lower limits?** Batch endpoints multiply resource cost by the number of URLs. A single batch request with 10 URLs consumes resources equivalent to 10 archive requests.

**Example:**
```bash
curl -X POST https://api.htbase.com/api/v1/save/batch \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"url": "https://example.com/1", "id": "item-1"},
      {"url": "https://example.com/2", "id": "item-2"}
    ]
  }'
```

### Status Endpoints (1000/minute)

Lightweight operations for checking task status:

- `GET /api/v1/tasks/{task_id}` - Get task status
- `GET /api/v1/tasks/{task_id}/celery` - Get Celery task info
- `GET /api/v1/tasks` - List recent tasks
- `GET /api/v1/queue/stats` - Get queue statistics

**High limits** because these are read-only database queries with minimal resource cost.

### Download Endpoints (100/minute)

Retrieving archived content:

- `GET /api/v1/retrieve` - Retrieve archived artifacts
- `GET /api/v1/archive/{item_id}/size` - Get archive size

### Admin Endpoints (50/minute)

Administrative operations:

- `POST /api/v1/tasks/{task_id}/cancel` - Cancel a pending task
- Admin management endpoints

## Implementation Details

### Redis-based Rate Limiter

The primary rate limiting mechanism uses Redis for distributed tracking:

**Key Features:**
- Tracks requests per API key (not IP)
- Distributed across all API Gateway instances
- Sliding window algorithm
- Persists across gateway restarts
- Fails open if Redis is unavailable (allows requests)

**Redis Key Pattern:**
```
htbase:ratelimit:{api_key}:{window_timestamp}
```

**Algorithm:**
1. Generate window key: `prefix + api_key + (current_timestamp // window_seconds)`
2. Increment counter atomically in Redis
3. Set expiration on first request in window
4. Check if count exceeds limit
5. Return result with remaining quota

### SlowAPI Fallback

IP-based rate limiting provides a secondary layer of protection:

**Default Limit:** 1000 requests/minute per IP
**Use Case:** Protects against abuse when API key validation fails or for public endpoints

## Monitoring Rate Limits

### Check Your Current Limit Status

Inspect response headers on any API request:

```bash
curl -I https://api.htbase.com/api/v1/tasks/abc123 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Response:
```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1704801420
```

### Calculate Time Until Reset

```python
import time
from datetime import datetime

reset_timestamp = 1704801420  # From X-RateLimit-Reset header
current_time = int(time.time())
seconds_until_reset = reset_timestamp - current_time

print(f"Rate limit resets in {seconds_until_reset} seconds")
```

## Best Practices

### 1. Monitor Rate Limit Headers

Always check `X-RateLimit-Remaining` to avoid hitting limits:

```python
import requests

response = requests.post(
    "https://api.htbase.com/api/v1/save",
    headers={"Authorization": f"Bearer {api_key}"},
    json={"url": "https://example.com", "id": "123"}
)

remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
if remaining < 2:
    print("Warning: Approaching rate limit!")
```

### 2. Implement Exponential Backoff

When you receive a 429 response:

```python
import time
import requests

def make_request_with_retry(url, headers, data, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(url, headers=headers, json=data)

        if response.status_code != 429:
            return response

        # Get retry-after from response
        retry_after = int(response.headers.get("Retry-After", 60))

        print(f"Rate limited. Retrying in {retry_after} seconds...")
        time.sleep(retry_after)

    raise Exception("Max retries exceeded")
```

### 3. Use Batch Endpoints Wisely

Batch endpoints have lower limits. If you need to process many URLs:

```python
# Good: Chunk requests and respect rate limits
def archive_urls(urls, api_key):
    chunk_size = 50  # Process 50 URLs per batch
    chunks = [urls[i:i+chunk_size] for i in range(0, len(urls), chunk_size)]

    for chunk in chunks:
        response = requests.post(
            "https://api.htbase.com/api/v1/save/batch",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"items": [{"url": url, "id": f"item-{i}"} for i, url in enumerate(chunk)]}
        )

        # Check if approaching limit
        remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
        if remaining < 2:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait_time = reset_time - int(time.time())
            print(f"Approaching limit. Waiting {wait_time}s...")
            time.sleep(wait_time)
```

### 4. Use Status Endpoints for Polling

Status endpoints have high limits (1000/min), making them suitable for polling:

```python
import time

def wait_for_completion(task_id, api_key, poll_interval=5):
    while True:
        response = requests.get(
            f"https://api.htbase.com/api/v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        status = response.json()["status"]
        if status in ["completed", "failed"]:
            return status

        time.sleep(poll_interval)
```

### 5. Cache Results When Possible

Avoid redundant API calls:

```python
from functools import lru_cache
import time

@lru_cache(maxsize=1000)
def get_cached_task_status(task_id, api_key, cache_key):
    response = requests.get(
        f"https://api.htbase.com/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    return response.json()

# Use current minute as cache key for status checks
cache_key = int(time.time() // 60)
status = get_cached_task_status(task_id, api_key, cache_key)
```

## Troubleshooting

### Issue: Constantly Hitting Rate Limits

**Solutions:**
1. Check if you're using batch endpoints when you could use single requests
2. Implement request queuing with proper spacing
3. Cache status checks instead of polling too frequently
4. Consider upgrading your plan for higher limits (future feature)

### Issue: Rate Limit Resets Not Working

**Check:**
- Redis connection is healthy
- System clock is synchronized (rate limiting uses timestamps)
- API key is valid and hasn't been rotated

### Issue: Different Limits Than Expected

**Verify:**
- You're using the correct endpoint type
- API key is properly authenticated
- Not mixing different endpoint types in calculations

## Future Enhancements

### Planned Features

1. **Tiered Rate Limits** - Different limits based on subscription level
   - Free: Current limits
   - Pro: 5x higher limits
   - Enterprise: Custom limits

2. **Rate Limit Dashboard** - Web UI to monitor your usage
   - Real-time quota usage
   - Historical usage graphs
   - Alerts before hitting limits

3. **Burst Allowances** - Short-term bursts above normal limits
   - Unused quota rolls over for 1 hour
   - Allows occasional spikes without hitting limits

4. **Per-Operation Costs** - More granular cost tracking
   - Different costs for different archivers
   - Credits-based system for flexible allocation

## API Reference

### Rate Limit Response Format

**Success Response (200):**
```json
{
  "task_id": "abc123def456",
  "count": 5,
  "message": "Archive tasks dispatched"
}
```

Headers:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 5
X-RateLimit-Reset: 1704801360
```

**Rate Limit Exceeded (429):**
```json
{
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded for archive endpoints",
  "details": {
    "limit": "10/60s",
    "reset_at": 1704801360,
    "retry_after": 45
  }
}
```

Headers:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704801360
Retry-After: 45
```

## Support

For questions about rate limits or to request limit increases:
- Check current limits in API response headers
- Review this documentation for optimization tips
- Contact support for custom rate limit requirements

## Related Documentation

- [API Authentication](./docs/authentication.md) - API key setup
- [API Reference](./docs/api-reference.md) - Complete endpoint documentation
- [Error Handling](./docs/errors.md) - Error codes and troubleshooting
