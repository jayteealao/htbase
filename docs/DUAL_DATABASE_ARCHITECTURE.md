# Dual Database Architecture

This document explains the dual database storage pattern used in HTBase, where PostgreSQL serves as the primary source of truth and Firestore acts as a mobile-optimized read replica.

## Overview

**Pattern:** Write-Through Dual Database with Selective Replication
**Primary:** PostgreSQL (ACID, full data)
**Replica:** Firestore (NoSQL, filtered data for mobile)
**Sync Direction:** One-way (PostgreSQL → Firestore)
**Consistency Model:** Strong (PostgreSQL), Eventual (Firestore)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    API Request                              │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│           DualDatabaseStorage (Orchestrator)                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  1. Write to PostgreSQL (PRIMARY - REQUIRED)        │  │
│  │     ├─ ArchivedUrl                                  │  │
│  │     ├─ UrlMetadata                                  │  │
│  │     ├─ ArchiveArtifact                              │  │
│  │     ├─ ArticleSummary                               │  │
│  │     ├─ ArticleEntity                                │  │
│  │     └─ ArticleTag                                   │  │
│  │     └─ COMMIT (must succeed)                        │  │
│  └─────────────────────────────────────────────────────┘  │
│                        │                                    │
│                        ▼                                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  2. Filter Data (sync_filter.py)                    │  │
│  │     ├─ Remove large fields (text_content)           │  │
│  │     ├─ Remove internal fields (exit_code, errors)   │  │
│  │     └─ Keep mobile-relevant fields only             │  │
│  └─────────────────────────────────────────────────────┘  │
│                        │                                    │
│                        ▼                                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  3. Write to Firestore (REPLICA - BEST EFFORT)     │  │
│  │     └─ articles/{item_id}                           │  │
│  │        ├─ metadata (filtered)                       │  │
│  │        ├─ archives (status map)                     │  │
│  │        └─ pocket (if present)                       │  │
│  └─────────────────────────────────────────────────────┘  │
│                        │                                    │
│                        ▼                                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  4. Handle Firestore Failure                        │  │
│  │     ├─ fail_fast: Rollback PostgreSQL, return error │  │
│  │     ├─ log_and_continue: Log warning, continue      │  │
│  │     └─ queue_retry: Queue for retry (NOT IMPL)      │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### Core Orchestrator

**File:** `shared/storage/dual_database_storage.py`

```python
class DualDatabaseStorage(DatabaseStorageProvider):
    """Orchestrates writes to both PostgreSQL and Firestore."""

    def __init__(
        self,
        postgres: PostgresStorage,
        firestore: Optional[FirestoreStorage] = None,
        failure_mode: str = "log_and_continue"
    ):
        self.postgres = postgres  # Primary (required)
        self.firestore = firestore  # Replica (optional)
        self.failure_mode = failure_mode

    def create_article(self, metadata: ArticleMetadata) -> bool:
        # Step 1: Write to PostgreSQL (REQUIRED)
        pg_success = self.postgres.create_article(metadata)
        if not pg_success:
            return False  # Fail immediately if PostgreSQL fails

        # Step 2: Write to Firestore (OPTIONAL)
        if self.firestore:
            try:
                # Filter data for mobile
                filtered = sync_filter.filter_article_metadata(metadata)

                # Write to Firestore
                fs_success = self.firestore.create_article(filtered)

                if not fs_success:
                    return self._handle_firestore_failure(
                        operation="create_article",
                        item_id=metadata.item_id
                    )
            except Exception as e:
                return self._handle_firestore_failure(
                    operation="create_article",
                    item_id=metadata.item_id,
                    error=e
                )

        return True

    def _handle_firestore_failure(
        self,
        operation: str,
        item_id: str,
        error: Optional[Exception] = None
    ) -> bool:
        """Handle Firestore write failure based on configured mode."""
        if self.failure_mode == "fail_fast":
            logger.error(f"Firestore {operation} failed for {item_id}: {error}")
            return False

        elif self.failure_mode == "log_and_continue":
            logger.warning(f"Firestore {operation} failed for {item_id}, continuing")
            return True

        elif self.failure_mode == "queue_retry":
            logger.warning(f"Firestore {operation} failed for {item_id}, queuing retry")
            # TODO: Implement retry queue
            return True

        return True
```

### Data Filtering

**File:** `shared/storage/sync_filter.py`

```python
class SyncFilter:
    """Filters data before writing to Firestore."""

    # Fields allowed in Firestore
    ALLOWED_METADATA_FIELDS = {
        'item_id', 'url', 'title', 'byline', 'excerpt',
        'word_count', 'created_at', 'updated_at'
    }

    # Fields that stay in PostgreSQL only
    POSTGRES_ONLY_FIELDS = {
        'text_content',  # Too large for Firestore
        'summary_text',  # AI summaries too large
    }

    # Artifact fields for Firestore
    ALLOWED_ARTIFACT_FIELDS = {
        'status', 'gcs_path', 'gcs_bucket', 'file_size',
        'created_at', 'updated_at'
    }

    # Artifact fields for PostgreSQL only
    EXCLUDED_ARTIFACT_FIELDS = {
        'local_path',     # Not relevant for mobile
        'exit_code',      # Internal detail
        'error_message',  # Internal detail
        'stdout',         # Debug info
        'stderr'          # Debug info
    }

    def filter_article_metadata(self, metadata: ArticleMetadata) -> dict:
        """Filter article metadata for Firestore."""
        filtered = {}
        for key, value in metadata.__dict__.items():
            if key in self.ALLOWED_METADATA_FIELDS:
                filtered[key] = value
        return filtered

    def filter_artifact(self, artifact: ArchiveArtifact) -> dict:
        """Filter artifact data for Firestore."""
        filtered = {}
        for key, value in artifact.__dict__.items():
            if key in self.ALLOWED_ARTIFACT_FIELDS:
                filtered[key] = value
        return filtered
```

## Data Distribution

### PostgreSQL (Full Data)

**Tables:**
- `archived_urls` - URL, item_id, name, created_at, updated_at
- `url_metadata` - text_content (LARGE), metadata_json, word_count
- `archive_artifact` - All fields (status, paths, exit_codes, errors)
- `article_summary` - AI-generated summaries (LARGE)
- `article_entity` - Extracted entities with confidence scores
- `article_tag` - Article tags/categories

**Characteristics:**
- **Complete history:** All operations logged
- **Large fields:** Full text content, AI summaries
- **Internal metadata:** Exit codes, error messages, debug info
- **ACID transactions:** Strong consistency guarantees
- **Full-text search:** PostgreSQL text search
- **Complex queries:** JOINs, aggregations, filtering

### Firestore (Filtered Data)

**Document:** `articles/{item_id}`

```javascript
{
  // Basic metadata (filtered)
  id: "pocket-a1b2c3d4e5f6",
  url: "https://example.com/article",
  title: "Amazing Article",
  byline: "John Doe",
  excerpt: "This article is amazing...",
  word_count: 1500,
  created_at: Timestamp,
  updated_at: Timestamp,

  // Archives map (denormalized)
  archives: {
    readability: {
      status: "success",
      gcs_path: "gs://bucket/archives/pocket-a1b2c3d4e5f6/readability/output.html",
      gcs_bucket: "htbase-archives",
      file_size: 125480,
      updated_at: Timestamp
    },
    monolith: {
      status: "success",
      gcs_path: "gs://...",
      file_size: 2840192,
      updated_at: Timestamp
    }
    // ... other archivers
  },

  // Pocket data (if present)
  pocket: {
    title: "Amazing Article",
    authors: "John Doe",
    image_url: "https://...",
    tags: ["tech", "programming"],
    time_to_read: 7
  },

  // Summary NOT included (too large)
  // Entities NOT included (too large)
  // Tags NOT included (separate collection if needed)
}
```

**Characteristics:**
- **Filtered fields:** No large text content
- **Denormalized:** Archives as nested map (not separate collection)
- **Mobile-optimized:** Only data needed for mobile display
- **Real-time:** Firestore real-time listeners for mobile
- **Offline support:** Firestore offline caching

## Write Strategies

### Strategy 1: Sequential Write (Current)

```python
def create_article(metadata):
    # 1. Write to PostgreSQL FIRST
    pg_success = postgres.create_article(metadata)
    if not pg_success:
        return False

    # 2. Write to Firestore SECOND
    fs_success = firestore.create_article(filtered_metadata)
    if not fs_success:
        # Handle based on failure_mode
        return handle_failure()

    return True
```

**Pros:**
- Simple to implement
- PostgreSQL always has latest data
- Firestore writes are optional

**Cons:**
- Window where PostgreSQL has data but Firestore doesn't
- No atomicity across databases
- Firestore can fall behind

### Strategy 2: Parallel Write (Future)

```python
async def create_article(metadata):
    # Write to both databases in parallel
    pg_task = asyncio.create_task(postgres.create_article(metadata))
    fs_task = asyncio.create_task(firestore.create_article(filtered_metadata))

    pg_success, fs_success = await asyncio.gather(pg_task, fs_task)

    if not pg_success:
        return False  # PostgreSQL is required

    if not fs_success:
        return handle_failure()

    return True
```

**Pros:**
- Faster (parallel execution)
- Reduced latency

**Cons:**
- More complex error handling
- Still no atomicity

## Failure Modes

### Mode 1: fail_fast (Strict Consistency)

```python
failure_mode = "fail_fast"

# If Firestore write fails:
1. Log error
2. Return False
3. Rollback PostgreSQL transaction (if in transaction)
4. Return 500 to client
```

**Use Case:** Strict consistency required, Firestore must stay in sync

**Risk:** Higher error rate, degraded availability if Firestore down

### Mode 2: log_and_continue (Best Effort) **[RECOMMENDED]**

```python
failure_mode = "log_and_continue"

# If Firestore write fails:
1. Log warning
2. Return True (operation succeeds)
3. PostgreSQL data committed
4. Firestore out-of-sync (manual reconciliation needed)
```

**Use Case:** PostgreSQL is source of truth, Firestore is nice-to-have

**Risk:** Firestore can fall behind, requires reconciliation

### Mode 3: queue_retry (Not Implemented)

```python
failure_mode = "queue_retry"

# If Firestore write fails:
1. Log warning
2. Queue operation for retry
3. Return True (operation succeeds)
4. Background worker retries Firestore write
```

**Use Case:** Eventual consistency with automatic reconciliation

**Risk:** Complex retry logic, potential for duplicate writes

## Consistency Guarantees

### Strong Consistency (PostgreSQL)

```
Write Request → PostgreSQL
     ↓
COMMIT (ACID)
     ↓
Read Request → PostgreSQL
     ↓
Always see latest write (immediate consistency)
```

**Guarantees:**
- **Atomicity:** All or nothing
- **Consistency:** Database constraints enforced
- **Isolation:** Transactions don't interfere
- **Durability:** Writes persisted to disk

### Eventual Consistency (Firestore)

```
Write Request → PostgreSQL (SUCCESS)
     ↓
Write Request → Firestore (QUEUED/DELAYED)
     ↓
Read Request → Firestore
     ↓
May see stale data (lag: milliseconds to minutes)
```

**Characteristics:**
- **Eventually consistent:** Writes propagate over time
- **Replication lag:** Firestore may be behind PostgreSQL
- **Best effort:** Firestore writes can fail without blocking
- **Manual reconciliation:** `/sync/postgres-to-firestore` endpoint

## Reconciliation

### Manual Sync Endpoint

**File:** `services/api-gateway/app/routes/sync.py`

```python
@router.post("/sync/postgres-to-firestore")
async def sync_postgres_to_firestore(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Manually sync PostgreSQL data to Firestore."""

    # Get articles from PostgreSQL
    articles = db.query(ArchivedUrl).limit(limit).offset(offset).all()

    synced_count = 0
    failed_count = 0

    for article in articles:
        try:
            # Build Firestore document from PostgreSQL data
            doc_data = {
                'id': article.item_id,
                'url': article.url,
                'title': article.name,
                'created_at': article.created_at,
                'updated_at': article.updated_at,
                'archives': {}
            }

            # Get artifacts for this article
            artifacts = db.query(ArchiveArtifact).filter(
                ArchiveArtifact.archived_url_id == article.id,
                ArchiveArtifact.success == True
            ).all()

            # Add artifact data
            for artifact in artifacts:
                doc_data['archives'][artifact.archiver] = {
                    'status': 'success',
                    'gcs_path': artifact.gcs_path,
                    'gcs_bucket': artifact.gcs_bucket,
                    'file_size': artifact.size_bytes,
                    'updated_at': artifact.updated_at
                }

            # Write to Firestore
            firestore_client.collection('articles').document(article.item_id).set(
                doc_data,
                merge=True  # Update existing or create new
            )

            synced_count += 1

        except Exception as e:
            logger.error(f"Failed to sync {article.item_id}: {e}")
            failed_count += 1

    return {
        'synced': synced_count,
        'failed': failed_count,
        'total': len(articles)
    }
```

### Automated Reconciliation (Future)

**File:** `services/storage-worker/app/tasks.py` (from recent fixes)

```python
@celery_app.task
def reconcile_dual_database():
    """Detect and fix PostgreSQL <-> Firestore drift."""

    # Find articles in PostgreSQL not in Firestore
    threshold = datetime.utcnow() - timedelta(minutes=10)

    missing_in_fs = db.query(ArchivedUrl).filter(
        or_(
            ArchivedUrl.last_synced_to_firestore == None,
            ArchivedUrl.last_synced_to_firestore < threshold
        )
    ).limit(50).all()

    for article in missing_in_fs:
        try:
            # Sync to Firestore
            sync_article_to_firestore(article)

            # Update sync timestamp
            article.last_synced_to_firestore = datetime.utcnow()
            db.commit()

        except Exception as e:
            logger.error(f"Reconciliation failed for {article.item_id}: {e}")

    return len(missing_in_fs)
```

**Scheduling:** Runs every 5 minutes via Celery Beat

## Configuration

### Environment Variables

```bash
# Enable dual persistence
ENABLE_DUAL_PERSISTENCE=true

# Failure mode: fail_fast | log_and_continue | queue_retry
DUAL_WRITE_FAILURE_MODE=log_and_continue

# Firestore configuration
FIRESTORE_PROJECT_ID=your-firebase-project
FIRESTORE_CREDENTIALS_PATH=/path/to/service-account.json

# PostgreSQL (always required)
DATABASE_URL=postgresql://user:pass@localhost:5432/htbase
```

### Server Initialization

**File:** `server.py:110-141`

```python
# Always initialize PostgreSQL
primary_db = PostgresStorage()

# Initialize Firestore if enabled
replica_db = None
if settings.enable_dual_persistence and settings.firestore.project_id:
    replica_db = FirestoreStorage(
        project_id=settings.firestore.project_id,
        credentials_path=settings.firestore.credentials_path
    )

    # Wrap in dual-write coordinator
    db_storage = DualDatabaseStorage(
        postgres=primary_db,
        firestore=replica_db,
        failure_mode=settings.dual_write_failure_mode
    )
else:
    # Fallback to PostgreSQL only
    db_storage = primary_db

# Store on app state
app.state.db_storage = db_storage
app.state.postgres_storage = primary_db
app.state.firestore_storage = replica_db
```

## Monitoring

### Key Metrics

1. **Write Success Rate**
   - PostgreSQL write success rate (should be ~100%)
   - Firestore write success rate (depends on mode)

2. **Sync Lag**
   - Time between PostgreSQL write and Firestore write
   - Number of articles behind in Firestore

3. **Failure Mode Triggers**
   - Count of `fail_fast` failures
   - Count of `log_and_continue` warnings
   - Count of retry queue entries

4. **Reconciliation Stats**
   - Articles synced per reconciliation run
   - Drift detected (PostgreSQL vs Firestore)

### Logging

```python
# Successful dual write
logger.info(f"Article {item_id} written to both databases")

# Firestore write failure (log_and_continue)
logger.warning(f"Firestore write failed for {item_id}, continuing")

# Firestore write failure (fail_fast)
logger.error(f"Firestore write failed for {item_id}, operation failed")

# Reconciliation
logger.info(f"Reconciliation synced {count} articles")
```

## Database Schema Comparison

### PostgreSQL Schema

```sql
-- Full schema with all fields
CREATE TABLE archived_urls (
    id SERIAL PRIMARY KEY,
    item_id VARCHAR(255) UNIQUE NOT NULL,
    url TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_synced_to_firestore TIMESTAMP  -- Reconciliation tracking
);

CREATE TABLE url_metadata (
    id SERIAL PRIMARY KEY,
    save_rowid INTEGER REFERENCES archived_urls(id),
    text TEXT,  -- Full text content (LARGE)
    metadata_json JSONB,
    word_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE archive_artifact (
    id SERIAL PRIMARY KEY,
    archived_url_id INTEGER REFERENCES archived_urls(id),
    archiver VARCHAR(50) NOT NULL,
    task_id VARCHAR(255),
    status VARCHAR(50),  -- pending, success, failed
    success BOOLEAN,
    exit_code INTEGER,      -- Internal
    error_message TEXT,     -- Internal
    saved_path TEXT,        -- Local path
    gcs_path TEXT,          -- Cloud path
    gcs_bucket VARCHAR(255),
    size_bytes BIGINT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_synced_to_firestore TIMESTAMP
);

CREATE TABLE article_summary (
    id SERIAL PRIMARY KEY,
    archived_url_id INTEGER REFERENCES archived_urls(id),
    summary_text TEXT,  -- AI summary (LARGE)
    key_points JSONB,
    created_at TIMESTAMP
);
```

### Firestore Schema

```javascript
// Simplified, denormalized schema for mobile
articles/{item_id} = {
  // Basic fields only
  id: string,
  url: string,
  title: string,
  byline: string,
  excerpt: string,
  word_count: number,
  created_at: Timestamp,
  updated_at: Timestamp,

  // Denormalized archives (not separate collection)
  archives: {
    [archiver_name]: {
      status: string,
      gcs_path: string,
      gcs_bucket: string,
      file_size: number,
      updated_at: Timestamp
    }
  },

  // Pocket data
  pocket: {
    title: string,
    authors: string,
    image_url: string,
    tags: [string],
    time_to_read: number
  },

  // Summary text (optional, keep short)
  summary: {
    text: string,  // Truncated version
    created_at: Timestamp
  }

  // NO: text_content (too large)
  // NO: exit_code, error_message (internal)
  // NO: local_path (not relevant)
}
```

## Best Practices

### 1. Always Treat PostgreSQL as Source of Truth

```python
# ✅ GOOD: Read from PostgreSQL
article = db.query(ArchivedUrl).filter(...).first()

# ❌ BAD: Read from Firestore
article = firestore_client.collection('articles').document(item_id).get()
```

### 2. Use log_and_continue Mode (Recommended)

```python
# ✅ GOOD: Best effort Firestore
DUAL_WRITE_FAILURE_MODE=log_and_continue

# ❌ RISKY: Strict consistency (Firestore outages block writes)
DUAL_WRITE_FAILURE_MODE=fail_fast
```

### 3. Filter Data Before Firestore Write

```python
# ✅ GOOD: Filter large fields
filtered = sync_filter.filter_article_metadata(metadata)
firestore.create_article(filtered)

# ❌ BAD: Write full data
firestore.create_article(metadata)  # May exceed Firestore limits
```

### 4. Monitor Sync Lag

```python
# Check sync lag regularly
articles_behind = db.query(ArchivedUrl).filter(
    or_(
        ArchivedUrl.last_synced_to_firestore == None,
        ArchivedUrl.last_synced_to_firestore < datetime.utcnow() - timedelta(minutes=10)
    )
).count()

if articles_behind > 100:
    logger.warning(f"Firestore sync lag: {articles_behind} articles behind")
```

### 5. Use Reconciliation for Recovery

```bash
# Manual sync after Firestore outage
curl -X POST http://localhost:8000/api/v1/sync/postgres-to-firestore?limit=1000
```

## Limitations

### Current Implementation

1. **No backward sync:** Firestore → PostgreSQL not supported
2. **No automatic retry:** `queue_retry` mode not implemented
3. **Manual reconciliation:** Requires explicit endpoint call
4. **No conflict resolution:** No handling of concurrent updates
5. **One-way replication:** PostgreSQL → Firestore only

### Scalability Concerns

1. **Sequential writes:** PostgreSQL then Firestore (not parallel)
2. **Blocking operations:** Firestore write can slow down API response
3. **No batch optimization:** Each write is separate operation
4. **Memory buffering:** No write-behind caching

## Future Improvements

### 1. Implement queue_retry Mode

```python
class RetryQueue:
    """Queue failed Firestore writes for retry."""

    def enqueue(self, operation, data):
        retry_task = {
            'operation': operation,
            'data': data,
            'attempts': 0,
            'max_attempts': 5,
            'next_attempt': datetime.utcnow() + timedelta(seconds=30)
        }
        redis_client.lpush('firestore_retry_queue', json.dumps(retry_task))
```

### 2. Add Change Data Capture (CDC)

```python
# Stream PostgreSQL changes to Firestore
@postgresql_trigger
def on_archived_url_change(old, new):
    """Trigger on PostgreSQL row change."""
    if new.last_synced_to_firestore != old.last_synced_to_firestore:
        # Sync to Firestore
        sync_to_firestore(new)
```

### 3. Implement Conflict Resolution

```python
def resolve_conflict(pg_data, fs_data):
    """Resolve conflicts using last-write-wins."""
    if pg_data.updated_at > fs_data.updated_at:
        return pg_data  # PostgreSQL wins
    else:
        logger.warning("Firestore has newer data, manual review needed")
        return pg_data  # PostgreSQL still wins (source of truth)
```

## Troubleshooting

### Issue: Firestore Sync Lag

**Symptoms:** Mobile app shows stale data

**Solution:**
```bash
# Check sync lag
curl http://localhost:8000/api/v1/sync/check-drift

# Manual sync
curl -X POST http://localhost:8000/api/v1/sync/postgres-to-firestore?limit=1000
```

### Issue: Firestore Write Failures

**Symptoms:** `log_and_continue` warnings in logs

**Solution:**
1. Check Firestore credentials
2. Verify network connectivity
3. Check Firestore quotas
4. Run manual reconciliation

### Issue: Data Mismatch

**Symptoms:** PostgreSQL has data, Firestore doesn't

**Solution:**
```sql
-- Find unsync'd articles
SELECT id, item_id, created_at, last_synced_to_firestore
FROM archived_urls
WHERE last_synced_to_firestore IS NULL
   OR last_synced_to_firestore < NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

## Next Steps

For related documentation:
- **API endpoints:** [FIREBASE_API_FLOW.md](./FIREBASE_API_FLOW.md)
- **Complete flow:** [REQUEST_FLOW_COMPLETE.md](./REQUEST_FLOW_COMPLETE.md)
- **Visual diagrams:** [diagrams/SEQUENCE_DIAGRAMS.md](./diagrams/SEQUENCE_DIAGRAMS.md)
- **Architecture:** [ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md)
