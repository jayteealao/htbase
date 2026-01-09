---
status: pending
priority: p1
issue_id: "003"
tags: [code-review, data-integrity, distributed-transactions, dual-database]
dependencies: []
---

# Dual Write Without Distributed Transactions

Dual database writes to PostgreSQL + Firestore lack distributed transaction coordination, leading to data inconsistency.

## Problem Statement

The `DualDatabaseStorage` class performs sequential writes to PostgreSQL then Firestore without atomic transaction guarantees. If PostgreSQL succeeds but Firestore fails, data diverges between the two databases permanently.

**Impact:**
- Mobile apps (Firestore) show incomplete/stale data
- PostgreSQL has truth, Firestore has gaps
- No automatic reconciliation mechanism
- Manual cleanup required for drift
- User confusion from inconsistent state

## Findings

- **Location:** `shared/storage/dual_database_storage.py:90-114`
- **Vulnerable pattern:**
  ```python
  # Step 1: Write to PostgreSQL (commits immediately)
  pg_success = self.postgres.create_article(metadata)
  if not pg_success:
      return False  # PostgreSQL is source of truth - fail immediately

  # Step 2: Write to Firestore (if this fails, data already in PostgreSQL!)
  fs_success = self.firestore.create_article(metadata)
  ```
- **Failure modes:**
  - `fail_fast` mode: Entire operation fails AFTER PostgreSQL commit (line 51)
  - `log_and_continue` mode: Divergence accumulates silently (line 619-621)
  - `queue_retry` mode: Not implemented (TODO comment line 625)
- **Affected operations:** All CRUD operations (create, update, delete, batch)
- **No drift detection** or reconciliation worker exists

## Proposed Solutions

### Option 1: Implement Saga Pattern with Compensating Transactions (Recommended)

**Approach:** Use Saga pattern to handle distributed transactions with explicit compensation logic.

**Pros:**
- Industry-standard for microservices
- Explicit failure handling
- Can implement retry logic
- Preserves eventual consistency

**Cons:**
- Requires compensation logic for each operation
- More complex than simple transactions
- Eventual consistency delay

**Effort:** 12-15 hours

**Risk:** Medium

**Implementation:**
```python
class DualDatabaseStorage:
    def create_article(self, metadata: ArticleMetadata) -> bool:
        # Step 1: Write to PostgreSQL
        pg_id = self.postgres.create_article(metadata)
        if not pg_id:
            return False

        # Step 2: Write to Firestore with compensation
        try:
            fs_success = self.firestore.create_article(metadata)
            if not fs_success:
                # Compensate: Rollback PostgreSQL write
                self.postgres.delete_article(metadata.item_id)
                return False
        except Exception as e:
            # Compensate: Rollback PostgreSQL write
            self.postgres.delete_article(metadata.item_id)
            raise

        return True
```

---

### Option 2: Two-Phase Commit (2PC) Protocol

**Approach:** Implement explicit two-phase commit across both databases.

**Pros:**
- Strongest consistency guarantee
- Atomic commit or rollback
- No data drift

**Cons:**
- Firestore doesn't natively support 2PC prepare/commit phases
- High complexity
- Performance overhead (multiple round trips)
- Blocking protocol (availability impact)

**Effort:** 20-25 hours

**Risk:** High

---

### Option 3: Eventual Consistency with Reconciliation Worker

**Approach:** Accept eventual consistency, add reconciliation worker to detect and fix drift.

**Pros:**
- Simplest to implement
- Non-blocking writes
- Resilient to Firestore outages
- Matches microservices patterns

**Cons:**
- Temporary data inconsistency
- Requires reconciliation logic
- Monitoring complexity

**Effort:** 8-10 hours

**Risk:** Low

**Implementation:**
```python
# New Celery task
@celery_app.task
def reconcile_dual_database():
    """Detect and fix PostgreSQL <-> Firestore drift."""
    # Find items in PostgreSQL not in Firestore
    missing_in_fs = detect_drift()

    for item in missing_in_fs:
        try:
            firestore.create_article(item)
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")

    # Schedule next reconciliation
    reconcile_dual_database.apply_async(countdown=300)  # Every 5 mins
```

---

### Option 4: Change Data Capture (CDC) for Sync

**Approach:** Use PostgreSQL CDC (logical replication) to stream changes to Firestore.

**Pros:**
- PostgreSQL remains source of truth
- Automatic synchronization
- No application-level sync logic
- Industry-standard pattern

**Cons:**
- Requires CDC infrastructure (Debezium, etc.)
- Operational complexity
- Learning curve

**Effort:** 15-20 hours

**Risk:** Medium

## Recommended Action

**Implement Option 3 (Eventual Consistency + Reconciliation) for short-term fix, plan Option 4 (CDC) for long-term solution.**

1. Add `last_synced_at` timestamp to track sync status
2. Implement reconciliation Celery task (runs every 5 minutes)
3. Add drift detection monitoring/alerting
4. Change failure mode to `log_and_continue` by default
5. Document eventual consistency behavior for clients

**Timeline:** BLOCKS MERGE - Data consistency is critical

## Technical Details

**Affected files:**
- `shared/storage/dual_database_storage.py:90-114` - create_article
- `shared/storage/dual_database_storage.py:140-180` - update_article_metadata
- `shared/storage/dual_database_storage.py:182-214` - delete_article
- `shared/storage/dual_database_storage.py:237-273` - create_artifact
- `shared/storage/dual_database_storage.py:488-515` - batch operations

**Related components:**
- PostgreSQL models need `last_synced_at` column
- Firestore documents need `synced_from_postgres` flag
- Monitoring dashboard for drift metrics

**Database schema changes:**
```sql
-- Add sync tracking
ALTER TABLE archived_urls ADD COLUMN last_synced_to_firestore TIMESTAMP;
ALTER TABLE archive_artifact ADD COLUMN last_synced_to_firestore TIMESTAMP;

-- Index for reconciliation queries
CREATE INDEX idx_sync_status ON archived_urls(last_synced_to_firestore);
```

## Resources

- **PR:** #6
- **Saga Pattern:** https://microservices.io/patterns/data/saga.html
- **CDC with Debezium:** https://debezium.io/
- **Eventual Consistency:** https://martinfowler.com/articles/microservices.html

## Acceptance Criteria

- [ ] Compensation logic implemented for failed Firestore writes
- [ ] Reconciliation worker deployed and running every 5 minutes
- [ ] Drift detection monitoring in place
- [ ] `last_synced_at` timestamp added to database schema
- [ ] Alerts configured for sync lag > 10 minutes
- [ ] Tests for failure scenarios (Firestore down, partial failures)
- [ ] Documentation updated with consistency guarantees

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Data Integrity Guardian Agent)

**Actions:**
- Analyzed DualDatabaseStorage implementation
- Identified lack of distributed transaction coordination
- Evaluated failure modes (fail_fast, log_and_continue)
- Found no drift detection or reconciliation mechanism
- Drafted Saga and CDC-based solutions

**Learnings:**
- PostgreSQL commits happen before Firestore writes
- Failures leave data in inconsistent state
- Mobile clients will see incomplete/stale data
- No automatic recovery from drift
- Must implement reconciliation before production deployment

## Notes

- **BLOCKS MERGE** - Critical data integrity issue
- Consider Google Spanner as unified database alternative (eliminates dual-write problem)
- Monitor Firestore error rates to detect systemic issues
- Plan for Firestore outages (fallback to PostgreSQL-only mode?)
- Document eventual consistency SLAs for mobile team
