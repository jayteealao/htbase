# HTBase Agent Best Practices

A comprehensive guide for AI agents and automated systems using HTBase.

---

## Overview

HTBase is designed for programmatic access by AI agents, bots, and automation systems. This guide covers:

- Architecture patterns for reliable integration
- Performance optimization strategies
- Error handling and retry logic
- Resource management
- Production deployment considerations

---

## Architecture Patterns

### Pattern 1: Request-Response (Synchronous)

**Use case:** Immediate results for single URLs

```python
import requests

def archive_url(url: str, item_id: str, archiver: str = "readability"):
    """Synchronous archive with immediate response."""
    response = requests.post(
        f"http://localhost:8000/api/save/{archiver}",
        json={"url": url, "id": item_id},
        timeout=300  # 5 minutes
    )
    response.raise_for_status()
    return response.json()

# Usage
result = archive_url("https://example.com", "article-123")
if result["ok"] and result["exit_code"] == 0:
    print(f"Archived to: {result['saved_path']}")
```

**Pros:**
- Simple implementation
- Immediate results
- No polling needed

**Cons:**
- Blocks until completion (up to 5 minutes)
- Doesn't scale for batch operations
- Connection timeouts possible

---

### Pattern 2: Batch-and-Poll (Asynchronous)

**Use case:** Multiple URLs, non-blocking operation

```python
import requests
import time
from typing import List, Dict

class HTBaseClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def batch_archive(self, items: List[Dict[str, str]], archiver: str = "readability"):
        """Submit batch archive request."""
        response = requests.post(
            f"{self.base_url}/api/batch/{archiver}",
            json={"items": items},
            timeout=30
        )
        response.raise_for_status()
        return response.json()["task_id"]

    def get_task_status(self, task_id: str):
        """Poll for task status."""
        response = requests.get(
            f"{self.base_url}/api/tasks/{task_id}",
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(self, task_id: str, poll_interval: int = 5, max_wait: int = 600):
        """Wait for batch task to complete."""
        start = time.time()
        while time.time() - start < max_wait:
            status = self.get_task_status(task_id)
            if status["status"] in ["success", "failed"]:
                return status
            time.sleep(poll_interval)
        raise TimeoutError(f"Task {task_id} did not complete in {max_wait}s")

# Usage
client = HTBaseClient()
items = [
    {"url": "https://example.com/1", "id": "article-1"},
    {"url": "https://example.com/2", "id": "article-2"},
]
task_id = client.batch_archive(items)
result = client.wait_for_completion(task_id)
print(f"Batch completed: {result['status']}")
```

**Pros:**
- Non-blocking
- Scales to hundreds of URLs
- Efficient for bulk operations

**Cons:**
- Requires polling logic
- Delayed results
- More complex implementation

**Best for:** Agents processing RSS feeds, bulk imports, batch jobs

---

### Pattern 3: Webhook-Driven (Event-Based)

**Use case:** Real-time notifications without polling

> **Note:** Webhook support is planned but not yet implemented. See [Issue #008](../../.claude/todos/008-pending-p2-webhook-system-not-implemented.md).

**Planned API:**
```python
# Future implementation
def archive_with_webhook(url: str, item_id: str, webhook_url: str):
    response = requests.post(
        "http://localhost:8000/api/save/readability",
        json={
            "url": url,
            "id": item_id,
            "webhook_url": webhook_url  # Not yet implemented
        }
    )
    return response.json()

# Your webhook endpoint receives:
# POST https://your-agent.com/webhook
# {
#   "task_id": "...",
#   "status": "success",
#   "item_id": "article-123",
#   "saved_path": "...",
#   "exit_code": 0
# }
```

**Pros:**
- No polling overhead
- Real-time notifications
- Resource efficient

**Cons:**
- Requires publicly accessible webhook endpoint
- More complex infrastructure

**When available:** Recommended for production agents handling high volumes

---

## Error Handling Strategies

### Strategy 1: Exponential Backoff

Handle transient failures gracefully:

```python
import time
import requests
from typing import Optional

def archive_with_retry(
    url: str,
    item_id: str,
    archiver: str = "readability",
    max_retries: int = 3,
    base_delay: int = 2
) -> Optional[dict]:
    """Retry with exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"http://localhost:8000/api/save/{archiver}",
                json={"url": url, "id": item_id},
                timeout=300
            )
            response.raise_for_status()
            result = response.json()

            # Check exit code
            if result.get("exit_code") == 0:
                return result

            # Non-retryable error codes
            if result.get("exit_code") == 404:
                print(f"URL not found: {url}")
                return result

            # Retryable failure
            if attempt < max_retries - 1:
                wait = base_delay ** attempt  # 2s, 4s, 8s
                print(f"Attempt {attempt + 1} failed, retrying in {wait}s...")
                time.sleep(wait)
                continue

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait = base_delay ** attempt
                print(f"Timeout on attempt {attempt + 1}, retrying in {wait}s...")
                time.sleep(wait)
                continue

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay ** attempt)
                continue

    return None  # All retries exhausted
```

---

### Strategy 2: Circuit Breaker

Protect against cascading failures:

```python
from datetime import datetime, timedelta

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = datetime.now()
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
            raise

# Usage
breaker = CircuitBreaker()

def archive_safe(url, item_id):
    return breaker.call(archive_url, url, item_id)
```

---

### Strategy 3: Fallback Archivers

Try alternative archivers if primary fails:

```python
def archive_with_fallback(url: str, item_id: str, archivers: list = None):
    """Try multiple archivers in order until one succeeds."""
    if archivers is None:
        archivers = ["readability", "monolith", "singlefile-cli"]

    for archiver in archivers:
        try:
            result = archive_url(url, item_id, archiver)
            if result.get("ok") and result.get("exit_code") == 0:
                print(f"Success with {archiver}")
                return result
        except Exception as e:
            print(f"{archiver} failed: {e}")
            continue

    raise Exception(f"All archivers failed for {url}")
```

---

## Performance Optimization

### Optimization 1: Skip Existing Archives

Avoid re-archiving URLs you've already saved:

```bash
export SKIP_EXISTING_SAVES=true
```

HTBase will check for existing archives before processing:

```python
# First call - archives the URL
result = archive_url("https://example.com", "article-123")
# saved_path: /data/article-123/readability/output.html

# Second call - reuses existing archive
result = archive_url("https://example.com", "article-123")
# saved_path: /data/article-123/readability/output.html (same file, no re-archiving)
```

**Savings:** 5-30 seconds per URL (no archiver execution)

---

### Optimization 2: Batch Operations

Use batch endpoints for multiple URLs:

```python
# Inefficient: 100 sequential requests
for url in urls:
    archive_url(url, f"article-{i}")

# Efficient: 1 batch request
items = [{"url": url, "id": f"article-{i}"} for i, url in enumerate(urls)]
task_id = client.batch_archive(items, archiver="readability")
```

**Savings:** Reduces HTTP overhead, improves throughput

---

### Optimization 3: Parallel Processing

Process multiple archives concurrently:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def archive_parallel(urls: List[str], max_workers: int = 5):
    """Archive multiple URLs in parallel."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(archive_url, url, f"article-{i}"): url
            for i, url in enumerate(urls)
        }

        results = []
        for future in as_completed(futures):
            url = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"Failed to archive {url}: {e}")

        return results

# Usage
urls = ["https://example.com/1", "https://example.com/2", ...]
results = archive_parallel(urls, max_workers=10)
```

**Recommendation:** Use `max_workers=5-10` to avoid overwhelming the server

---

### Optimization 4: Choose Fast Archivers

Different archivers have different performance characteristics:

| Archiver | Speed | Quality | Use Case |
|----------|-------|---------|----------|
| **readability** | Fast (5-10s) | Good text extraction | AI/LLM processing |
| **monolith** | Fast (5-15s) | Complete HTML | Quick archiving |
| **singlefile-cli** | Slow (15-30s) | High fidelity | Complete preservation |
| **pdf** | Slow (10-25s) | Print quality | Documents |
| **screenshot** | Fast (5-10s) | Visual only | Quick snapshots |

**Recommendation:**
- For AI agents: Use `readability` (fast, clean output)
- For preservation: Use `singlefile-cli` or `monolith`
- For visual verification: Use `screenshot`

---

## Resource Management

### Memory Considerations

**Chromium-based archivers** (singlefile-cli, pdf, screenshot) use 500MB-2GB per instance.

**Best practices:**
1. Limit concurrent Chromium processes
2. Monitor memory usage
3. Implement request queuing

```python
from queue import Queue
from threading import Thread

class ArchiveQueue:
    def __init__(self, max_concurrent: int = 3):
        self.queue = Queue()
        self.max_concurrent = max_concurrent
        self.workers = []

    def start_workers(self):
        for _ in range(self.max_concurrent):
            worker = Thread(target=self._worker)
            worker.daemon = True
            worker.start()
            self.workers.append(worker)

    def _worker(self):
        while True:
            url, item_id, callback = self.queue.get()
            try:
                result = archive_url(url, item_id, archiver="singlefile-cli")
                if callback:
                    callback(result)
            finally:
                self.queue.task_done()

    def submit(self, url: str, item_id: str, callback=None):
        self.queue.put((url, item_id, callback))

    def wait_completion(self):
        self.queue.join()

# Usage
queue = ArchiveQueue(max_concurrent=3)
queue.start_workers()

for url in urls:
    queue.submit(url, f"article-{i}")

queue.wait_completion()
```

---

### Disk Space Management

Archives consume disk space:
- **Readability:** 50KB-500KB per page
- **Monolith:** 100KB-2MB per page
- **SingleFile:** 500KB-5MB per page
- **PDF:** 200KB-5MB per page
- **Screenshot:** 100KB-1MB per image

**Monitoring:**
```python
import shutil

def check_disk_space(path: str = "./data", min_gb: float = 10.0):
    """Check available disk space before archiving."""
    stat = shutil.disk_usage(path)
    available_gb = stat.free / (1024 ** 3)

    if available_gb < min_gb:
        raise Exception(f"Low disk space: {available_gb:.2f}GB available")

    return available_gb

# Usage
check_disk_space(min_gb=10.0)  # Raise error if < 10GB free
```

**Cleanup strategies:**
1. Delete old archives after N days
2. Use GCS storage for long-term retention
3. Archive only essential formats

---

### Rate Limiting

Respect target website rate limits:

```python
import time
from collections import defaultdict
from urllib.parse import urlparse

class RateLimiter:
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.domain_timestamps = defaultdict(list)

    def wait_if_needed(self, url: str):
        """Wait if rate limit would be exceeded."""
        domain = urlparse(url).netloc
        now = time.time()

        # Remove timestamps older than 1 minute
        self.domain_timestamps[domain] = [
            ts for ts in self.domain_timestamps[domain]
            if now - ts < 60
        ]

        # Check if rate limit reached
        if len(self.domain_timestamps[domain]) >= self.requests_per_minute:
            oldest = self.domain_timestamps[domain][0]
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                print(f"Rate limit reached for {domain}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)

        self.domain_timestamps[domain].append(now)

# Usage
limiter = RateLimiter(requests_per_minute=10)

for url in urls:
    limiter.wait_if_needed(url)
    archive_url(url, ...)
```

---

## Production Deployment Checklist

### Security
- [ ] Enable authentication (see [AUTHENTICATION.md](AUTHENTICATION.md))
- [ ] Use HTTPS in production
- [ ] Set up firewall rules
- [ ] Implement API rate limiting

### Monitoring
- [ ] Set up health check polling (`GET /api/health`)
- [ ] Monitor disk usage
- [ ] Track error rates
- [ ] Set up alerts for failures

### Scalability
- [ ] Deploy behind load balancer
- [ ] Use GCS for file storage
- [ ] Configure PostgreSQL for high availability
- [ ] Enable connection pooling

### Reliability
- [ ] Implement retry logic in client
- [ ] Set up automatic restarts (systemd, Docker restart policy)
- [ ] Configure backup strategy
- [ ] Test failover procedures

---

## Testing Your Integration

### Unit Tests

```python
import unittest
from unittest.mock import patch, Mock

class TestHTBaseClient(unittest.TestCase):
    def test_successful_archive(self):
        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = {
                "ok": True,
                "exit_code": 0,
                "saved_path": "/data/test/readability/output.html",
                "id": "test-123"
            }

            result = archive_url("https://example.com", "test-123")
            self.assertTrue(result["ok"])
            self.assertEqual(result["exit_code"], 0)

    def test_retry_on_failure(self):
        with patch('requests.post') as mock_post:
            # Fail twice, succeed on third attempt
            mock_post.side_effect = [
                Mock(status_code=500),
                Mock(status_code=500),
                Mock(json=lambda: {"ok": True, "exit_code": 0})
            ]

            result = archive_with_retry("https://example.com", "test")
            self.assertEqual(result["exit_code"], 0)
```

### Integration Tests

```python
def test_end_to_end_archive():
    """Test actual API integration."""
    url = "https://example.com"
    item_id = f"test-{int(time.time())}"

    # Archive
    result = archive_url(url, item_id)
    assert result["ok"]
    assert result["exit_code"] == 0
    assert result["saved_path"]

    # Retrieve
    response = requests.get(
        f"http://localhost:8000/api/retrieve?id={item_id}&archiver=readability"
    )
    assert response.status_code == 200
    assert len(response.content) > 0
```

---

## Example Agent Implementations

### Example 1: RSS Feed Archiver

```python
import feedparser
import hashlib

class RSSArchiver:
    def __init__(self, htbase_url: str):
        self.htbase_url = htbase_url
        self.client = HTBaseClient(htbase_url)

    def generate_id(self, url: str) -> str:
        """Generate stable ID from URL."""
        return hashlib.md5(url.encode()).hexdigest()

    def archive_feed(self, feed_url: str):
        """Archive all items from RSS feed."""
        feed = feedparser.parse(feed_url)
        items = []

        for entry in feed.entries:
            item_id = self.generate_id(entry.link)
            items.append({
                "url": entry.link,
                "id": item_id
            })

        # Batch archive
        task_id = self.client.batch_archive(items, archiver="readability")
        result = self.client.wait_for_completion(task_id)

        # Report results
        success = sum(1 for item in result["items"] if item["status"] == "success")
        print(f"Archived {success}/{len(items)} articles from {feed_url}")

        return result

# Usage
archiver = RSSArchiver("http://localhost:8000")
archiver.archive_feed("https://example.com/feed.xml")
```

---

### Example 2: Dead Link Checker

```python
class DeadLinkChecker:
    def __init__(self, htbase_url: str):
        self.client = HTBaseClient(htbase_url)

    def check_url(self, url: str) -> bool:
        """Check if URL is alive by attempting to archive."""
        item_id = f"check-{int(time.time())}"
        result = archive_url(url, item_id, archiver="readability")

        # Clean up (delete the archive since we only wanted to check)
        if result.get("db_rowid"):
            try:
                requests.delete(
                    f"{self.client.base_url}/api/admin/delete",
                    params={"rowid": result["db_rowid"]}
                )
            except:
                pass

        return result.get("exit_code") != 404

    def check_links(self, urls: List[str]) -> Dict[str, bool]:
        """Check multiple URLs in parallel."""
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.check_url, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    results[url] = future.result()
                except:
                    results[url] = False
        return results

# Usage
checker = DeadLinkChecker("http://localhost:8000")
links = ["https://example.com/1", "https://example.com/2"]
status = checker.check_links(links)
dead_links = [url for url, alive in status.items() if not alive]
print(f"Dead links: {dead_links}")
```

---

## Debugging Tips

### Enable Verbose Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Inspect Saved Files

```python
import json
from pathlib import Path

def inspect_archive(item_id: str, archiver: str = "readability"):
    """Inspect saved archive files."""
    path = Path(f"./data/{item_id}/{archiver}/output.html")
    if not path.exists():
        print(f"File not found: {path}")
        return

    print(f"File size: {path.stat().st_size} bytes")

    if archiver == "readability":
        # Check for metadata.json
        metadata_path = path.parent / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            print(f"Title: {metadata.get('title')}")
            print(f"Author: {metadata.get('byline')}")
            print(f"Excerpt: {metadata.get('excerpt')}")

    # Show first 500 chars
    content = path.read_text(errors='ignore')
    print(f"Content preview:\n{content[:500]}")
```

### Test Archive Quality

```python
def validate_archive_quality(item_id: str, min_size: int = 1000):
    """Validate that archive meets quality standards."""
    path = Path(f"./data/{item_id}/readability/output.html")

    if not path.exists():
        raise ValueError(f"Archive not found: {path}")

    size = path.stat().st_size
    if size < min_size:
        raise ValueError(f"Archive too small: {size} bytes (min {min_size})")

    content = path.read_text()
    if "404" in content or "Not Found" in content:
        raise ValueError("Archive contains 404 error page")

    print(f"Archive quality OK: {size} bytes")
    return True
```

---

## FAQ

### Q: Should I use synchronous or batch endpoints?
**A:** Use synchronous for <10 URLs, batch for larger operations.

### Q: How do I handle rate limiting?
**A:** Implement client-side rate limiting and exponential backoff (see examples above).

### Q: Which archiver should I use?
**A:** For AI/LLM work, use `readability`. For preservation, use `singlefile-cli`.

### Q: How do I avoid re-archiving the same URL?
**A:** Set `SKIP_EXISTING_SAVES=true` and use consistent IDs.

### Q: What happens if archiving times out?
**A:** HTBase has 5-minute timeouts. For slow sites, consider using faster archivers.

### Q: Can I archive authenticated pages?
**A:** Not currently supported. Future feature.

### Q: How do I clean up old archives?
**A:** Use the delete endpoint: `DELETE /api/admin/delete?rowid=123`

---

## Next Steps

- [API Quickstart](API_QUICKSTART.md) - Get started in 5 minutes
- [Error Codes Reference](ERROR_CODES.md) - Troubleshooting guide
- [Authentication Setup](AUTHENTICATION.md) - Secure your API
- [Webhooks Guide](WEBHOOKS.md) - Real-time notifications (planned)
- [Code Examples](../examples/) - Working code samples

---

**Questions or feedback?** Open an issue on GitHub.
