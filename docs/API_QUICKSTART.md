# HTBase API Quick Start

## Overview

HTBase is a web archiving service designed for programmatic access by developers and AI agents. This guide will get you started with the API in 5 minutes.

**What you can do:**
- Archive web pages using multiple formats (Readability, Monolith, SingleFile, PDF, Screenshot)
- Check archiving task status
- Retrieve archived content
- Generate AI summaries of archived articles

> **Note:** As of 2026-01-16, HTBase uses a microservices architecture. All API endpoints use the `/api/v1/` prefix.

---

## Quick Start: Archive Your First URL

### 1. Archive a URL

**Request:**
```bash
curl -X POST http://localhost:8080/api/v1/archives \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [{"id": "my-first-save", "url": "https://example.com"}],
    "archivers": ["readability"]
  }'
```

**Response:**
```json
{
  "ok": true,
  "exit_code": 0,
  "saved_path": "/data/my-first-save/readability/output.html",
  "id": "my-first-save",
  "db_rowid": 1
}
```

### 2. Retrieve Your Archive

**Request:**
```bash
curl http://localhost:8080/api/v1/archives/my-first-save/download?archiver=readability
```

This will download the archived file.

---

## Available Archivers

HTBase supports multiple archiving formats, each optimized for different use cases:

| Archiver | Output Format | Best For | Endpoint |
|----------|--------------|----------|----------|
| **readability** | Clean HTML + JSON metadata | Article text extraction, AI processing | `/api/v1/archives` |
| **monolith** | Single HTML file | Complete page preservation | `/api/v1/archives` |
| **singlefile-cli** | Single HTML file with embedded assets | Offline viewing, complete fidelity | `/api/v1/archives` |
| **pdf** | PDF | Print-ready documents | `/api/v1/archives` |
| **screenshot** | PNG | Visual snapshots | `/api/v1/archives` |
| **all** | All formats | Comprehensive archiving | `/api/v1/archives` |

---

## Common Workflows

### Workflow 1: Archive Multiple Formats

Archive a URL with all available archivers:

```bash
curl -X POST http://localhost:8080/api/v1/archives \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [{"id": "article-2026-01-09", "url": "https://www.example.com/article"}],
    "archivers": ["all"]
  }'
```

### Workflow 2: Batch Archiving

Archive multiple URLs at once:

```bash
curl -X POST http://localhost:8080/api/v1/archives \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"id": "article-1", "url": "https://example.com/1"},
      {"id": "article-2", "url": "https://example.com/2"},
      {"id": "article-3", "url": "https://example.com/3"}
    ],
    "archivers": ["readability"]
  }'
```

**Response:**
```json
{
  "task_id": "batch-abc123",
  "count": 3
}
```

### Workflow 3: Check Batch Task Status

```bash
curl http://localhost:8080/api/v1/tasks/batch-abc123
```

**Response:**
```json
{
  "task_id": "batch-abc123",
  "status": "success",
  "items": [
    {
      "url": "https://example.com/1",
      "id": "article-1",
      "status": "success",
      "exit_code": 0,
      "saved_path": "/data/article-1/readability/output.html",
      "db_rowid": 10
    },
    {
      "url": "https://example.com/2",
      "id": "article-2",
      "status": "success",
      "exit_code": 0,
      "saved_path": "/data/article-2/readability/output.html",
      "db_rowid": 11
    },
    {
      "url": "https://example.com/3",
      "id": "article-3",
      "status": "failed",
      "exit_code": 404
    }
  ]
}
```

### Workflow 4: Generate AI Summary

After archiving with `readability`, generate an AI summary:

```bash
curl -X POST http://localhost:8080/api/v1/system/summarize \
  -H 'Content-Type: application/json' \
  -d '{
    "item_id": "my-first-save"
  }'
```

**Response:**
```json
{
  "ok": true,
  "archived_url_id": 1,
  "summary_created": true
}
```

### Workflow 5: Retrieve All Formats

Download all archived formats for a URL as a tarball:

```bash
curl http://localhost:8080/api/v1/archives/article-2026-01-09/download?archiver=all \
  --output article-2026-01-09.tar.gz
```

---

## Understanding Exit Codes

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| `0` | Success | Archive completed successfully |
| `404` | Not Found | URL returned 404, cannot archive |
| `21` | Chromium Lock Error | Restart service to clear stale locks |
| `1` | General Failure | Check archiver logs for details |

---

## Error Handling

### URL Not Found (404)

```json
{
  "ok": false,
  "exit_code": 404,
  "saved_path": null,
  "id": "missing-article"
}
```

**Resolution:** The URL does not exist or returned 404. Verify the URL is correct.

### Missing Required Field

```bash
curl -X POST http://localhost:8080/api/v1/archives \
  -H 'Content-Type: application/json' \
  -d '{"items": [{"url": "https://example.com"}]}'
```

**Error:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "id"],
      "msg": "Field required"
    }
  ]
}
```

**Resolution:** Include the `id` field in your request.

---

## Best Practices for Agents

### 1. Use Descriptive IDs

Use meaningful identifiers that help you organize archives:

```bash
# Good
"id": "nytimes-2026-01-09-ai-article"

# Avoid
"id": "temp123"
```

### 2. Skip Existing Archives

Enable skip mode to avoid re-archiving:

```bash
export SKIP_EXISTING_SAVES=true
```

HTBase will check if an archive already exists before processing.

### 3. Choose the Right Archiver

- **For AI/LLM processing**: Use `readability` (clean text + metadata)
- **For complete preservation**: Use `singlefile-cli` or `monolith`
- **For visual records**: Use `screenshot`
- **For printing/PDFs**: Use `pdf`
- **For everything**: Use `all`

### 4. Handle Batch Operations

For multiple URLs, use batch mode to improve efficiency:

```python
# Efficient
POST /api/v1/archives with {"items": [100 items], "archivers": ["readability"]}

# Inefficient
100 individual POST /api/v1/archives calls
```

### 5. Implement Retry Logic

Handle transient failures with exponential backoff:

```python
import time

def archive_with_retry(url, id, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "http://localhost:8080/api/v1/archives",
                json={
                    "items": [{"url": url, "id": id}],
                    "archivers": ["readability"]
                }
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            time.sleep(wait_time)
```

---

## Advanced Features

### Paywall Bypass

HTBase automatically rewrites certain paywalled URLs:

- **WSJ articles**: Adds Google referrer for 12ft.io compatibility
- **Medium articles**: Converts to freedium.cfd

This happens transparently - you don't need to modify your URLs.

### Automatic Summarization

When `readability` archiving succeeds and summarization is enabled, HTBase automatically queues an AI summary task. No manual triggering required.

### Storage Providers

HTBase supports multiple storage backends:

- **Local filesystem**: Default, stores in `./data`
- **Google Cloud Storage (GCS)**: For production deployments
- **Dual persistence**: PostgreSQL + Firestore for high availability

---

## Interactive API Documentation

Visit the interactive API docs while your server is running:

- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

---

## Next Steps

- [Error Codes Reference](ERROR_CODES.md) - Complete list of error codes and resolutions
- [Authentication Guide](AUTHENTICATION.md) - Set up API key authentication (required for production)
- [Agent Best Practices](AGENT_GUIDE.md) - Patterns for AI agents
- [Webhooks Guide](WEBHOOKS.md) - Real-time notifications (recommended over polling)
- [Code Examples](../examples/) - Python, JavaScript, and curl examples

---

## Quick Reference

### Core Endpoints

```
# Archive (Single or Batch)
POST /api/v1/archives                  Body: {"items": [...], "archivers": [...]}

# List Archives
GET  /api/v1/archives                  Query: limit=..., offset=...

# Get Archive Details
GET  /api/v1/archives/{item_id}        Query: include=...

# Download Archive
GET  /api/v1/archives/{item_id}/download  Query: archiver=...

# Delete Archive
DELETE /api/v1/archives                Query: identifier=..., type=...

# Task Status
GET  /api/v1/tasks/{task_id}           Query: include_celery=...

# List Archivers
GET  /api/v1/system/archivers

# System Statistics
GET  /api/v1/system/stats

# Summarize
POST /api/v1/system/summarize          Body: {"item_id": "..."}

# Health Check
GET  /health
```

### Available Archivers

`readability` | `monolith` | `singlefile-cli` | `pdf` | `screenshot` | `all`

### Request Format

All POST requests require `Content-Type: application/json`.

Required fields:
- `id` - Unique identifier for this archive
- `url` - Valid HTTP/HTTPS URL to archive

---

**Need help?** Open an issue on GitHub or refer to the [full architecture documentation](REARCHITECTURE_PLAN.md).
