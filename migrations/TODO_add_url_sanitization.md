# Migration: Add URL Sanitization for Logging

**Issue**: CR-NEW-8 from correctness review
**Date**: 2026-01-17
**Priority**: LOW (security/privacy, defense-in-depth)

## Overview

URLs may contain sensitive data in query parameters (API keys, tokens, passwords, session IDs). Logging raw URLs can expose these secrets in:
- Application logs
- Error tracking services (Sentry, etc.)
- Monitoring dashboards
- Log aggregation systems

A new `shared/logging_utils.py` module provides safe URL sanitization for logging.

## Security Issue

### Before: Unsafe Logging

```python
import logging

url = "https://api.example.com/data?api_key=sk-1234567890&token=eyJhbGc..."
logging.info(f"Fetching data from {url}")
# ❌ Logs: Fetching data from https://api.example.com/data?api_key=sk-1234567890&token=eyJhbGc...
# Sensitive data exposed in logs!
```

### After: Safe Logging

```python
import logging
from shared.logging_utils import sanitize_url_for_logging

url = "https://api.example.com/data?api_key=sk-1234567890&token=eyJhbGc..."
safe_url = sanitize_url_for_logging(url)
logging.info(f"Fetching data from {safe_url}")
# ✅ Logs: Fetching data from https://api.example.com/data?api_key=***REDACTED***&token=***REDACTED***
# Sensitive data protected!
```

## New Utilities

### `sanitize_url_for_logging(url, **kwargs)`

Main function for sanitizing URLs:

```python
from shared.logging_utils import sanitize_url_for_logging

# Basic usage - redacts common sensitive params
safe_url = sanitize_url_for_logging(
    "https://api.example.com?api_key=secret&foo=bar"
)
# Returns: "https://api.example.com?api_key=***REDACTED***&foo=bar"

# Add custom sensitive params
safe_url = sanitize_url_for_logging(
    "https://example.com?custom_auth=xyz",
    sensitive_params={"custom_auth"}
)
# Returns: "https://example.com?custom_auth=***REDACTED***"

# Paranoid mode - redact ALL query params
safe_url = sanitize_url_for_logging(
    "https://example.com?foo=bar&baz=qux",
    redact_all_query_params=True
)
# Returns: "https://example.com"
```

### `sanitize_error_message(message)`

Sanitizes URLs found in error messages:

```python
from shared.logging_utils import sanitize_error_message

error = "Failed to fetch https://api.example.com/data?token=secret123"
safe_error = sanitize_error_message(error)
# Returns: "Failed to fetch https://api.example.com/data?token=***REDACTED***"
```

### `safe_url(url)`

Shorthand convenience function:

```python
from shared.logging_utils import safe_url

logging.info(f"Requesting {safe_url(url)}")
```

## Default Sensitive Parameters

The following parameter names are automatically redacted (case-insensitive):

**API Keys & Tokens:**
- `api_key`, `apikey`, `api-key`
- `token`, `access_token`, `refresh_token`, `auth_token`
- `bearer`, `authorization`

**Passwords & Secrets:**
- `password`, `passwd`, `pwd`
- `secret`, `client_secret`
- `key`, `signature`, `sig`

**Session Identifiers:**
- `session`, `sessionid`, `session_id`, `sid`

**Authentication:**
- `code`, `auth_code`, `verification_code`
- `client_id`, `state`, `nonce`

See `shared/logging_utils.py:SENSITIVE_PARAMS` for the complete list.

## Where to Apply URL Sanitization

### 1. Info/Debug Logging

**Before:**
```python
logging.info(f"Archiving URL: {url}")
logging.debug(f"Fetching metadata from {source_url}")
```

**After:**
```python
from shared.logging_utils import safe_url

logging.info(f"Archiving URL: {safe_url(url)}")
logging.debug(f"Fetching metadata from {safe_url(source_url)}")
```

### 2. Error Logging

**Before:**
```python
logging.error(f"Failed to archive {url}: {error}")
```

**After:**
```python
from shared.logging_utils import safe_url

logging.error(f"Failed to archive {safe_url(url)}: {error}")
```

### 3. Exception Messages

**Before:**
```python
raise ValueError(f"Invalid response from {url}")
```

**After:**
```python
from shared.logging_utils import safe_url

raise ValueError(f"Invalid response from {safe_url(url)}")
```

### 4. HTTP Error Responses

**Before:**
```python
return JSONResponse(
    status_code=400,
    content={"error": f"Failed to fetch {url}"}
)
```

**After:**
```python
from shared.logging_utils import safe_url

return JSONResponse(
    status_code=400,
    content={"error": f"Failed to fetch {safe_url(url)}"}
)
```

### 5. Task Logging (Celery)

**Before:**
```python
@app.task
def archive_url(url: str):
    logger.info(f"Starting archive task for {url}")
```

**After:**
```python
from shared.logging_utils import safe_url

@app.task
def archive_url(url: str):
    logger.info(f"Starting archive task for {safe_url(url)}")
```

## Files to Review

Search for logging statements that include URLs:

```bash
# Find logging with URLs
rg "logging\.(info|debug|warning|error).*url" --type py

# Find f-strings with URLs
rg 'f".*{.*url.*}"' --type py

# Find exception messages with URLs
rg 'raise.*url' --type py
```

### High Priority Files:

1. **Archivers** - Log URLs frequently:
   - `services/archive-worker/app/archivers/*.py`
   - `app/archivers/*.py`

2. **API Routes** - Return error messages with URLs:
   - `services/api-gateway/app/routes/*.py`

3. **Tasks** - Log task parameters:
   - `services/*/app/tasks/*.py`

4. **Workers** - Log processing steps:
   - `services/*/worker.py`

## Testing

### Unit Tests

```python
from shared.logging_utils import sanitize_url_for_logging

def test_sanitize_url_redacts_api_key():
    url = "https://api.example.com/data?api_key=secret123"
    result = sanitize_url_for_logging(url)
    assert "secret123" not in result
    assert "api_key=***REDACTED***" in result

def test_sanitize_url_preserves_safe_params():
    url = "https://example.com?foo=bar&token=secret&baz=qux"
    result = sanitize_url_for_logging(url)
    assert "foo=bar" in result
    assert "baz=qux" in result
    assert "secret" not in result

def test_sanitize_url_strips_userinfo():
    url = "https://user:password@example.com/path"
    result = sanitize_url_for_logging(url)
    assert "user" not in result
    assert "password" not in result
    assert "example.com" in result
```

### Integration Test

```python
import logging
from shared.logging_utils import safe_url

# Configure logging to capture output
logging.basicConfig(level=logging.INFO)

# Log a URL with sensitive data
sensitive_url = "https://api.example.com?api_key=sk-secret123"
logging.info(f"Processing {safe_url(sensitive_url)}")

# Verify log output doesn't contain sensitive data
# (Check log files or use logging capture in tests)
```

## Gradual Rollout

This is a **defense-in-depth** measure. The application should already avoid logging user credentials, but this provides an extra safety layer.

**Phase 1**: Add to new code
- Use `safe_url()` in all new logging statements
- Use in new error messages

**Phase 2**: High-risk areas
- Archiver logging (processes arbitrary URLs)
- API error responses
- Task logging

**Phase 3**: Comprehensive
- Audit all logging statements
- Add to existing code gradually

## Performance Considerations

- URL parsing is fast (uses standard library `urllib.parse`)
- Minimal overhead for logging operations
- Only use when logging/returning URLs to users
- Don't use in hot paths where URL is not logged

## Alternative: Structured Logging

For maximum security, consider structured logging with separate fields:

```python
# Instead of string formatting
logging.info(f"Archiving {url}")

# Use structured logging
logging.info("Archiving URL", extra={
    "url_domain": urlparse(url).netloc,  # Safe to log
    "url_path": urlparse(url).path,      # Safe to log
    # Do NOT log query params at all
})
```

## Documentation

See `shared/logging_utils.py` for:
- Full API documentation
- Detailed examples
- Security notes
- Usage patterns

## Rationale

**Problem**: URLs may contain secrets in query parameters. Logging raw URLs can expose:
- API keys in `?api_key=...`
- OAuth tokens in `?access_token=...`
- Session IDs in `?session=...`
- Passwords in `?password=...` (poor practice but happens)

**Solution**: Automatically redact sensitive parameters while preserving URL structure for debugging.

**Benefits**:
1. **Security**: Prevents credential leaks in logs
2. **Privacy**: Protects user session tokens
3. **Compliance**: Helps with data protection requirements
4. **Defense-in-depth**: Extra safety layer
5. **Debuggability**: URL structure preserved for troubleshooting

## Implementation Status

- ✅ `shared/logging_utils.py` created with sanitization functions
- ✅ Comprehensive test examples documented
- ✅ Usage patterns documented
- ⏳ Code migration (pending - LOW priority)
- ⏳ Unit tests for sanitization functions (pending)

## Notes

- This is **LOW priority** - existing code likely doesn't log sensitive URLs maliciously
- Apply to new code immediately
- Retrofit to existing code gradually
- Consider as part of security audit or compliance review
- Particularly important if logs are sent to third-party services
