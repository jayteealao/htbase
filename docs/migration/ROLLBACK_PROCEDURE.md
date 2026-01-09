# Migration Rollback Procedure

This document describes how to safely rollback the Firestore to PostgreSQL migration if critical issues are discovered.

## When to Rollback

Consider rolling back the migration if:

- Data integrity issues are discovered (>5% validation failure rate)
- Critical data is missing or corrupted
- Performance issues impact production systems
- Application errors occur due to migrated data
- Migration cannot be completed within acceptable timeframe

## Rollback Types

### 1. Soft Rollback (Recommended)

Keep PostgreSQL data but revert application to use Firestore only. This is the safest option as it preserves all data.

**When to use:** Testing issues, application compatibility problems, or when you want to retry migration later.

### 2. Hard Rollback (Destructive)

Delete all migrated data from PostgreSQL and reset migration state. Use only if absolutely necessary.

**When to use:** Data corruption, security issues, or complete migration restart required.

## Soft Rollback Procedure

### Step 1: Disable PostgreSQL Reads

Update your application configuration to stop reading from PostgreSQL:

```bash
# In your .env or docker-compose configuration
export DATABASE_READ_ENABLED=false
export FIRESTORE_READ_ENABLED=true
```

Restart affected services:

```bash
docker compose -f docker-compose.microservices.yml restart api-gateway
```

### Step 2: Verify Application Stability

1. Check that application is reading from Firestore
2. Monitor error logs for any issues
3. Run health checks on critical endpoints
4. Verify mobile clients can access data

### Step 3: Pause Migration

Prevent any new data from being migrated:

```python
from shared.celery_config import celery_app

task = celery_app.send_task(
    'services.migration_worker.tasks.pause_migration',
    kwargs={'collection': 'articles'}
)

result = task.get(timeout=10)
print(f"Migration paused: {result}")
```

### Step 4: Stop Migration Worker

```bash
docker compose -f docker-compose.microservices.yml stop migration-worker
```

### Step 5: Document Issues

Create an incident report documenting:

- What went wrong
- When it was detected
- Impact on users/systems
- Data affected
- Steps taken
- Lessons learned

### Step 6: Plan Remediation

Analyze the issues and create a plan to:

1. Fix the root cause
2. Update migration code if needed
3. Re-test in staging environment
4. Schedule retry of migration

## Hard Rollback Procedure

**WARNING:** This procedure deletes all migrated data from PostgreSQL. Ensure you have backups and approval before proceeding.

### Step 1: Backup Current State

Before deleting anything, create backups:

```bash
# Backup PostgreSQL database
pg_dump -h localhost -U htbase -d htbase > backup_before_rollback_$(date +%Y%m%d_%H%M%S).sql

# Backup migration_progress table specifically
psql -h localhost -U htbase -d htbase -c "\copy migration_progress TO 'migration_progress_backup.csv' CSV HEADER"
```

### Step 2: Stop All Services

Stop all services that might be writing to PostgreSQL:

```bash
docker compose -f docker-compose.microservices.yml stop api-gateway
docker compose -f docker-compose.microservices.yml stop storage-worker
docker compose -f docker-compose.microservices.yml stop summarization-worker
docker compose -f docker-compose.microservices.yml stop migration-worker
```

### Step 3: Execute Rollback Task

Run the rollback task to delete all migrated data:

```python
from shared.celery_config import celery_app

# This requires explicit confirmation
task = celery_app.send_task(
    'services.migration_worker.tasks.rollback_migration',
    kwargs={
        'confirm': True,  # Must be True to execute
        'collection': 'articles'
    }
)

result = task.get(timeout=300)  # May take several minutes
print(f"Rollback result: {result}")
```

Expected output:

```python
{
    'status': 'success',
    'message': 'Migration rolled back successfully',
    'deleted_counts': {
        'archived_urls': 10000,
        'url_metadata': 9500,
        'archive_artifacts': 45000,
        'article_summaries': 8000,
        'article_entities': 15000,
        'article_tags': 12000
    }
}
```

### Step 4: Verify Deletion

Confirm all data has been deleted:

```sql
-- Should return 0 for all tables
SELECT
    (SELECT COUNT(*) FROM archived_urls) as archived_urls,
    (SELECT COUNT(*) FROM url_metadata) as url_metadata,
    (SELECT COUNT(*) FROM archive_artifact) as archive_artifacts,
    (SELECT COUNT(*) FROM article_summaries) as article_summaries,
    (SELECT COUNT(*) FROM article_entities) as article_entities,
    (SELECT COUNT(*) FROM article_tags) as article_tags;
```

### Step 5: Reset Migration Progress

Reset the migration progress table:

```python
task = celery_app.send_task(
    'services.migration_worker.tasks.reset_migration_progress',
    kwargs={
        'collection': 'articles',
        'confirm': True  # Must be True to execute
    }
)

result = task.get(timeout=10)
print(f"Progress reset: {result}")
```

Or manually:

```sql
DELETE FROM migration_progress WHERE collection = 'articles';
```

### Step 6: Restore Application Configuration

Ensure application is configured to use Firestore:

```bash
# Verify configuration
export DATABASE_READ_ENABLED=false
export FIRESTORE_READ_ENABLED=true
```

### Step 7: Restart Services

Restart all services with Firestore-only configuration:

```bash
docker compose -f docker-compose.microservices.yml up -d api-gateway
docker compose -f docker-compose.microservices.yml up -d storage-worker
docker compose -f docker-compose.microservices.yml up -d summarization-worker
```

### Step 8: Verification Testing

Run comprehensive tests:

1. **Health Checks**
   ```bash
   curl http://localhost:8080/health
   ```

2. **Data Access Tests**
   ```bash
   # Test retrieving articles
   curl http://localhost:8080/api/articles?limit=10
   ```

3. **Mobile Client Tests**
   - Test iOS app data sync
   - Test Android app data sync
   - Verify real-time updates work

4. **Archive Tests**
   - Submit new URL for archiving
   - Verify archives are created correctly
   - Check Firestore for new data

## Batch Rollback (Safer Alternative)

Instead of deleting all data at once, delete in batches:

```python
task = celery_app.send_task(
    'services.migration_worker.tasks.delete_migrated_data',
    kwargs={
        'batch_size': 1000,  # Delete 1000 records at a time
        'dry_run': False  # Set to True to test first
    }
)

result = task.get(timeout=600)
print(f"Deleted {result['deleted_count']} records")
```

Benefits:

- Less database load
- Easier to monitor
- Can stop if issues occur
- Better for large datasets

## Partial Rollback

If only specific data is problematic, you can delete selectively:

```sql
-- Example: Delete articles migrated after a specific date
DELETE FROM archived_urls
WHERE created_at > '2026-01-09 12:00:00';

-- Example: Delete articles with validation errors
DELETE FROM archived_urls
WHERE id IN (
    SELECT archived_url_id
    FROM url_metadata
    WHERE title IS NULL AND text IS NULL
);
```

## Rollback Verification Checklist

After rollback, verify:

- [ ] All PostgreSQL tables are empty (or have expected counts)
- [ ] Firestore data is intact and accessible
- [ ] Application health checks pass
- [ ] API endpoints return correct data
- [ ] Mobile clients can sync data
- [ ] New archives can be created
- [ ] No error spikes in logs
- [ ] Database performance is normal
- [ ] Migration progress table is reset
- [ ] Backups are stored safely

## Post-Rollback Actions

1. **Incident Report**
   - Document what happened
   - Root cause analysis
   - Impact assessment
   - Lessons learned

2. **Team Communication**
   - Notify stakeholders of rollback
   - Explain reasons and impact
   - Share timeline for retry (if applicable)

3. **Code Review**
   - Review migration code for issues
   - Update converter logic if needed
   - Add additional validation checks
   - Improve error handling

4. **Testing**
   - Test migration in staging environment
   - Run full validation suite
   - Load test with production-like data
   - Test rollback procedure itself

5. **Documentation**
   - Update migration runbook
   - Document known issues
   - Add troubleshooting steps
   - Update rollback procedure

## Preventing Future Rollbacks

To avoid needing rollbacks in the future:

1. **Test Thoroughly**
   - Run migration on staging data first
   - Test with production-like volume
   - Validate all data transformations
   - Test rollback procedure

2. **Monitor Closely**
   - Watch migration progress continuously
   - Set up alerts for errors
   - Monitor validation metrics
   - Check data integrity regularly

3. **Start Small**
   - Migrate a small batch first (e.g., 1000 records)
   - Validate thoroughly
   - Gradually increase batch size
   - Have clear go/no-go criteria

4. **Automate Validation**
   - Run validation checks automatically
   - Set error thresholds
   - Auto-pause on high error rate
   - Alert on validation failures

5. **Document Everything**
   - Keep detailed migration logs
   - Track metrics and statistics
   - Document all issues and resolutions
   - Create runbooks and procedures

## Emergency Contacts

In case of critical issues:

- **Database Team**: [contact info]
- **DevOps Team**: [contact info]
- **On-Call Engineer**: [contact info]
- **Technical Lead**: [contact info]

## Rollback Testing

Test rollback procedure in staging before production:

```bash
# 1. Run migration in staging
docker compose -f docker-compose.microservices.yml --profile migration up -d migration-worker

# 2. Let it migrate some data
# Wait for ~100 records to be migrated

# 3. Execute test rollback
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task(
    'services.migration_worker.tasks.rollback_migration',
    kwargs={'confirm': True, 'collection': 'articles'}
)
print(task.get(timeout=300))
"

# 4. Verify cleanup
psql -h localhost -U htbase -d htbase -c "SELECT COUNT(*) FROM archived_urls;"
# Should be 0

# 5. Verify Firestore is still accessible
python -c "
from google.cloud import firestore
db = firestore.Client()
count = sum(1 for _ in db.collection('articles').limit(10).stream())
print(f'Firestore accessible: {count} documents')
"
```

## Support

For rollback assistance:

1. Review this procedure carefully
2. Check worker logs for errors
3. Consult database team if uncertain
4. Create backup before executing
5. Test in staging first if possible

## Summary

**Soft Rollback**: Pause migration, disable PostgreSQL reads, keep data for later retry

**Hard Rollback**: Delete all migrated data, reset progress, start from scratch

**Always**: Backup first, verify thoroughly, document everything, communicate clearly
