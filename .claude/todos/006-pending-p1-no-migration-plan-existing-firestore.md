---
status: resolved
priority: p1
issue_id: "006"
tags: [code-review, data-migration, firestore, postgresql, architecture]
dependencies: []
---

# No Data Migration Plan for Existing Firestore Data

PR introduces PostgreSQL as "source of truth" but has no migration path for existing Firestore data, risking data loss.

## Problem Statement

The rearchitecture makes PostgreSQL the primary database, but there's no migration strategy for existing production Firestore data. Deploying the new system will result in:
- PostgreSQL starts empty
- Firestore has all historical archives
- Dual writes only sync NEW data going forward
- Historical data never reaches PostgreSQL
- Queries return incomplete results

**Impact:**
- Loss of all historical archive data (months/years of work)
- Mobile apps show data backend doesn't have
- Broken API queries (no historical records)
- Business continuity failure
- Potential data loss lawsuit risk

## Findings

- **Architecture gap:** No migration code found in PR #6
- **REARCHITECTURE_PLAN.md** mentions migration strategy (lines 781-873) but no implementation
- **Dual database pattern** only handles forward sync, not backfill
- **No progress tracking** for migration
- **No rollback plan** if migration fails
- **Estimated data volume:** Unknown (could be GB+ of Firestore documents)

## Proposed Solutions

### Option 1: Parallel Backfill Worker (Recommended)

**Approach:** Create dedicated Celery worker to backfill PostgreSQL from Firestore in background.

**Pros:**
- Non-blocking deployment
- Progress tracking and resumability
- Can run alongside production traffic
- Gradual validation

**Cons:**
- Complex coordination
- Takes time (hours/days depending on data volume)
- Dual-state period (some data only in Firestore)

**Effort:** 15-20 hours

**Risk:** Medium

**Implementation:**
```python
# services/migration-worker/app/tasks.py
@celery_app.task
def backfill_firestore_to_postgres(batch_size=100, cursor=None):
    """Backfill Firestore documents to PostgreSQL."""
    firestore_db = get_firestore_client()
    postgres_db = get_postgres_session()

    # Query Firestore in batches
    query = firestore_db.collection('archived_urls').limit(batch_size)
    if cursor:
        query = query.start_after(cursor)

    docs = query.stream()
    count = 0
    last_doc = None

    for doc in docs:
        try:
            # Convert Firestore document to PostgreSQL model
            article = convert_firestore_to_postgres(doc.to_dict())

            # Check if already migrated
            existing = postgres_db.query(ArchivedUrl).filter(
                ArchivedUrl.url == article.url
            ).first()

            if not existing:
                postgres_db.add(article)
                count += 1

            last_doc = doc

        except Exception as e:
            logger.error(f"Migration failed for {doc.id}: {e}")
            # Continue with next document

    postgres_db.commit()

    # Schedule next batch if more data exists
    if count == batch_size:
        backfill_firestore_to_postgres.apply_async(
            kwargs={'cursor': last_doc},
            countdown=5
        )

    logger.info(f"Migrated {count} documents")
```

---

### Option 2: Pre-Deployment Bulk Migration Script

**Approach:** One-time script to migrate all data before deploying new system.

**Pros:**
- Simple and straightforward
- No dual-state period
- Easy to validate before cutover

**Cons:**
- Blocks deployment until migration completes
- No progress tracking (must run to completion)
- Risky for large datasets
- Downtime required

**Effort:** 10-12 hours

**Risk:** High (blocking)

---

### Option 3: Read-Through Cache Pattern

**Approach:** PostgreSQL queries fall back to Firestore for missing data, lazy migration.

**Pros:**
- No upfront migration needed
- Gradual migration on access
- Zero downtime

**Cons:**
- Complex query logic
- Performance overhead (two database checks)
- Some data never migrated (unused archives)
- Maintains dual dependency longer

**Effort:** 12-15 hours

**Risk:** Medium

## Recommended Action

**Implement Option 1 (Parallel Backfill Worker) before production deployment.**

1. Create migration worker service
2. Implement backfill task with resumability
3. Add progress tracking (Postgres table: `migration_progress`)
4. Add validation queries to compare Firestore vs PostgreSQL counts
5. Run migration in staging environment first
6. Monitor migration progress dashboard
7. Deploy new system after migration completes

**Migration Steps:**
1. Deploy migration worker
2. Start backfill task (could take hours/days)
3. Monitor progress and error rate
4. Validate data integrity (row counts, checksums)
5. Deploy new microservices system
6. Switch traffic to new API Gateway
7. Monitor for missing data errors

**Timeline:** BLOCKS MERGE - Must have migration plan before deploying

## Technical Details

**Affected components:**
- All existing Firestore data in production
- PostgreSQL database (target for migration)
- Dual database storage implementation

**Migration worker structure:**
```
services/
  migration-worker/
    ├── Dockerfile
    ├── requirements.txt
    ├── app/
    │   ├── celery_app.py
    │   ├── tasks/
    │   │   ├── backfill.py        # Main migration logic
    │   │   ├── validate.py        # Data validation
    │   │   └── rollback.py        # Rollback if needed
    │   └── converters/
    │       └── firestore_to_pg.py # Schema mapping
```

**Progress tracking table:**
```sql
CREATE TABLE migration_progress (
    id SERIAL PRIMARY KEY,
    collection VARCHAR(100),
    last_document_id VARCHAR(255),
    documents_migrated INTEGER,
    started_at TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50)  -- running, paused, completed, failed
);
```

**Validation queries:**
```sql
-- Compare counts
SELECT 'Firestore' AS source, COUNT(*) FROM firestore_count;
SELECT 'PostgreSQL' AS source, COUNT(*) FROM archived_urls;

-- Find missing records
SELECT fs.item_id
FROM firestore_snapshot fs
LEFT JOIN archived_urls pg ON fs.item_id = pg.item_id
WHERE pg.id IS NULL;
```

## Resources

- **PR:** #6
- **Firestore to SQL migration:** https://cloud.google.com/firestore/docs/manage-data/export-import
- **Data migration patterns:** https://martinfowler.com/articles/patterns-of-distributed-systems/migration.html
- **REARCHITECTURE_PLAN.md:** Lines 781-873 (migration strategy section)

## Acceptance Criteria

- [ ] Migration worker service created and deployed
- [ ] Backfill task implemented with resumability
- [ ] Progress tracking table and dashboard
- [ ] Validation queries verify data integrity
- [ ] Staging environment migration completed successfully
- [ ] Migration runbook documented
- [ ] Rollback procedure defined and tested
- [ ] Monitoring alerts for migration failures
- [ ] Estimated migration time calculated based on data volume

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Data Integrity Guardian Agent)

**Actions:**
- Reviewed REARCHITECTURE_PLAN.md for migration strategy
- Found no migration implementation in PR #6
- Analyzed dual database pattern (only handles forward sync)
- Identified risk of data loss for historical archives
- Drafted parallel backfill worker solution

**Learnings:**
- PostgreSQL is designated "source of truth" but starts empty
- Firestore contains all production data
- No backfill mechanism exists
- Historical data will be inaccessible after deployment
- Must implement migration before production cutover

## Notes

- **BLOCKS MERGE** - Risk of data loss
- Coordinate with mobile team on migration timeline
- Test migration in staging environment first
- Consider Firestore export/import tools for bulk transfer
- Document migration runbook for ops team
- Plan for migration downtime window (if needed)
- Validate data checksums after migration
