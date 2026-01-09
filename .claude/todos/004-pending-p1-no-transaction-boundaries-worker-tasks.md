---
status: resolved
priority: p1
issue_id: "004"
tags: [code-review, data-integrity, transactions, celery]
dependencies: []
---

# No Transaction Boundaries in Worker Tasks

Archive workers update database records without transaction isolation, leading to inconsistent state on failures.

## Problem Statement

Archive worker tasks (`services/archive-worker/app/tasks.py`) update artifact status in separate transactions. If archiving succeeds but the worker crashes before final status update, artifacts remain stuck in "in_progress" state forever with orphaned files.

**Impact:**
- Zombie tasks (marked in_progress but worker died)
- File/database inconsistency (file created but DB not updated)
- Resource leaks (orphaned files consuming disk space)
- Users see perpetual "processing..." status
- No automatic recovery mechanism

## Findings

- **Location:** `services/archive-worker/app/tasks.py:123-143`
- **Problematic pattern:**
  ```python
  # Transaction 1 - commits immediately
  _update_artifact_status(artifact_id, "in_progress")

  try:
      archiver = _get_archiver("singlefile")
      result = archiver.archive_with_storage(url=url, item_id=item_id)

      # Transaction 2 - if worker crashes here, status stuck "in_progress"
      _update_artifact_status(
          artifact_id,
          status="success" if result.success else "failed",
          ...
      )
  ```
- **Issue:** Each `_update_artifact_status()` commits immediately via context manager (line 75-83)
- **Context manager auto-commits** on exit (`shared/db/session.py:83-104`)
- **No rollback mechanism** for partial work
- **Zombie detection gap** - no cleanup job for stale in_progress tasks

##Proposed Solutions

### Option 1: Single Transaction Scope for Entire Task (Recommended)

**Approach:** Wrap entire task execution in a single database transaction, commit only after success.

**Pros:**
- Atomic task execution
- Automatic rollback on failure
- No orphaned database state
- Simple and correct

**Cons:**
- Requires refactoring task structure
- Long-running transactions (up to 10 minutes)
- Locks artifact row during execution

**Effort:** 4-6 hours

**Risk:** Low

**Implementation:**
```python
@celery_app.task(base=ArchiveTask, bind=True, ...)
def archive_singlefile(self, item_id, url, archived_url_id, artifact_id):
    with get_session() as session:
        # Get artifact
        artifact = session.query(ArchiveArtifact).get(artifact_id)

        # Update to in_progress (NOT committed yet)
        artifact.status = "in_progress"
        session.flush()  # Make visible to current transaction

        try:
            # Perform archiving
            archiver = _get_archiver("singlefile")
            result = archiver.archive_with_storage(url=url, item_id=item_id)

            # Update final status (NOT committed yet)
            artifact.status = "success" if result.success else "failed"
            artifact.success = result.success
            artifact.saved_path = result.saved_path
            # ... other fields

            # Commit everything atomically (on context exit)
        except Exception as e:
            # Rollback automatically on exception
            raise
```

---

### Option 2: Add Zombie Task Cleanup Job

**Approach:** Keep current pattern, add periodic cleanup for stale tasks.

**Pros:**
- Minimal code changes
- Eventually consistent
- Non-blocking

**Cons:**
- Doesn't prevent the issue
- Temporary inconsistency
- Requires monitoring

**Effort:** 3-4 hours

**Risk:** Medium

**Implementation:**
```python
@celery_app.task
def cleanup_zombie_tasks():
    """Clean up tasks stuck in in_progress for > 1 hour."""
    threshold = datetime.utcnow() - timedelta(hours=1)

    with get_session() as session:
        zombies = session.query(ArchiveArtifact).filter(
            ArchiveArtifact.status == "in_progress",
            ArchiveArtifact.updated_at < threshold
        ).all()

        for artifact in zombies:
            artifact.status = "failed"
            artifact.success = False
            # Mark for retry
```

---

### Option 3: Use Task State Table for Idempotency

**Approach:** Create separate task_state table to track execution, allowing safe retries.

**Pros:**
- Idempotent task execution
- Safe to retry
- Audit trail

**Cons:**
- Additional table complexity
- More database writes

**Effort:** 8-10 hours

**Risk:** Medium

## Recommended Action

**Implement Option 1 (Single Transaction) + Option 2 (Zombie Cleanup) for defense in depth.**

1. Refactor all archive tasks to use single transaction
2. Add `SELECT ... FOR UPDATE` row locking to prevent concurrent updates
3. Implement zombie task cleanup (runs every 15 minutes)
4. Add task heartbeat updates during long-running operations
5. Add monitoring for tasks stuck > 1 hour

**Timeline:** BLOCKS MERGE - Critical data integrity issue

## Technical Details

**Affected files:**
- `services/archive-worker/app/tasks.py:123-143` - archive_singlefile
- `services/archive-worker/app/tasks.py` - archive_monolith (similar pattern)
- `services/archive-worker/app/tasks.py` - archive_readability (similar pattern)
- `services/archive-worker/app/tasks.py` - archive_pdf (similar pattern)
- `services/archive-worker/app/tasks.py` - archive_screenshot (similar pattern)
- `shared/db/session.py:83-104` - Session context manager auto-commit

**Related components:**
- All archiver workers have same pattern
- Storage workers may have similar issues
- Summarization workers may have similar issues

**Database changes:**
```sql
-- Add task timeout tracking
ALTER TABLE archive_artifact ADD COLUMN task_started_at TIMESTAMP;
ALTER TABLE archive_artifact ADD COLUMN last_heartbeat TIMESTAMP;

-- Index for zombie detection
CREATE INDEX idx_zombie_tasks ON archive_artifact(status, updated_at)
WHERE status = 'in_progress';
```

**Monitoring queries:**
```sql
-- Find zombie tasks (stuck > 1 hour)
SELECT id, archiver, updated_at, NOW() - updated_at AS stuck_duration
FROM archive_artifact
WHERE status = 'in_progress'
  AND updated_at < NOW() - INTERVAL '1 hour'
ORDER BY updated_at;
```

## Resources

- **PR:** #6
- **Transaction patterns:** https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
- **Related Issue:** #003 (Dual write transactions)

## Acceptance Criteria

- [ ] All archive tasks refactored to single transaction
- [ ] Row locking (`SELECT ... FOR UPDATE`) implemented
- [ ] Zombie cleanup task deployed and running every 15 minutes
- [ ] Monitoring alert for tasks stuck > 1 hour
- [ ] Tests for worker crash scenarios
- [ ] Tests for concurrent task execution (race conditions)
- [ ] Documentation updated with transaction semantics

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Data Integrity Guardian Agent)

**Actions:**
- Analyzed archive worker task structure
- Identified separate transaction commits for status updates
- Found session context manager auto-commits on exit
- Discovered no zombie task detection/cleanup
- Evaluated failure scenarios (worker crash, OOM kill)

**Learnings:**
- Status updates commit immediately, causing partial state
- Worker crashes leave artifacts stuck "in_progress" forever
- No recovery mechanism exists
- Files created but database never updated (orphaned files)
- Must implement atomic transactions before production

## Notes

- **BLOCKS MERGE** - Critical data integrity issue
- Combine fix with Issue #007 (Task retry idempotency)
- Consider Celery task acknowledgment timing (`acks_late=True`)
- Test with worker kill scenarios (SIGKILL, OOM)
- Document transaction boundaries for future workers
