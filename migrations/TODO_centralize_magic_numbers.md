# Migration: Centralize Magic Numbers to Configuration

**Issue**: CR-NEW-7 from correctness review
**Date**: 2026-01-17
**Priority**: LOW (code quality, maintainability)

## Overview

Hardcoded timeout values, retry counts, and other numeric constants have been centralized in `shared/config.py` to improve maintainability and allow runtime configuration via environment variables.

## New Configuration Classes

Added to `shared/config.py`:

1. **ArchiverSettings** - Timeout values for each archiver type
2. **TaskSettings** - Celery task retry configuration
3. **HTTPSettings** - HTTP client timeout settings
4. **BatchSettings** - Batch processing limits

## Migration Examples

### Before: Hardcoded Timeouts

```python
# services/archive-worker/app/archivers/singlefile.py
result = self.run_command(
    cmd,
    timeout=300.0,  # ❌ Hardcoded magic number
)
```

### After: Configuration-Based

```python
# services/archive-worker/app/archivers/singlefile.py
from shared.config import get_settings

settings = get_settings()

result = self.run_command(
    cmd,
    timeout=settings.archivers.singlefile_timeout,  # ✅ Configurable
)
```

## Files to Update

### Archiver Timeouts

Replace hardcoded timeouts with `settings.archivers.*_timeout`:

- `services/archive-worker/app/archivers/singlefile.py` - Use `singlefile_timeout`
- `services/archive-worker/app/archivers/monolith.py` - Use `monolith_timeout`
- `services/archive-worker/app/archivers/pdf.py` - Use `pdf_timeout`
- `services/archive-worker/app/archivers/screenshot.py` - Use `screenshot_timeout`
- `services/archive-worker/app/archivers/readability.py` - Use `readability_timeout`

### Task Retry Configuration

Replace hardcoded retry values with `settings.tasks.*`:

- `services/archive-worker/app/tasks.py`:
  ```python
  # Before
  retry_backoff_max = 300
  max_retries = 3

  # After
  from shared.config import get_settings
  settings = get_settings()
  retry_backoff_max = settings.tasks.retry_backoff_max
  max_retries = settings.tasks.max_retries
  ```

- `services/storage-worker/app/tasks.py`:
  ```python
  # Before
  max_retries = 5

  # After
  max_retries = settings.tasks.storage_max_retries
  ```

- `services/archive-worker/app/tasks/webhooks.py`:
  ```python
  # Before
  retry_backoff_max = 600
  max_retries = 5
  default_retry_delay = 60

  # After
  retry_backoff_max = settings.tasks.webhook_retry_backoff_max
  max_retries = settings.tasks.webhook_max_retries
  default_retry_delay = settings.tasks.webhook_retry_delay
  ```

### HTTP Timeouts

Replace hardcoded HTTP timeouts with `settings.http.*`:

- `shared/summarization/providers.py`:
  ```python
  # Before
  async with httpx.AsyncClient(timeout=10) as client:

  # After
  async with httpx.AsyncClient(timeout=settings.http.health_check_timeout) as client:
  ```

- `services/archive-worker/app/tasks/webhooks.py`:
  ```python
  # Before
  timeout=10.0

  # After
  timeout=settings.http.webhook_timeout
  ```

### Batch Limits

Replace hardcoded batch sizes with `settings.batch.*`:

- `services/api-gateway/app/routes/archives.py`:
  ```python
  # Before
  items: List[ArchiveItem] = Field(..., max_items=100)

  # After
  from shared.config import get_settings
  settings = get_settings()
  items: List[ArchiveItem] = Field(..., max_items=settings.batch.max_batch_size)
  ```

- `app/task_manager/archiver.py`:
  ```python
  # Before
  DEFAULT_REQUEUE_CHUNK_SIZE = 10

  # After
  from shared.config import get_settings
  settings = get_settings()
  DEFAULT_REQUEUE_CHUNK_SIZE = settings.batch.requeue_chunk_size
  ```

- `services/sync-worker/worker.py`:
  ```python
  # Before
  "--max-tasks-per-child=10"

  # After
  f"--max-tasks-per-child={settings.batch.worker_max_tasks_per_child}"
  ```

## Environment Variable Configuration

All settings can now be configured via environment variables:

```bash
# Archiver timeouts (seconds)
ARCHIVER_SINGLEFILE_TIMEOUT=300.0
ARCHIVER_MONOLITH_TIMEOUT=300.0
ARCHIVER_PDF_TIMEOUT=120.0
ARCHIVER_SCREENSHOT_TIMEOUT=60.0
ARCHIVER_READABILITY_TIMEOUT=30.0

# Task retry configuration
TASK_DEFAULT_RETRY_DELAY=60
TASK_MAX_RETRIES=3
TASK_RETRY_BACKOFF_MAX=300
TASK_WEBHOOK_RETRY_DELAY=60
TASK_WEBHOOK_MAX_RETRIES=5
TASK_WEBHOOK_RETRY_BACKOFF_MAX=600
TASK_STORAGE_MAX_RETRIES=5

# HTTP timeouts (seconds)
HTTP_DEFAULT_TIMEOUT=30.0
HTTP_HEALTH_CHECK_TIMEOUT=10.0
HTTP_WEBHOOK_TIMEOUT=10.0

# Batch processing limits
BATCH_MAX_SIZE=100
BATCH_REQUEUE_CHUNK_SIZE=10
WORKER_MAX_TASKS_PER_CHILD=10
```

## Benefits

1. **Tunability**: Operators can adjust timeouts without code changes
2. **Environment-Specific**: Different values for dev/staging/production
3. **Discoverability**: All configuration in one place
4. **Type Safety**: Pydantic validation with helpful error messages
5. **Documentation**: Field descriptions explain purpose of each setting

## Testing

After migration, verify settings are loaded correctly:

```python
from shared.config import get_settings

settings = get_settings()

# Check archiver timeouts
assert settings.archivers.singlefile_timeout == 300.0
assert settings.archivers.pdf_timeout == 120.0

# Check task configuration
assert settings.tasks.max_retries == 3
assert settings.tasks.retry_backoff_max == 300

# Check HTTP timeouts
assert settings.http.default_timeout == 30.0

# Check batch limits
assert settings.batch.max_batch_size == 100
```

## Rationale

**Before**: Configuration scattered across 15+ files, difficult to tune performance, no environment-specific values.

**After**: Centralized configuration, environment-based tuning, type-safe validation, single source of truth.

This follows the principle of "configuration as data" and makes operational tuning significantly easier.

## Implementation Status

- ✅ Configuration classes added to `shared/config.py`
- ✅ Pydantic validation with helpful error messages
- ✅ Environment variable support with aliases
- ⏳ Code migration to use new settings (pending)
- ⏳ Testing to verify settings load correctly (pending)

## Notes

- This is a **LOW priority** refactoring - existing code works correctly
- Migration can be done incrementally, file by file
- No breaking changes - defaults match current hardcoded values
- Consider this for next maintenance cycle or when tuning performance
