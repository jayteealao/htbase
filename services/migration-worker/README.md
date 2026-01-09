# Migration Worker Service

Celery worker service for migrating data from Firestore to PostgreSQL as part of the HTBase rearchitecture.

## Overview

This service provides:

- **Resumable batch migration**: Processes Firestore documents in batches with progress tracking
- **Data validation**: Compares Firestore and PostgreSQL data for integrity
- **Rollback support**: Safely revert migration if issues are discovered
- **Progress monitoring**: Track migration status and statistics

## Architecture

### Components

- **worker.py**: Celery worker entry point
- **tasks/backfill.py**: Main migration task with resumability
- **tasks/validate.py**: Validation and integrity checking tasks
- **tasks/rollback.py**: Rollback and cleanup tasks
- **converters/firestore_to_pg.py**: Schema transformation logic

### Data Flow

```
Firestore Collection
    ↓
Batch Query (100 docs)
    ↓
FirestoreToPostgresConverter
    ↓
PostgreSQL Models (ArchivedUrl, UrlMetadata, etc.)
    ↓
Database Insert
    ↓
Progress Update
    ↓
Schedule Next Batch (if more data)
```

## Usage

### Deploy Migration Worker

```bash
# Using docker-compose with migration profile
docker compose -f docker-compose.microservices.yml --profile migration up -d migration-worker

# Check worker logs
docker logs -f htbase-migration
```

### Start Migration

```python
from shared.celery_config import celery_app

# Start migration
task = celery_app.send_task(
    'services.migration_worker.tasks.backfill_firestore_to_postgres',
    kwargs={
        'batch_size': 100,
        'collection': 'articles',
    }
)

print(f"Migration started: {task.id}")
```

### Monitor Progress

```python
# Get migration statistics
task = celery_app.send_task(
    'services.migration_worker.tasks.get_migration_stats'
)
stats = task.get(timeout=10)
print(stats)
```

```sql
-- Query progress table
SELECT * FROM migration_progress
ORDER BY started_at DESC
LIMIT 1;
```

### Validate Migration

```python
# Compare counts
task = celery_app.send_task(
    'services.migration_worker.tasks.compare_counts'
)
result = task.get(timeout=30)
print(f"Match: {result['match']}")

# Validate sample
task = celery_app.send_task(
    'services.migration_worker.tasks.validate_migration',
    kwargs={'sample_size': 100}
)
validation = task.get(timeout=60)
print(f"Validation rate: {validation['validation_rate']:.2%}")
```

### Resume Failed Migration

```python
# Resume from last checkpoint
task = celery_app.send_task(
    'services.migration_worker.tasks.resume_backfill'
)
result = task.get(timeout=10)
print(result)
```

### Rollback Migration

```python
# Hard rollback (deletes all data)
task = celery_app.send_task(
    'services.migration_worker.tasks.rollback_migration',
    kwargs={'confirm': True}
)
result = task.get(timeout=300)
print(result)
```

## Available Tasks

### Backfill Tasks

- `backfill_firestore_to_postgres`: Main migration task
  - Args: `batch_size` (default: 100), `cursor`, `collection`
  - Returns: Migration results with status and counts

- `resume_backfill`: Resume from last checkpoint
  - Args: `batch_size`, `collection`
  - Returns: Resume status

### Validation Tasks

- `compare_counts`: Compare document counts
  - Args: `collection`
  - Returns: Count comparison results

- `validate_migration`: Validate data integrity
  - Args: `collection`, `sample_size`
  - Returns: Validation results with error details

- `find_missing_records`: Find missing records
  - Args: `collection`, `limit`
  - Returns: List of missing records

- `get_migration_stats`: Get comprehensive statistics
  - Returns: Progress, counts, duration

### Rollback Tasks

- `rollback_migration`: Delete all migrated data
  - Args: `confirm` (must be True), `collection`
  - Returns: Deletion counts

- `delete_migrated_data`: Batch deletion
  - Args: `batch_size`, `dry_run`
  - Returns: Deletion results

- `pause_migration`: Pause ongoing migration
  - Args: `collection`
  - Returns: Pause status

- `reset_migration_progress`: Reset progress table
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

The migration worker is defined in `docker-compose.microservices.yml` under the `migration` profile:

```yaml
migration-worker:
  image: htbase/migration-worker:latest
  environment:
    WORKER_QUEUES: migration
    WORKER_CONCURRENCY: 1
    FIRESTORE_PROJECT_ID: ${GCS_PROJECT_ID}
  profiles:
    - migration
```

## Schema Mapping

### Firestore → PostgreSQL

| Firestore | PostgreSQL |
|-----------|------------|
| `articles/{item_id}` | `archived_urls` |
| `articles/{item_id}/metadata` | `url_metadata` |
| `articles/{item_id}/archives` | `archive_artifact` |
| `articles/{item_id}/summary` | `article_summaries` |
| `articles/{item_id}/entities` | `article_entities` |
| `articles/{item_id}/tags` | `article_tags` |

### Field Mappings

- `title` → `name` (archived_urls)
- `textContent` → `text` (url_metadata)
- `wordCount` → `word_count` (url_metadata)
- Firestore timestamps → DateTime (PostgreSQL)
- Nested maps → Separate tables with foreign keys

## Migration Progress Table

```sql
CREATE TABLE migration_progress (
    id SERIAL PRIMARY KEY,
    collection VARCHAR(100),
    last_document_id VARCHAR(255),
    documents_migrated INTEGER,
    started_at TIMESTAMP,
    updated_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50)  -- running, paused, completed, failed, rolled_back
);
```

## Error Handling

The migration task handles errors gracefully:

- **Document conversion errors**: Logged and skipped, migration continues
- **Database errors**: Transaction rolled back, document skipped
- **Task failures**: Migration can be resumed from last checkpoint
- **Worker crashes**: Progress preserved, resume when worker restarts

## Performance

### Typical Performance

- **Processing rate**: ~10-15 documents/second
- **Batch size**: 100 documents (configurable)
- **Batch processing time**: 7-10 seconds per batch
- **Example**: 10,000 documents = ~12-15 minutes

### Tuning

- Increase `batch_size` for faster migration (uses more memory)
- Decrease `batch_size` for safer, slower migration
- Monitor database connection pool usage
- Watch memory consumption

## Monitoring

### Logs

```bash
# Follow worker logs
docker logs -f htbase-migration

# Search for errors
docker logs htbase-migration 2>&1 | grep ERROR
```

### Metrics

```sql
-- Current progress
SELECT
    documents_migrated,
    status,
    EXTRACT(EPOCH FROM (NOW() - started_at)) / 60 as minutes_elapsed,
    documents_migrated / NULLIF(EXTRACT(EPOCH FROM (NOW() - started_at)) / 60, 0) as docs_per_minute
FROM migration_progress
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

### Migration Stuck

```bash
# Check worker is running
docker ps | grep migration

# Check logs for errors
docker logs htbase-migration

# Restart worker
docker compose -f docker-compose.microservices.yml restart migration-worker
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
migration-worker:
  deploy:
    resources:
      limits:
        memory: 4G  # Increase from 2G
```

## Testing

### Test in Staging

```bash
# 1. Deploy to staging environment
docker compose -f docker-compose.microservices.yml --profile migration up -d

# 2. Migrate a small sample
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task(
    'services.migration_worker.tasks.backfill_firestore_to_postgres',
    kwargs={'batch_size': 10}
)
print(task.get(timeout=60))
"

# 3. Validate results
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task('services.migration_worker.tasks.compare_counts')
print(task.get(timeout=30))
"

# 4. Test rollback
python -c "
from shared.celery_config import celery_app
task = celery_app.send_task(
    'services.migration_worker.tasks.rollback_migration',
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
python services/migration-worker/worker.py
```

### Running Tests

```bash
# Unit tests
pytest services/migration-worker/tests/

# Integration tests (requires Firestore and PostgreSQL)
pytest services/migration-worker/tests/integration/
```

## License

Part of HTBase project.
