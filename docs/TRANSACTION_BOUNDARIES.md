# Archive Worker Transaction Boundaries

## Overview

Archive workers now use single-transaction execution to prevent zombie tasks and ensure data integrity. This document explains the transaction model and best practices.

## Problem Statement

### Previous Implementation (Broken)

```python
# Transaction 1 - commits immediately
_update_artifact_status(artifact_id, "in_progress")

try:
    archiver = _get_archiver("singlefile")
    result = archiver.archive_with_storage(url=url, item_id=item_id)

    # Transaction 2 - if worker crashes here, status stuck "in_progress"
    _update_artifact_status(artifact_id, "success" if result.success else "failed")
```

**Issues:**
- Each `_update_artifact_status()` commits immediately via context manager
- If worker crashes between transactions, artifact stuck in `in_progress` forever
- No automatic rollback on failure
- Creates "zombie tasks" that never complete

### Impact

1. **Zombie tasks** - Artifacts marked `in_progress` but worker died
2. **File/database inconsistency** - File created but DB not updated
3. **Resource leaks** - Orphaned files consuming disk space
4. **User experience** - Perpetual "processing..." status
5. **No recovery** - Manual intervention required

## Solution

### Single Transaction Scope (Option 1)

**All archive tasks now execute within a single database transaction:**

```python
with get_session() as session:
    # Step 1: Lock artifact row
    artifact = session.execute(
        select(ArchiveArtifact)
        .where(ArchiveArtifact.id == artifact_id)
        .with_for_update()  # Row-level lock
    ).scalar_one_or_none()

    # Step 2: Update to in_progress (NOT committed yet)
    artifact.status = "in_progress"
    artifact.task_started_at = datetime.utcnow()
    artifact.last_heartbeat = datetime.utcnow()
    session.flush()  # Make visible to current transaction

    # Step 3: Perform archiving
    archiver = _get_archiver(archiver_name)
    result = archiver.archive_with_storage(url=url, item_id=item_id)

    # Step 4: Update final status (NOT committed yet)
    artifact.status = "success" if result.success else "failed"
    artifact.success = result.success
    artifact.exit_code = result.exit_code
    artifact.saved_path = result.saved_path
    artifact.size_bytes = size_bytes

    # Step 5: Commit everything atomically (on context exit)
```

**Benefits:**
- Atomic execution - all changes committed together
- Automatic rollback on exception
- No partial state in database
- Worker crash = transaction rolled back, artifact stays `pending`

### Zombie Task Cleanup (Option 2)

**Periodic cleanup job detects and fails stale tasks:**

```python
@celery_app.task(name="services.archive_worker.tasks.cleanup_zombie_tasks")
def cleanup_zombie_tasks() -> dict:
    """Clean up tasks stuck in in_progress for > 1 hour."""
    threshold = datetime.utcnow() - timedelta(hours=1)

    with get_session() as session:
        zombies = session.execute(
            select(ArchiveArtifact)
            .where(
                ArchiveArtifact.status == "in_progress",
                ArchiveArtifact.updated_at < threshold,
            )
            .with_for_update()
        ).scalars().all()

        for artifact in zombies:
            artifact.status = "failed"
            artifact.success = False
            artifact.updated_at = datetime.utcnow()
```

**Runs every 15 minutes via Celery Beat.**

## Implementation Details

### Database Schema Changes

**New columns for zombie detection:**

```sql
ALTER TABLE archive_artifact ADD COLUMN task_started_at TIMESTAMP;
ALTER TABLE archive_artifact ADD COLUMN last_heartbeat TIMESTAMP;

-- Partial index for efficient zombie detection
CREATE INDEX idx_zombie_tasks ON archive_artifact(status, updated_at)
WHERE status = 'in_progress';
```

### Row Locking with SELECT FOR UPDATE

All archive tasks use `SELECT ... FOR UPDATE` to prevent concurrent updates:

```python
artifact = session.execute(
    select(ArchiveArtifact)
    .where(ArchiveArtifact.id == artifact_id)
    .with_for_update()  # Exclusive lock until transaction commits
).scalar_one_or_none()
```

**Benefits:**
- Prevents race conditions
- Serializes concurrent requests for same artifact
- Ensures only one worker processes artifact at a time

### Transaction Lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│ Single Database Transaction                                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. BEGIN TRANSACTION                                        │
│  2. SELECT ... FOR UPDATE (acquire row lock)                 │
│  3. UPDATE status = 'in_progress' + FLUSH                    │
│  4. Perform archiving (external operation)                   │
│  5. UPDATE status = 'success'/'failed'                       │
│  6. COMMIT (releases lock, makes all changes visible)        │
│                                                              │
│  Exception → ROLLBACK (no changes committed)                 │
└──────────────────────────────────────────────────────────────┘
```

## Affected Files

### Modified Files

1. **`services/archive-worker/app/tasks.py`**
   - Added `_execute_archive_task()` helper for single-transaction execution
   - Refactored all archive tasks to use single transaction
   - Added `cleanup_zombie_tasks()` periodic task
   - Updated docstrings to document transaction semantics

2. **`shared/db/models.py`**
   - Added `task_started_at` column to `ArchiveArtifact`
   - Added `last_heartbeat` column to `ArchiveArtifact`

3. **`shared/celery_config.py`**
   - Added `cleanup-zombie-tasks` to beat schedule (runs every 15 minutes)

### New Files

1. **`alembic/versions/0006_add_task_tracking_columns.py`**
   - Database migration for task tracking columns
   - Creates partial index for zombie detection

2. **`tests/unit/test_archive_transactions.py`**
   - Comprehensive tests for transaction boundaries
   - Tests for rollback on worker crash
   - Tests for zombie task cleanup
   - Tests for concurrent execution prevention

## Testing

### Run Transaction Tests

```bash
pytest tests/unit/test_archive_transactions.py -v
```

### Test Coverage

1. **Single transaction commit on success**
   - Verifies all changes committed atomically
   - Checks `task_started_at` and `last_heartbeat` set

2. **Single transaction rollback on failure**
   - Simulates worker crash (exception during archiving)
   - Verifies artifact remains in `pending` state
   - No partial state committed

3. **Row locking prevents concurrent updates**
   - Tests `SELECT FOR UPDATE` serializes concurrent requests
   - Prevents race conditions

4. **Zombie task cleanup**
   - Creates old `in_progress` task (> 1 hour)
   - Runs cleanup job
   - Verifies task marked as `failed`

5. **Zombie cleanup ignores recent tasks**
   - Creates recent `in_progress` task (< 1 hour)
   - Runs cleanup job
   - Verifies task unchanged

6. **All archivers use transactions**
   - Tests all 5 archiver tasks (singlefile, monolith, readability, pdf, screenshot)
   - Verifies consistent transaction pattern

### Manual Testing

**Simulate worker crash:**

```python
# Add this to archiver code to simulate crash
import time
time.sleep(2)
raise RuntimeError("Simulated worker crash")
```

**Expected behavior:**
- Transaction rolled back
- Artifact remains in `pending` state
- Zombie cleanup fails task after 1 hour

## Monitoring

### Zombie Task Queries

**Find current zombie tasks:**

```sql
SELECT
    id,
    archiver,
    task_started_at,
    last_heartbeat,
    NOW() - updated_at AS stuck_duration
FROM archive_artifact
WHERE status = 'in_progress'
    AND updated_at < NOW() - INTERVAL '1 hour'
ORDER BY updated_at;
```

**Zombie cleanup metrics:**

```sql
-- Failed by zombie cleanup (last 24 hours)
SELECT COUNT(*)
FROM archive_artifact
WHERE status = 'failed'
    AND success = false
    AND updated_at > NOW() - INTERVAL '24 hours'
    AND task_started_at < updated_at - INTERVAL '1 hour';
```

### Celery Beat Logs

**Monitor zombie cleanup execution:**

```bash
# Check Celery Beat logs for cleanup runs
grep "cleanup_zombie_tasks" celery-beat.log

# Expected output every 15 minutes:
# [INFO] Starting zombie task cleanup
# [WARNING] Found N zombie tasks
# [INFO] Zombie task cleanup completed
```

## Best Practices

### Writing New Archive Tasks

**Always follow this pattern:**

```python
@celery_app.task(base=ArchiveTask, bind=True)
def archive_new_format(self, item_id, url, archived_url_id, artifact_id):
    """Archive URL using new format."""

    # Execute within single transaction
    with get_session() as session:
        result = _execute_archive_task(
            session=session,
            artifact_id=artifact_id,
            archiver_name="new_format",
            url=url,
            item_id=item_id,
            task_id=self.request.id,
        )

    return result
```

### Transaction Timeout Considerations

**Long-running archivers:**
- Current timeout: 10 minutes (hard limit)
- Transaction held for entire duration
- Row locked during execution
- Consider breaking into smaller operations if > 10 minutes

**Database connection pool:**
- Default pool size: 5 connections
- Max overflow: 10 connections
- Pool timeout: 30 seconds
- Long transactions can exhaust pool

### Heartbeat Updates (Future Enhancement)

**For very long operations (> 5 minutes):**

```python
# Periodically update heartbeat within transaction
artifact.last_heartbeat = datetime.utcnow()
session.flush()
```

**Adjust zombie threshold:**
- Tasks updating heartbeat can run longer
- Zombie detection uses `last_heartbeat` instead of `updated_at`

## Failure Scenarios

### Scenario 1: Worker Crash During Archiving

**Before fix:**
```
1. Status → in_progress (committed)
2. Archiver creates file
3. WORKER CRASHES
4. Status stuck "in_progress" forever
5. File orphaned, never uploaded
```

**After fix:**
```
1. BEGIN TRANSACTION
2. Status → in_progress (NOT committed)
3. Archiver creates file
4. WORKER CRASHES
5. TRANSACTION ROLLED BACK
6. Status → pending (never changed)
7. Zombie cleanup eventually fails task after 1 hour
```

### Scenario 2: Database Connection Lost

**Before fix:**
- Partial state committed
- Status update fails silently
- File created but DB not updated

**After fix:**
- Transaction rolled back automatically
- No partial state
- Artifact remains `pending` for retry

### Scenario 3: Out of Memory Kill

**Before fix:**
- Worker killed mid-operation
- Status committed as `in_progress`
- Never recovers

**After fix:**
- Transaction rolled back
- Status reverts to `pending`
- Celery retries task (acks_late=True)

## Performance Considerations

### Transaction Duration

**Typical archive operations:**
- SingleFile: 10-30 seconds
- Monolith: 5-15 seconds
- PDF: 15-45 seconds
- Screenshot: 10-20 seconds
- Readability: 1-5 seconds

**Database impact:**
- Row lock held for entire duration
- Concurrent requests for same artifact wait
- Different artifacts process in parallel

### Index Performance

**Partial index for zombie detection:**

```sql
CREATE INDEX idx_zombie_tasks ON archive_artifact(status, updated_at)
WHERE status = 'in_progress';
```

**Benefits:**
- Index only includes `in_progress` rows
- Zombie cleanup query extremely fast
- Minimal storage overhead

## Migration Guide

### Applying the Migration

```bash
# Review migration
alembic history
alembic show 0006_add_task_tracking_columns

# Apply migration
alembic upgrade head

# Verify columns added
psql -c "\d archive_artifact"
```

### Rollback (if needed)

```bash
# Downgrade to previous version
alembic downgrade 0005_add_multi_provider_tracking

# Verify columns removed
psql -c "\d archive_artifact"
```

## Related Issues

- **Issue #003** - Dual write transaction boundaries (similar pattern)
- **Issue #007** - Task retry idempotency (depends on this fix)

## References

- [SQLAlchemy Transaction Documentation](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [PostgreSQL SELECT FOR UPDATE](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE)
- [Celery Task Acknowledgment](https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-acks-late)
