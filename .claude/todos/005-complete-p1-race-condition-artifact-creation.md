---
status: resolved
priority: p1
issue_id: "005"
tags: [code-review, data-integrity, concurrency, race-condition]
dependencies: []
---

# Race Condition on Artifact Creation

Multiple concurrent requests for the same URL create race conditions leading to unique constraint violations and API errors.

## Problem Statement

The `/save` endpoint checks for existing artifacts then creates new ones, but the check-then-create pattern is not atomic. Multiple concurrent requests for the same URL/archiver combination can pass the existence check simultaneously, then both try to create the artifact, causing unique constraint violations.

**Impact:**
- API returns 500 Internal Server Error to users
- User confusion ("why did my save fail?")
- No idempotency despite unique constraints
- Poor user experience
- Lost work (user must retry manually)

## Findings

- **Location:** `services/api-gateway/app/routes/saves.py:94-131`
- **Race condition window:**
  ```python
  # Time T1: Request A checks for artifact
  existing_artifact = db.query(ArchiveArtifact).filter(...).first()

  # Time T2: Request B checks for artifact (not yet created!)
  existing_artifact = db.query(ArchiveArtifact).filter(...).first()

  # Time T3: Request A creates artifact
  if existing_artifact:
      continue
  artifact = ArchiveArtifact(...)
  db.add(artifact)
  db.flush()  # Commits to database

  # Time T4: Request B tries to create same artifact -> UNIQUE CONSTRAINT VIOLATION!
  artifact = ArchiveArtifact(...)
  db.add(artifact)
  db.flush()  # CRASH: IntegrityError
  ```
- **Unique constraint:** `(archived_url_id, archiver)` pair in `archive_artifact` table
- **No row locking** to prevent concurrent creation
- **No upsert pattern** to handle conflicts gracefully

## Proposed Solutions

### Option 1: Row Locking with SELECT FOR UPDATE (Recommended)

**Approach:** Lock the row during existence check to prevent concurrent creation.

**Pros:**
- Prevents race condition entirely
- Industry standard pattern
- Works with PostgreSQL
- No application-level coordination needed

**Cons:**
- Serializes concurrent requests (performance impact)
- Requires transaction management

**Effort:** 2-3 hours

**Risk:** Low

**Implementation:**
```python
for archiver in archivers:
    # Lock the archived_url row to prevent concurrent artifact creation
    archived_url = db.query(ArchivedUrl).filter(
        ArchivedUrl.id == archived_url_id
    ).with_for_update().first()

    # Check for existing artifact (within locked transaction)
    existing_artifact = db.query(ArchiveArtifact).filter(
        ArchiveArtifact.archived_url_id == archived_url_id,
        ArchiveArtifact.archiver == archiver,
    ).first()

    if not existing_artifact:
        artifact = ArchiveArtifact(
            archived_url_id=archived_url_id,
            archiver=archiver,
            status="pending",
            task_id=workflow_id,
        )
        db.add(artifact)
```

---

### Option 2: Upsert with ON CONFLICT DO UPDATE

**Approach:** Use PostgreSQL upsert to handle conflicts gracefully.

**Pros:**
- Idempotent by design
- No explicit locking
- Better performance (no blocking)
- Handles race gracefully

**Cons:**
- PostgreSQL-specific syntax
- Requires raw SQL or SQLAlchemy 2.0+ dialects
- Different behavior than current code

**Effort:** 3-4 hours

**Risk:** Low

**Implementation:**
```python
from sqlalchemy.dialects.postgresql import insert

for archiver in archivers:
    # Upsert: insert or update if exists
    stmt = insert(ArchiveArtifact).values(
        archived_url_id=archived_url_id,
        archiver=archiver,
        status="pending",
        task_id=workflow_id,
    ).on_conflict_do_update(
        index_elements=["archived_url_id", "archiver"],
        set_=dict(status="pending", task_id=workflow_id)
    )
    db.execute(stmt)
```

---

### Option 3: Catch IntegrityError and Handle Gracefully

**Approach:** Let the constraint violation happen, catch the exception, and treat as success.

**Pros:**
- Minimal code changes
- Works with any database
- Simple to understand

**Cons:**
- Relies on exception handling (not ideal)
- Logs will show errors
- Transactional overhead

**Effort:** 1-2 hours

**Risk:** Medium (fragile)

**Implementation:**
```python
from sqlalchemy.exc import IntegrityError

for archiver in archivers:
    try:
        artifact = ArchiveArtifact(...)
        db.add(artifact)
        db.flush()
    except IntegrityError:
        # Already exists from concurrent request - that's okay
        db.rollback()
        logger.info(f"Artifact already exists: {archiver}")
        continue
```

## Recommended Action

**Implement Option 1 (SELECT FOR UPDATE) for correctness, consider Option 2 (Upsert) for performance optimization later.**

1. Add row locking to artifact existence check
2. Wrap artifact creation in explicit transaction
3. Add integration test for concurrent requests
4. Monitor for constraint violation errors in logs
5. Add retry logic in API client for transient failures

**Timeline:** BLOCKS MERGE - Causes API errors under concurrent load

## Technical Details

**Affected files:**
- `services/api-gateway/app/routes/saves.py:94-131` - save_url endpoint
- `services/api-gateway/app/routes/saves.py:180-250` - save_batch endpoint (similar pattern)

**Related components:**
- Database unique constraint: `UNIQUE (archived_url_id, archiver)`
- Session management needs explicit transaction handling

**Unique constraint definition:**
```sql
-- Existing constraint (from models.py)
ALTER TABLE archive_artifact
ADD CONSTRAINT uq_archived_url_archiver
UNIQUE (archived_url_id, archiver);
```

**Concurrency test:**
```python
import asyncio
import httpx

async def test_concurrent_saves():
    """Test concurrent save requests for same URL."""
    url = "https://example.com"

    async with httpx.AsyncClient() as client:
        # Submit 10 concurrent requests
        tasks = [
            client.post("/save", json={"url": url, "archivers": ["readability"]})
            for _ in range(10)
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed (idempotent)
        assert all(r.status_code in [200, 201] for r in responses)
```

## Resources

- **PR:** #6
- **PostgreSQL Row Locking:** https://www.postgresql.org/docs/current/explicit-locking.html
- **SQLAlchemy Upsert:** https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert

## Acceptance Criteria

- [ ] Row locking implemented with `SELECT ... FOR UPDATE`
- [ ] Concurrent save requests succeed without errors
- [ ] Integration test added for concurrent saves
- [ ] No IntegrityError exceptions in logs
- [ ] API returns 200 OK for duplicate requests (idempotent)
- [ ] Performance impact measured and acceptable
- [ ] Documentation updated with concurrency handling

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Data Integrity Guardian Agent)

**Actions:**
- Analyzed artifact creation flow in API Gateway
- Identified check-then-create race condition
- Evaluated failure scenarios under concurrent load
- Drafted row locking and upsert solutions

**Learnings:**
- Race window exists between existence check and creation
- Unique constraint violations cause 500 errors
- No row locking or upsert pattern in place
- Will fail under concurrent mobile app usage
- Must fix before production deployment

## Notes

- **BLOCKS MERGE** - Causes API failures under load
- Related to Issue #004 (Transaction boundaries)
- Test with load testing tool (k6, Locust) to verify fix
- Consider database connection pooling limits during high concurrency
- Monitor P95/P99 latency impact from row locking
