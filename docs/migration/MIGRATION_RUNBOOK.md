# Firestore to PostgreSQL Migration Runbook

This runbook describes the process for migrating existing Firestore data to PostgreSQL as part of the HTBase rearchitecture.

## Overview

The migration worker service provides a resumable, batch-based migration from Firestore to PostgreSQL with:

- Progress tracking and resumability
- Validation and data integrity checks
- Rollback procedures
- Minimal impact on production systems

## Prerequisites

Before starting the migration:

1. **Database Migrations Applied**
   ```bash
   # Run Alembic migrations to create migration_progress table
   alembic upgrade head
   ```

2. **Firestore Credentials Configured**
   ```bash
   # Ensure GOOGLE_APPLICATION_CREDENTIALS is set
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   export GCS_PROJECT_ID=your-project-id
   ```

3. **Migration Worker Deployed**
   ```bash
   # Deploy migration worker with docker-compose
   docker compose -f docker-compose.microservices.yml --profile migration up -d migration-worker

   # Verify worker is running
   docker logs htbase-migration
   ```

4. **Backup Existing Data**
   ```bash
   # Backup PostgreSQL database
   pg_dump -h localhost -U htbase -d htbase > backup_before_migration.sql

   # Export Firestore collection (optional, as backup)
   gcloud firestore export gs://your-backup-bucket/firestore-backup
   ```

## Migration Steps

### Step 1: Pre-Migration Validation

1. **Check Firestore Document Count**
   ```python
   from google.cloud import firestore

   db = firestore.Client()
   articles = db.collection('articles').stream()
   count = sum(1 for _ in articles)
   print(f"Firestore documents to migrate: {count}")
   ```

2. **Verify PostgreSQL is Empty (if fresh migration)**
   ```sql
   SELECT COUNT(*) FROM archived_urls;
   -- Should be 0 for fresh migration, or existing count for resuming
   ```

3. **Estimate Migration Time**
   - Batch size: 100 documents per batch
   - Processing time: ~5-10 seconds per batch
   - Estimated time = (document_count / 100) * 7.5 seconds
   - Example: 10,000 documents = 100 batches × 7.5s = ~12.5 minutes

### Step 2: Start Migration

Start the migration using the Celery task:

```python
# Option 1: Via Python/API
from shared.celery_config import celery_app

task = celery_app.send_task(
    'services.migration_worker.tasks.backfill_firestore_to_postgres',
    kwargs={
        'batch_size': 100,
        'collection': 'articles',
    }
)

print(f"Migration started: task_id={task.id}")
```

```bash
# Option 2: Via Celery CLI (if flower is running)
# Access Flower at http://localhost:5555
# Navigate to "Tasks" → "Execute Task"
# Task name: services.migration_worker.tasks.backfill_firestore_to_postgres
# Args: {"batch_size": 100, "collection": "articles"}
```

### Step 3: Monitor Migration Progress

1. **Check Progress in Database**
   ```sql
   SELECT
       id,
       collection,
       documents_migrated,
       status,
       started_at,
       updated_at,
       last_document_id
   FROM migration_progress
   ORDER BY started_at DESC
   LIMIT 1;
   ```

2. **Monitor Worker Logs**
   ```bash
   docker logs -f htbase-migration
   ```

3. **Check Celery Task Status**
   ```python
   from shared.celery_config import celery_app, get_task_info

   info = get_task_info(task_id)
   print(f"Status: {info['status']}")
   print(f"Ready: {info['ready']}")
   ```

4. **Get Migration Statistics**
   ```python
   task = celery_app.send_task(
       'services.migration_worker.tasks.get_migration_stats'
   )
   stats = task.get(timeout=10)
   print(stats)
   ```

### Step 4: Validate Migration

After migration completes, validate data integrity:

1. **Compare Document Counts**
   ```python
   task = celery_app.send_task(
       'services.migration_worker.tasks.compare_counts',
       kwargs={'collection': 'articles'}
   )
   result = task.get(timeout=30)
   print(f"Firestore: {result['firestore_count']}")
   print(f"PostgreSQL: {result['postgres_count']}")
   print(f"Match: {result['match']}")
   ```

2. **Run Validation Checks**
   ```python
   task = celery_app.send_task(
       'services.migration_worker.tasks.validate_migration',
       kwargs={
           'collection': 'articles',
           'sample_size': 100  # Sample 100 random records
       }
   )
   validation = task.get(timeout=60)
   print(f"Validation rate: {validation['validation_rate']:.2%}")
   print(f"Errors: {len(validation['errors'])}")
   ```

3. **Find Missing Records**
   ```python
   task = celery_app.send_task(
       'services.migration_worker.tasks.find_missing_records',
       kwargs={
           'collection': 'articles',
           'limit': 100
       }
   )
   missing = task.get(timeout=120)
   print(f"Missing records: {missing['missing_count']}")
   ```

4. **Manual Spot Checks**
   ```sql
   -- Check a few random articles
   SELECT
       au.url,
       au.name,
       au.created_at,
       um.title,
       um.word_count,
       COUNT(aa.id) as artifact_count
   FROM archived_urls au
   LEFT JOIN url_metadata um ON um.archived_url_id = au.id
   LEFT JOIN archive_artifact aa ON aa.archived_url_id = au.id
   GROUP BY au.id, um.id
   ORDER BY RANDOM()
   LIMIT 10;
   ```

### Step 5: Post-Migration Cleanup

1. **Update Migration Status**
   ```sql
   UPDATE migration_progress
   SET status = 'completed',
       completed_at = NOW()
   WHERE collection = 'articles'
     AND status = 'running';
   ```

2. **Stop Migration Worker (if no longer needed)**
   ```bash
   docker compose -f docker-compose.microservices.yml stop migration-worker
   ```

3. **Archive Migration Logs**
   ```bash
   docker logs htbase-migration > migration_logs_$(date +%Y%m%d).txt
   ```

## Resuming a Failed Migration

If the migration fails or is interrupted:

1. **Check Current Progress**
   ```sql
   SELECT * FROM migration_progress
   WHERE collection = 'articles'
   ORDER BY started_at DESC
   LIMIT 1;
   ```

2. **Resume Migration**
   ```python
   task = celery_app.send_task(
       'services.migration_worker.tasks.resume_backfill',
       kwargs={
           'batch_size': 100,
           'collection': 'articles'
       }
   )
   ```

The migration will automatically resume from the last successfully migrated document.

## Pausing Migration

To pause an ongoing migration:

```python
task = celery_app.send_task(
    'services.migration_worker.tasks.pause_migration',
    kwargs={'collection': 'articles'}
)
```

To resume:

```python
task = celery_app.send_task(
    'services.migration_worker.tasks.resume_backfill',
    kwargs={'collection': 'articles'}
)
```

## Performance Tuning

### Adjusting Batch Size

Larger batches = faster migration but more memory usage:

```python
# Small batch (conservative, slower)
backfill_firestore_to_postgres(batch_size=50)

# Default batch (balanced)
backfill_firestore_to_postgres(batch_size=100)

# Large batch (faster, more memory)
backfill_firestore_to_postgres(batch_size=250)
```

### Worker Concurrency

Migration worker runs with concurrency=1 by default (safe):

```bash
# Increase concurrency (EXPERIMENTAL - may cause issues)
docker compose -f docker-compose.microservices.yml up -d \
  --scale migration-worker=2
```

**WARNING:** Running multiple migration workers concurrently may cause duplicate records. Use with caution.

## Troubleshooting

### Migration Stuck

If migration appears stuck:

1. Check worker logs for errors
2. Verify Firestore connection
3. Check database connection
4. Restart migration worker

```bash
docker compose -f docker-compose.microservices.yml restart migration-worker
```

### Duplicate Records

If you encounter URL uniqueness constraint errors:

```sql
-- Find duplicates
SELECT url, COUNT(*)
FROM archived_urls
GROUP BY url
HAVING COUNT(*) > 1;

-- Remove duplicates (keep oldest)
DELETE FROM archived_urls a
USING archived_urls b
WHERE a.url = b.url
  AND a.id > b.id;
```

### Memory Issues

If worker runs out of memory:

1. Reduce batch size
2. Increase worker memory limit in docker-compose
3. Check for memory leaks in logs

### Slow Migration

If migration is too slow:

1. Increase batch size (with caution)
2. Check network latency to Firestore
3. Verify PostgreSQL performance
4. Consider running migration during off-peak hours

## Migration Metrics

Track these metrics during migration:

- **Documents per minute**: documents_migrated / (time_elapsed / 60)
- **Success rate**: (documents_migrated / total_documents) × 100%
- **Error rate**: error_count / total_processed
- **Validation rate**: validated_count / sample_size

## Emergency Rollback

If critical issues are discovered, see [ROLLBACK_PROCEDURE.md](./ROLLBACK_PROCEDURE.md) for rollback instructions.

## Post-Migration Checklist

- [ ] Migration status is 'completed'
- [ ] Document counts match between Firestore and PostgreSQL
- [ ] Validation checks pass (>95% success rate)
- [ ] Spot checks confirm data integrity
- [ ] Migration logs archived
- [ ] Rollback procedure tested (in staging)
- [ ] Migration worker stopped or removed
- [ ] Team notified of completion
- [ ] Documentation updated with final metrics

## Support

For issues or questions:

1. Check worker logs: `docker logs htbase-migration`
2. Review migration progress table
3. Consult [ROLLBACK_PROCEDURE.md](./ROLLBACK_PROCEDURE.md) if needed
4. Contact the development team
