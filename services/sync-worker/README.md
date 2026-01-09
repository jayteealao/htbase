# Sync Worker Service

Celery worker service for syncing data from PostgreSQL to Firestore as part of the HTBase dual persistence architecture.

## Overview

This service provides:

- **Continuous data sync**: Syncs PostgreSQL data to Firestore for mobile apps
- **Data validation**: Compares PostgreSQL and Firestore data for integrity
- **Progress monitoring**: Track sync status and statistics
- **Dual persistence support**: Keeps mobile read replicas in sync with source of truth

## Architecture

### Components

- **worker.py**: Celery worker entry point
- **tasks/backfill.py**: Initial sync task with resumability
- **tasks/validate.py**: Validation and integrity checking tasks
- **tasks/rollback.py**: Rollback and cleanup tasks
- **converters/firestore_to_pg.py**: Schema transformation logic

### Data Flow

```
PostgreSQL Database (Source of Truth)
    ↓
Data Change Detected
    ↓
Convert to Firestore Schema
    ↓
Firestore Document Write
    ↓
Progress Update
    ↓
Confirmation
```

## Usage

### Deploy Sync Worker

```bash
# Using docker-compose with sync profile
docker compose -f docker-compose.microservices.yml --profile sync up -d sync-worker

# Check worker logs
docker logs -f htbase-sync
```

### Start Sync

```python
from shared.celery_config import celery_app

# Start sync
task = celery_app.send_task(
    'services.sync_worker.tasks.backfill_postgres_to_firestore',
    kwargs={
        'batch_size': 100,
        'collection': 'articles',
    }
)

print(f"Sync started: {task.id}")
```

### Monitor Progress

```python
# Get sync statistics
task = celery_app.send_task(
    'services.sync_worker.tasks.get_sync_stats'
)
stats = task.get(timeout=10)
print(stats)
```

```sql
-- Query progress table
SELECT * FROM sync_progress
ORDER BY started_at DESC
LIMIT 1;
```

### Validate Sync

```python
# Compare counts
task = celery_app.send_task(
    'services.sync_worker.tasks.compare_counts'
)
result = task.get(timeout=30)
print(f"Match: {result['match']}")

# Validate sample
task = celery_app.send_task(
    'services.sync_worker.tasks.validate_sync',
    kwargs={'sample_size': 100}
)
validation = task.get(timeout=60)
print(f"Validation rate: {validation['validation_rate']:.2%}")
```

### Resume Failed Sync

```python
# Resume from last checkpoint
task = celery_app.send_task(
    'services.sync_worker.tasks.resume_backfill'
)
result = task.get(timeout=10)
print(result)
```

### Rollback Sync

```python
# Hard rollback (deletes all data)
task = celery_app.send_task(
    'services.sync_worker.tasks.rollback_sync',
    kwargs={'confirm': True}
)
result = task.get(timeout=300)
print(result)
```

## Available Tasks

### Backfill Tasks

- `backfill_postgres_to_firestore`: Main sync task
  - Args: `batch_size` (default: 100), `cursor`, `collection`
  - Returns: Sync results with status and counts

- `resume_backfill`: Resume from last checkpoint
  - Args: `batch_size`, `collection`
  - Returns: Resume status

### Validation Tasks

- `compare_counts`: Compare document counts
  - Args: `collection`
  - Returns: Count comparison results

- `validate_sync`: Validate data integrity
  - Args: `collection`, `sample_size`
  - Returns: Validation results with error details

- `find_missing_records`: Find missing records
  - Args: `collection`, `limit`
  - Returns: List of missing records

- `get_sync_stats`: Get comprehensive statistics
  - Returns: Progress, counts, duration

### Rollback Tasks

- `rollback_sync`: Delete all synced data
  - Args: `confirm` (must be True), `collection`
  - Returns: Deletion counts

- `delete_synced_data`: Batch deletion
  - Args: `batch_size`, `dry_run`
  - Returns: Deletion results

- `pause_sync`: Pause ongoing sync
  - Args: `collection`
  - Returns: Pause status

- `reset_sync_progress`: Reset progress table
  - Args: `collection`, `confirm`
  - Returns: Reset status

## Configuration

### Environment Variables

```bash
# Firestore configuration
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs-credentials.json
FIRESTORE_PROJECT_ID=your-project-id

# Database configuration
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Celery configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# Worker configuration
WORKER_CONCURRENCY=1  # Keep at 1 to prevent duplicates
LOG_LEVEL=INFO
```

### Docker Compose

The sync worker is defined in `docker-compose.microservices.yml` under the `sync` profile:

```yaml
sync-worker:
  image: htbase/sync-worker:latest
  environment:
    WORKER_QUEUES: sync
    WORKER_CONCURRENCY: 1
    FIRESTORE_PROJECT_ID: ${GCS_PROJECT_ID}
  profiles:
    - sync
```

## Schema Mapping

### PostgreSQL → Firestore

| PostgreSQL | Firestore |
|-----------|-----------|
| `archived_urls` | `articles/{item_id}` |
| `url_metadata` | `articles/{item_id}/metadata` |
| `archive_artifact` | `articles/{item_id}/archives` |
| `article_summaries` | `articles/{item_id}/summary` |
| `article_entities` | `articles/{item_id}/entities` |
| `article_tags` | `articles/{item_id}/tags` |

### Field Mappings

- `name` → `title` (archived_urls)
- `text` → `textContent` (url_metadata)
- `word_count` → `wordCount` (url_metadata)
- DateTime → Firestore timestamps
- Separate tables with foreign keys → Nested maps

## Sync Progress Table

```sql
CREATE TABLE sync_progress (
    id SERIAL PRIMARY KEY,
    collection VARCHAR(100),
    last_document_id VARCHAR(255),
    documents_synced INTEGER,
    started_at TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50)  -- running, paused, completed, failed, rolled_back
);
```

## Error Handling

The sync task handles errors gracefully:

- **Document conversion errors**: Logged and skipped, sync continues
- **Database errors**: Transaction rolled back, document skipped
- **Task failures**: Sync can be resumed from last checkpoint
- **Worker crashes**: Progress preserved, resume when worker restarts

## Performance

### Typical Performance

- **Processing rate**: ~10-15 documents/second
- **Batch size**: 100 documents (configurable)
- **Batch processing time**: 7-10 seconds per batch
- **Example**: 10,000 documents = ~12-15 minutes

### Tuning

- Increase `batch_size` for faster sync (uses more memory)
- Decrease `batch_size` for safer, slower sync
- Monitor database connection pool usage
- Watch memory consumption

## Monitoring

### Logs

```bash
# Follow worker logs
docker logs -f htbase-sync

# Search for errors
docker logs htbase-sync 2>&1 | grep ERROR
```

### Metrics

```sql
-- Current progress
SELECT
    documents_synced,
    status,
    EXTRACT(EPOCH FROM (NOW() - started_at)) / 60 as minutes_elapsed,
    documents_synced / NULLIF(EXTRACT(EPOCH FROM (NOW() - started_at)) / 60, 0) as docs_per_minute
FROM sync_progress
WHERE collection = 'articles'
ORDER BY started_at DESC
LIMIT 1;
```

### Health Checks

```python
# Check worker status via Flower
# http://localhost:5555

# Check task queue length
from shared.celery_config import celery_app
inspect = celery_app.control.inspect()
print(inspect.active_queues())
```

## Troubleshooting

### Sync Stuck

```bash
# Check worker is running
docker ps | grep sync

# Check logs for errors
docker logs htbase-sync

# Restart worker
docker compose -f docker-compose.microservices.yml restart sync-worker
```

### Duplicate Records

```sql
-- Find duplicates
SELECT url, COUNT(*) FROM archived_urls
GROUP BY url HAVING COUNT(*) > 1;

-- Remove duplicates (keep oldest)
DELETE FROM archived_urls a
USING archived_urls b
WHERE a.url = b.url AND a.id > b.id;
```

### Out of Memory

```yaml
# Increase memory limit in docker-compose.microservices.yml
sync-worker:
  deploy:
    resources:
      limits:
        memory: 4G  # Increase from 2G
```

## Testing

### Test in Staging

```bash
# 1. Deploy to staging environment
docker compose -f docker-compose.microservices.yml --profile sync up -d

# 2. Sync a small sample
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task(
    'services.sync_worker.tasks.backfill_postgres_to_firestore',
    kwargs={'batch_size': 10}
)
print(task.get(timeout=60))
"

# 3. Validate results
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task('services.sync_worker.tasks.compare_counts')
print(task.get(timeout=30))
"

# 4. Test rollback
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task(
    'services.sync_worker.tasks.rollback_sync',
    kwargs={'confirm': True}
)
print(task.get(timeout=60))
"
```

## Documentation

For detailed procedures, see:

- [Migration Runbook](../../docs/migration/MIGRATION_RUNBOOK.md)
- [Rollback Procedure](../../docs/migration/ROLLBACK_PROCEDURE.md)

## Dependencies

- `firebase-admin`: Firestore access
- `celery`: Task queue
- `sqlalchemy`: PostgreSQL ORM
- `psycopg`: PostgreSQL driver
- `redis`: Celery broker

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.microservices.txt
pip install firebase-admin

# Set environment variables
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
export DATABASE_URL=postgresql://localhost/htbase

# Run worker
python services/sync-worker/worker.py
```

### Running Tests

```bash
# Unit tests
pytest services/sync-worker/tests/

# Integration tests (requires Firestore and PostgreSQL)
pytest services/sync-worker/tests/integration/
```

## License

Part of HTBase project.
