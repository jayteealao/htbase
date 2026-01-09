# HTBase Error Codes Reference

Complete reference of error codes, their meanings, and resolution steps.

---

## HTTP Status Codes

### 200 OK
**Meaning:** Request completed successfully.

**When returned:**
- Successful archive operation
- Successful retrieval
- Task status query succeeded

**Example:**
```json
{
  "ok": true,
  "exit_code": 0,
  "saved_path": "/data/article-123/readability/output.html",
  "id": "article-123",
  "db_rowid": 42
}
```

---

### 400 Bad Request
**Meaning:** Invalid request format or missing required fields.

**Common causes:**
1. Missing required field (`id` or `url`)
2. Invalid URL format
3. Malformed JSON

**Example Error:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "id"],
      "msg": "Field required",
      "input": {"url": "https://example.com"}
    }
  ]
}
```

**Resolution:**
- Verify all required fields are present
- Check JSON syntax
- Ensure URL is valid HTTP/HTTPS format

**Correct Request:**
```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "my-article",
    "url": "https://example.com"
  }'
```

---

### 404 Not Found

**Meaning:** Resource not found.

**Common causes:**
1. Task ID doesn't exist
2. Archive ID not found in database
3. Invalid API endpoint

**Example - Task Not Found:**
```json
{
  "detail": "task not found"
}
```

**Example - Save Not Found:**
```json
{
  "detail": "save not found"
}
```

**Resolution:**
- Verify the task ID or archive ID is correct
- Check that the archive operation completed
- Confirm the endpoint path is correct

---

### 422 Unprocessable Entity

**Meaning:** Request syntax is valid but data validation failed.

**Common causes:**
1. Invalid URL scheme (not HTTP/HTTPS)
2. Validation constraint violation
3. Type mismatch in fields

**Example Error:**
```json
{
  "detail": [
    {
      "type": "url_parsing",
      "loc": ["body", "url"],
      "msg": "Input should be a valid URL",
      "input": "not-a-url"
    }
  ]
}
```

**Resolution:**
- Ensure URL starts with `http://` or `https://`
- Verify field types match schema
- Check Pydantic model constraints

---

### 500 Internal Server Error

**Meaning:** Unexpected server error.

**Common causes:**
1. Database connection failure
2. Storage provider unavailable
3. Unhandled exception in archiver

**Example Error:**
```json
{
  "detail": "Internal server error"
}
```

**Resolution:**
- Check server logs for detailed error traces
- Verify database connectivity
- Ensure storage providers (GCS, local filesystem) are accessible
- Check system resources (disk space, memory)

---

### 503 Service Unavailable

**Meaning:** Required service component is not available.

**Common causes:**
1. Firestore backend not initialized
2. Summarization service disabled
3. Task manager not started

**Example Error:**
```json
{
  "detail": "Firestore backend is not available"
}
```

**Resolution:**
- Check service configuration
- Verify required services are enabled in settings
- Ensure all dependencies are running

---

## Archiver Exit Codes

These are archiver-specific codes returned in the `exit_code` field of responses.

### Exit Code 0 - Success
**Meaning:** Archiver completed successfully.

**Response:**
```json
{
  "ok": true,
  "exit_code": 0,
  "saved_path": "/data/article-123/readability/output.html"
}
```

**No action needed.**

---

### Exit Code 1 - General Failure
**Meaning:** Archiver encountered an unspecified error.

**Common causes:**
- Invalid HTML structure
- JavaScript execution error (for Chromium-based archivers)
- Command-line tool crashed
- Insufficient resources

**Resolution:**
1. Check archiver-specific logs
2. Verify the URL is accessible
3. Try a different archiver
4. Check system resources (CPU, memory)

**Example:**
```bash
# Retry with different archiver
curl -X POST http://localhost:8000/api/save/monolith \
  -H 'Content-Type: application/json' \
  -d '{"id": "article-123", "url": "https://example.com"}'
```

---

### Exit Code 21 - Chromium Singleton Lock
**Meaning:** Chromium detected a stale singleton lock file.

**Common causes:**
- Previous Chromium process didn't exit cleanly
- Shared `user-data-dir` across multiple processes
- Container restart without cleanup

**Resolution:**

**Option 1: Restart the service**
```bash
docker compose restart
```

**Option 2: Manual cleanup (if not using Docker)**
```bash
# Remove singleton lock files
rm -f ./data/chromium-user-data/SingletonLock
rm -f ./data/chromium-user-data/SingletonSocket
```

**Option 3: Use separate user-data-dir per archiver** (future enhancement)

**Prevention:**
- HTBase automatically cleans locks on startup
- If error persists, check file permissions on `data/chromium-user-data/`

---

### Exit Code 404 - URL Not Found
**Meaning:** Target URL returned HTTP 404 (Not Found).

**Response:**
```json
{
  "ok": false,
  "exit_code": 404,
  "saved_path": null,
  "id": "missing-article",
  "db_rowid": 45
}
```

**Common causes:**
- URL is incorrect or outdated
- Page was deleted
- Server returned 404

**Resolution:**
1. Verify the URL is correct
2. Check if the page exists by visiting in a browser
3. Look for alternative URLs (e.g., archive.org snapshot)

**Note:** HTBase proactively checks URLs before archiving. If a URL returns 404, no archiver is run and exit code 404 is recorded immediately.

---

### Exit Code 500-599 - Server Errors
**Meaning:** Target website returned a server error.

**Common causes:**
- Website is temporarily down
- Rate limiting by target server
- Server-side error on target website

**Resolution:**
1. Wait and retry later
2. Check if the website is accessible in a browser
3. Implement retry with exponential backoff

**Example retry logic:**
```python
import time
import requests

def archive_with_backoff(url, id, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(
            "http://localhost:8000/api/save/readability",
            json={"url": url, "id": id}
        )
        result = response.json()

        if result.get("exit_code") == 0:
            return result

        if result.get("exit_code", 0) >= 500:
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
            continue

        # Non-retryable error
        return result

    raise Exception("Max retries exceeded")
```

---

## Application-Specific Errors

### Error: "id is required"
**HTTP Status:** 400

**Cause:** Request missing the required `id` field.

**Fix:**
```bash
# Wrong
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'

# Correct
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "id": "example-article"}'
```

---

### Error: "Unknown archiver: xyz"
**HTTP Status:** 404

**Cause:** Requested archiver is not registered.

**Available archivers:**
- `readability`
- `monolith`
- `singlefile-cli`
- `pdf`
- `screenshot`
- `all`

**Fix:**
```bash
# Wrong
curl -X POST http://localhost:8000/api/save/invalid-archiver \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "id": "article"}'

# Correct
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "id": "article"}'
```

---

### Error: "no archivers registered"
**HTTP Status:** 500

**Cause:** Server startup failed to register any archivers.

**Resolution:**
1. Check server logs for initialization errors
2. Verify required binaries are installed:
   - Chromium/Chrome
   - SingleFile CLI
   - Monolith
3. Ensure PATH is configured correctly
4. Restart the service

---

### Error: "task manager not initialized"
**HTTP Status:** 500

**Cause:** Background task manager failed to start.

**Resolution:**
1. Check if queue.Queue initialization failed
2. Review server startup logs
3. Restart the application

---

### Error: "summarizer unavailable"
**HTTP Status:** 503

**Cause:** Summarization service is disabled or not configured.

**Resolution:**

**Option 1: Enable summarization in settings**
```bash
export SUMMARIZATION_ENABLED=true
export SUMMARIZATION_PROVIDER=huggingface
export SUMMARIZATION_BASE_URL=https://your-llm-api.com
```

**Option 2: Skip summarization**
Don't call the `/api/admin/summarize` endpoint if you don't need summaries.

---

## Troubleshooting Guide

### Problem: Archives succeed but files are empty

**Possible causes:**
- Website blocks headless browsers
- JavaScript-heavy site didn't render
- Archiver timed out prematurely

**Solutions:**
1. Try `singlefile-cli` instead of `readability`
2. Check archiver timeout settings
3. Inspect the saved file for clues

---

### Problem: Batch operations partially fail

**Behavior:**
```json
{
  "task_id": "batch-123",
  "status": "failed",
  "items": [
    {"id": "article-1", "status": "success"},
    {"id": "article-2", "status": "failed", "exit_code": 404},
    {"id": "article-3", "status": "success"}
  ]
}
```

**Resolution:**
- This is expected behavior - batch operations are partially successful
- Check individual item `exit_code` to determine why specific items failed
- Re-submit failed items individually if needed

---

### Problem: "File not found" when retrieving archive

**Possible causes:**
1. Archive operation reported success but file wasn't created
2. File was deleted after archiving
3. Storage provider issue (GCS sync failed)

**Resolution:**
1. Check database record: `sqlite3 data/htbase.db "SELECT * FROM saves WHERE item_id='your-id';"`
2. Verify file exists at `saved_path`
3. Check storage provider logs
4. Re-run archiving operation

---

### Problem: Chromium errors (exit code 21, crashes)

**Common errors:**
- "Failed to move SingletonSocket"
- Chrome exit code 21

**Resolution:**
1. Restart the service (automatic lock cleanup)
2. Ensure sufficient memory (Chromium needs 1-2GB)
3. Check disk space
4. Verify user-data-dir permissions

**Manual cleanup:**
```bash
docker compose down
rm -rf ./data/chromium-user-data/Singleton*
docker compose up -d
```

---

## Getting Help

### Check Logs
```bash
# Docker
docker compose logs -f

# Local development
tail -f logs/htbase.log
```

### Enable Debug Logging
```bash
export LOG_LEVEL=DEBUG
docker compose restart
```

### Report Issues
When reporting errors, include:
1. Full error message
2. Request that triggered the error
3. Exit code (if applicable)
4. Server logs (with DEBUG level)

---

## Quick Reference Table

| Code | Type | Meaning | Action |
|------|------|---------|--------|
| 0 | Exit | Success | None |
| 1 | Exit | General failure | Check logs, retry |
| 21 | Exit | Chromium lock | Restart service |
| 404 | Exit/HTTP | Not found | Verify URL/resource |
| 400 | HTTP | Bad request | Fix request format |
| 422 | HTTP | Validation error | Fix field values |
| 500 | HTTP | Server error | Check logs |
| 503 | HTTP | Service unavailable | Enable required service |

---

**See also:**
- [API Quickstart](API_QUICKSTART.md) - Getting started guide
- [Agent Guide](AGENT_GUIDE.md) - Best practices for AI agents
- [Architecture Documentation](REARCHITECTURE_PLAN.md) - Technical details
