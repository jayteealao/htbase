# Complete Request Flow: End-to-End

This document traces a complete request through the HTBase system from initial API call to final response, covering all 9 phases of processing.

## Flow Overview

```
Client → API Gateway → Database → Task Queue → Background Worker
→ Archiver → Storage Upload → Summarization → Cleanup → Status Poll → Client
```

**Total Phases:** 9
**Estimated Duration:** 30 seconds - 10 minutes (depends on archiver and URL)
**Processing Model:** Asynchronous with status polling

---

## Example Request

We'll trace this request through the system:

```bash
POST /api/v1/firebase/add-pocket-article
{
  "user_id": "user_12345",
  "url": "https://example.com/amazing-article",
  "pocket_data": {"title": "Amazing Article"},
  "archiver": "all"
}
```

---

## Phase 1: API Gateway Entry

**Duration:** <100ms
**File:** `services/api-gateway/app/routes/firebase.py:45-120`

### Step 1.1: Request Reception

```python
@router.post("/add-pocket-article", response_model=AddPocketArticleResponse)
@rate_limit_archive  # Rate limiting check
async def add_pocket_article(
    request: AddPocketArticleRequest,
    api_key: str = Depends(verify_api_key),  # Authentication
    db: Session = Depends(get_db)
):
```

**Operations:**
1. **Authentication** (`shared/auth.py:verify_api_key`)
   - Extract Bearer token from `Authorization` header
   - Verify token against `API_KEYS` environment variable
   - Return 401 if invalid

2. **Rate Limiting** (`shared/rate_limit.py:check_rate_limit`)
   - Check Redis for request count (sliding window)
   - Increment counter
   - Return 429 if limit exceeded (10 req/min)
   - Add rate limit headers to response

3. **Request Validation** (Pydantic)
   - Validate JSON structure
   - Check required fields (`url`, `user_id`, `pocket_data`)
   - Return 422 if validation fails

### Step 1.2: ID Generation

```python
# Generate unique item_id from URL hash
item_id = hashlib.sha256(request.url.encode()).hexdigest()[:16]
item_id = f"pocket-{item_id}"  # Prefix for Pocket articles
```

**Result:** `pocket-a1b2c3d4e5f6`

### Step 1.3: Duplicate Check

```python
existing_article = db.query(ArchivedUrl).filter(
    ArchivedUrl.item_id == item_id
).first()

if existing_article:
    return AddPocketArticleResponse(
        article_id=item_id,
        status="exists",
        message="Article already archived",
        task_id=None
    )
```

**Decision:**
- Article exists → Return immediately with `status="exists"`
- Article new → Continue to Phase 2

---

## Phase 2: Database Write (Dual Persistence)

**Duration:** 50-200ms
**File:** `shared/storage/dual_database_storage.py:74-115`

### Step 2.1: PostgreSQL Write (PRIMARY - REQUIRED)

**File:** `shared/storage/postgres_storage.py`

```python
# Create ArchivedUrl record
archived_url = ArchivedUrl(
    item_id=item_id,
    url=request.url,
    name=pocket_data.get('title', 'Untitled'),
    created_at=datetime.utcnow()
)
db.add(archived_url)

# Create UrlMetadata record
metadata = UrlMetadata(
    save_rowid=archived_url.id,
    text=pocket_data.get('excerpt', ''),
    metadata_json=json.dumps(pocket_data)
)
db.add(metadata)

db.commit()  # CRITICAL: Must succeed or entire operation fails
```

**Tables Updated:**
- `archived_urls` - URL, item_id, name, created_at
- `url_metadata` - text, metadata_json

### Step 2.2: Firestore Write (REPLICA - BEST EFFORT)

**File:** `shared/storage/firestore_storage.py`

**Only if:** `ENABLE_DUAL_PERSISTENCE=true` and `FIRESTORE_PROJECT_ID` configured

```python
# Filter data for mobile (remove large fields)
filtered_metadata = sync_filter.filter_for_firestore(metadata)

# Write to Firestore
firestore_client.collection('articles').document(item_id).set({
    'id': item_id,
    'url': request.url,
    'metadata': filtered_metadata,  # NO text_content
    'pocket': pocket_data,
    'archives': {},  # Empty, will be populated by workers
    'created_at': firestore.SERVER_TIMESTAMP,
    'updated_at': firestore.SERVER_TIMESTAMP
})
```

**Failure Handling:**
```python
if firestore_write_fails:
    if DUAL_WRITE_FAILURE_MODE == "fail_fast":
        db.rollback()  # Rollback PostgreSQL
        raise HTTPException(500, "Firestore write failed")
    elif DUAL_WRITE_FAILURE_MODE == "log_and_continue":
        logger.warning("Firestore write failed, continuing")
        # PostgreSQL commit stands, Firestore out-of-sync
```

**Data Filtering:** See [DUAL_DATABASE_ARCHITECTURE.md](./DUAL_DATABASE_ARCHITECTURE.md#data-filtering-rules)

---

## Phase 3: Task Queuing

**Duration:** 5-20ms
**File:** `app/task_manager/archiver.py:enqueue()`

### Step 3.1: URL Rewriting (Paywall Bypass)

```python
# Check if URL should be rewritten
rewritten_url = None
if 'twitter.com' in request.url:
    rewritten_url = f"https://freedium.ecsynth.net/{request.url}"
elif 'medium.com' in request.url:
    rewritten_url = f"https://freedium.ecsynth.net/{request.url}"
```

**Result:**
- Original URL stored in database: `https://example.com/amazing-article`
- Rewritten URL used for archiving: Same (no rewrite needed)

### Step 3.2: Create Batch Task

```python
# "all" expands to all available archivers
archivers = ["readability", "monolith", "singlefile-cli", "pdf", "screenshot"]

# Create BatchTask
batch_task = BatchTask(
    task_id=str(uuid.uuid4()),  # "task_uuid_12345"
    archiver_name="all",
    items=[
        BatchItem(
            item_id="pocket-a1b2c3d4e5f6",
            url="https://example.com/amazing-article",
            rewritten_url=None,
            rowid=archived_url.id,
            archiver_name=archiver
        )
        for archiver in archivers  # 5 items created
    ]
)
```

### Step 3.3: Create Pending Artifacts

**For each archiver:**
```python
artifact = ArchiveArtifact(
    archived_url_id=archived_url.id,
    archiver=archiver,
    task_id=task_id,
    status="pending",
    success=False,
    created_at=datetime.utcnow()
)
db.add(artifact)
db.commit()
```

**Tables Updated:**
- `archive_artifact` - 5 rows created (one per archiver), all `status="pending"`

### Step 3.4: Submit to Queue

```python
task_manager._queue.put(batch_task)  # In-memory Python queue
task_manager.start()  # Ensure worker thread is running
```

**Queue:** Python `queue.Queue()` (in-memory, NOT Celery/Redis)

### Step 3.5: Return to Client

```python
return AddPocketArticleResponse(
    article_id="pocket-a1b2c3d4e5f6",
    status="queued",
    message="Article queued for archiving with 5 archivers",
    task_id="task_uuid_12345"
)
```

**HTTP Status:** 202 Accepted (async processing)

---

## Phase 4: Background Processing

**Duration:** 30 seconds - 10 minutes (varies by archiver)
**File:** `app/task_manager/base.py` + `app/task_manager/archiver.py`

### Step 4.1: Worker Thread Picks Up Task

**File:** `app/task_manager/base.py:_run()`

```python
def _run(self):
    """Daemon thread that processes tasks from queue."""
    while True:
        task = self._queue.get(block=True)  # Blocking wait
        try:
            self.process(task)
        except Exception as e:
            logger.error(f"Task processing failed: {e}")
        finally:
            self._queue.task_done()
```

**Threading Model:**
- Single daemon thread per TaskManager
- Processes tasks sequentially (NOT parallel)
- Runs in background, doesn't block API responses

### Step 4.2: Process Batch Items

**File:** `app/task_manager/archiver.py:process()`

```python
def process(self, task: BatchTask):
    for item in task.items:  # 5 items (one per archiver)
        self._process_item(task_id=task.task_id, item=item)
```

### Step 4.3: Process Individual Item

**For each BatchItem (e.g., readability archiver):**

#### 4.3a: Check URL Reachability

```python
def _should_archive(url, archiver):
    # HTTP HEAD request to check URL
    response = httpx.head(url, follow_redirects=True, timeout=10)

    if response.status_code == 404:
        # Mark artifact as failed immediately
        artifact_repo.finalize_result(
            rowid=item.rowid,
            success=False,
            exit_code=404,
            status="failed"
        )
        return False

    return True
```

#### 4.3b: Check Existing Archives

```python
# Check if already archived
existing = artifact_repo.find_successful(
    item_id=item.item_id,
    archiver=item.archiver_name
)

if existing:
    # Reuse existing archive
    artifact_repo.finalize_result(
        rowid=item.rowid,
        success=True,
        saved_path=existing.saved_path,
        status="success"
    )
    return  # Skip archiving
```

#### 4.3c: Execute Archiver

```python
if _should_archive(fetch_url, archiver):
    archiver_instance = _get_archiver(item.archiver_name)
    result = archiver_instance.archive_with_storage(
        url=fetch_url,
        item_id=item.item_id
    )
```

**Continue to Phase 5 →**

---

## Phase 5: Archive Execution

**Duration:** 5-60 seconds per archiver
**File:** `app/archivers/base.py:archive_with_storage()`

### Step 5.1: Run Local Archiving

**Example: Readability Archiver**
**File:** `app/archivers/readability.py:archive()`

```python
def archive(self, url: str, item_id: str) -> ArchiveResult:
    # 1. Fetch HTML
    response = httpx.get(url, timeout=30)
    html_content = response.text

    # 2. Parse with Readability
    doc = Document(html_content)

    # 3. Extract content
    title = doc.title()
    content_html = doc.summary()
    text = extract_text(content_html)

    # 4. Save to local file
    out_dir = Path(data_dir) / item_id / "readability"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "output.html"
    out_file.write_text(content_html, encoding='utf-8')

    # 5. Extract metadata
    metadata = {
        'title': title,
        'text': text,
        'word_count': len(text.split()),
        'extracted_at': datetime.utcnow().isoformat()
    }

    return ArchiveResult(
        success=True,
        saved_path=str(out_file),
        metadata=metadata
    )
```

**Output:** `/data/pocket-a1b2c3d4e5f6/readability/output.html`

### Step 5.2: Upload to Storage Providers

**File:** `app/archivers/base.py:upload_to_all_providers()`

```python
def upload_to_all_providers(local_path: Path, item_id: str):
    """Upload to all configured storage providers in parallel."""
    providers = ["gcs", "local"]  # From STORAGE_PROVIDERS config

    upload_results = []

    # GCS Upload
    if "gcs" in providers:
        gcs_result = gcs_uploader.upload(
            local_path=local_path,
            remote_path=f"archives/{item_id}/readability/output.html",
            bucket=settings.gcs_bucket
        )
        upload_results.append({
            'provider': 'gcs',
            'success': gcs_result.success,
            'gcs_path': f"gs://{settings.gcs_bucket}/archives/{item_id}/readability/output.html",
            'gcs_bucket': settings.gcs_bucket,
            'public_url': gcs_result.public_url
        })

    # Local Backup Upload
    if "local" in providers:
        local_backup_result = local_uploader.copy(
            source=local_path,
            dest=Path(settings.local_backup_dir) / item_id / "readability" / "output.html"
        )
        upload_results.append({
            'provider': 'local',
            'success': local_backup_result.success
        })

    return upload_results
```

**Result:**
```python
[
  {'provider': 'gcs', 'success': True, 'gcs_path': 'gs://...'},
  {'provider': 'local', 'success': True}
]
```

### Step 5.3: Update Database with Results

**File:** `app/archivers/base.py`

```python
# Check if all uploads succeeded
all_succeeded = all(r.get('success') for r in upload_results)

# Update artifact in database
self.db_storage.update_artifact_status(
    item_id=item_id,
    archiver=self.name,
    status="success" if result.success else "failed",
    success=result.success,
    saved_path=result.saved_path,
    gcs_path=upload_results[0].get('gcs_path'),
    gcs_bucket=upload_results[0].get('gcs_bucket'),
    file_size=result.saved_path.stat().st_size,
    metadata=result.metadata
)
```

**Database Update:** `archive_artifact` table
- `status`: "pending" → "success"
- `success`: False → True
- `saved_path`: "/data/pocket-a1b2c3d4e5f6/readability/output.html"
- `gcs_path`: "gs://htbase-archives/archives/pocket-a1b2c3d4e5f6/readability/output.html"
- `file_size`: 125480 (bytes)
- `updated_at`: Current timestamp

### Step 5.4: Update Firestore (if enabled)

**File:** `shared/storage/dual_database_storage.py`

```python
if self.firestore and settings.enable_dual_persistence:
    # Update Firestore document
    firestore_client.collection('articles').document(item_id).update({
        f'archives.readability': {
            'status': 'success',
            'gcs_path': gcs_path,
            'gcs_bucket': gcs_bucket,
            'file_size': file_size,
            'updated_at': firestore.SERVER_TIMESTAMP
        }
    })
```

**Firestore Update:**
```json
{
  "archives": {
    "readability": {
      "status": "success",
      "gcs_path": "gs://htbase-archives/archives/pocket-a1b2c3d4e5f6/readability/output.html",
      "file_size": 125480,
      "updated_at": "2026-01-09T12:34:56Z"
    }
  }
}
```

---

## Phase 6: Storage Upload

**Covered in Phase 5.2** - Uploads happen during archiver execution

**Storage Structure:**

**Local:**
```
/data/
  pocket-a1b2c3d4e5f6/
    readability/
      output.html
    monolith/
      output.html
    pdf/
      output.pdf
    screenshot/
      output.png
```

**Cloud (GCS):**
```
gs://htbase-archives/
  archives/
    pocket-a1b2c3d4e5f6/
      readability/
        output.html
      monolith/
        output.html
      pdf/
        output.pdf
      screenshot/
        output.png
```

---

## Phase 7: Summarization Pipeline

**Duration:** 10-30 seconds (if readability succeeds)
**File:** `app/task_manager/summarization.py`

### Step 7.1: Check if Summarization Enabled

```python
if archiver_name == "readability" and result.success:
    summarization_coordinator.schedule(
        archived_url_id=archived_url.id,
        rowid=artifact.id,
        source="readability",
        reason="task-readability"
    )
```

### Step 7.2: Queue Summarization Task

```python
def schedule(self, archived_url_id, rowid, source, reason):
    if source not in ["readability"]:
        return False  # Only readability triggers summarization

    if not summarizer.is_enabled:
        return False

    task = SummarizeTask(
        rowid=rowid,
        archived_url_id=archived_url_id,
        reason=reason
    )

    self._queue.put(task)  # Separate queue from archiving
```

### Step 7.3: Process Summarization

```python
def process(self, task: SummarizeTask):
    # 1. Get readability output from database
    artifact = db.query(ArchiveArtifact).get(task.rowid)
    html_path = artifact.saved_path

    # 2. Extract text
    html_content = Path(html_path).read_text()
    text = extract_text_from_html(html_content)

    # 3. Chunk text (for large articles)
    chunks = article_chunker.chunk(text, max_tokens=4000)

    # 4. Call LLM provider (Anthropic, OpenAI, etc.)
    summary_response = llm_provider.summarize(
        text=chunks[0],  # Or combine chunks
        prompt="Summarize this article concisely..."
    )

    # 5. Parse response
    summary = response_parser.parse(summary_response)

    # 6. Store in database
    article_summary = ArticleSummary(
        archived_url_id=task.archived_url_id,
        summary_text=summary.text,
        key_points=summary.key_points,
        created_at=datetime.utcnow()
    )
    db.add(article_summary)
    db.commit()
```

**Database Update:** `article_summary` table
- New row with AI-generated summary

**Firestore Update:** (if enabled)
```json
{
  "summary": {
    "text": "AI-generated summary...",
    "created_at": "2026-01-09T12:35:30Z"
  }
}
```

---

## Phase 8: Cleanup Pipeline

**Duration:** After retention period (configurable, default: 24 hours)
**File:** `app/task_manager/cleanup.py`

### Step 8.1: Schedule Cleanup

**Only if all uploads succeeded:**

```python
if all_uploads_succeeded and settings.enable_local_cleanup:
    cleanup_coordinator.schedule_cleanup(
        local_path=saved_path,
        artifact_id=artifact.id,
        retention_hours=settings.local_workspace_retention_hours
    )
```

### Step 8.2: Cleanup Task

```python
@dataclass
class CleanupTask:
    artifact_id: int
    local_path: str
    scheduled_at: datetime
    execute_at: datetime  # scheduled_at + retention_hours
```

### Step 8.3: Execute Cleanup (After Retention Period)

```python
def process(self, task: CleanupTask):
    if datetime.utcnow() < task.execute_at:
        # Re-queue for later
        self._queue.put(task)
        time.sleep(60)
        return

    # Delete local file
    Path(task.local_path).unlink()
    logger.info(f"Cleaned up {task.local_path}")

    # Cloud copies remain in GCS
```

---

## Phase 9: Status Polling

**Duration:** Continuous (client polls every 2-5 seconds)
**File:** `services/api-gateway/app/routes/tasks.py`

### Step 9.1: Client Polls Status

```bash
GET /api/v1/tasks/task_uuid_12345
```

### Step 9.2: Query Database

```python
@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    # Get all artifacts for this task_id
    artifacts = db.query(ArchiveArtifact).filter(
        ArchiveArtifact.task_id == task_id
    ).all()

    if not artifacts:
        raise HTTPException(404, "Task not found")

    # Build response
    items = []
    for artifact in artifacts:
        items.append(TaskItemStatus(
            item_id=artifact.archived_url.item_id,
            archiver=artifact.archiver,
            status=artifact.status,  # "pending", "success", "failed"
            success=artifact.success,
            exit_code=artifact.exit_code,
            saved_path=artifact.saved_path,
            gcs_path=artifact.gcs_path
        ))

    # Determine overall status
    statuses = [item.status for item in items]
    if any(s == "pending" for s in statuses):
        overall_status = "pending"
    elif all(s == "success" for s in statuses):
        overall_status = "success"
    elif any(s == "failed" for s in statuses):
        overall_status = "failed"
    else:
        overall_status = "unknown"

    return TaskStatusResponse(
        task_id=task_id,
        status=overall_status,
        items=items
    )
```

### Step 9.3: Client Response (In Progress)

```json
{
  "task_id": "task_uuid_12345",
  "status": "pending",
  "items": [
    {
      "archiver": "readability",
      "status": "success",
      "success": true,
      "gcs_path": "gs://htbase-archives/archives/pocket-a1b2c3d4e5f6/readability/output.html"
    },
    {
      "archiver": "monolith",
      "status": "pending",
      "success": false
    },
    {
      "archiver": "pdf",
      "status": "pending",
      "success": false
    }
  ]
}
```

### Step 9.4: Client Response (Completed)

```json
{
  "task_id": "task_uuid_12345",
  "status": "success",
  "items": [
    {
      "archiver": "readability",
      "status": "success",
      "success": true,
      "gcs_path": "gs://..."
    },
    {
      "archiver": "monolith",
      "status": "success",
      "success": true,
      "gcs_path": "gs://..."
    },
    {
      "archiver": "pdf",
      "status": "success",
      "success": true,
      "gcs_path": "gs://..."
    },
    {
      "archiver": "screenshot",
      "status": "success",
      "success": true,
      "gcs_path": "gs://..."
    },
    {
      "archiver": "singlefile-cli",
      "status": "success",
      "success": true,
      "gcs_path": "gs://..."
    }
  ]
}
```

---

## Threading Model

### Architecture

```
FastAPI Server (uvicorn)
├─ API Request Handlers (async)
│  └─ Return immediately (202 Accepted)
│
├─ ArchiverTaskManager
│  ├─ _queue: queue.Queue() (in-memory)
│  └─ _worker_thread: threading.Thread(daemon=True)
│     └─ Processes items sequentially
│
├─ SummarizationTaskManager
│  ├─ _queue: queue.Queue()
│  └─ _worker_thread: threading.Thread(daemon=True)
│
└─ CleanupTaskManager
   ├─ _queue: queue.Queue()
   └─ _worker_thread: threading.Thread(daemon=True)
```

### Key Characteristics

- **Non-Blocking API:** Returns immediately with task_id
- **Sequential Processing:** Each worker thread processes one item at a time
- **Multiple Pipelines:** Separate threads for archiving, summarization, cleanup
- **In-Memory Queues:** Python `queue.Queue()`, NOT Celery/Redis
- **Daemon Threads:** Automatically terminated when main process exits

---

## Configuration Impact

### Key Settings That Affect Flow

| Setting | Impact on Flow |
|---------|---------------|
| `skip_existing_saves` | Phase 4: Skip archiving if artifact exists |
| `enable_storage_integration` | Phase 5: Upload to cloud after archiving |
| `storage_providers` | Phase 5: Which backends to upload to |
| `enable_dual_persistence` | Phase 2 & 5: Write to Firestore |
| `dual_write_failure_mode` | Phase 2: Behavior on Firestore failure |
| `summarization.enabled` | Phase 7: Enable/disable AI summarization |
| `enable_local_cleanup` | Phase 8: Schedule file deletion |
| `local_workspace_retention_hours` | Phase 8: How long to keep files |

---

## Error Scenarios

### Scenario 1: URL Unreachable (404)

```
Phase 4.3a: HTTP HEAD request → 404
├─ Mark artifact as failed (exit_code=404)
├─ Skip archiving for this URL
├─ Continue with other archivers
└─ Overall task status: "failed" (for this archiver)
```

### Scenario 2: Archiver Failure

```
Phase 5.1: Archiver execution fails
├─ Catch exception
├─ Log error
├─ Update artifact: status="failed", success=False, exit_code=1
└─ Continue with other archivers
```

### Scenario 3: Storage Upload Failure

```
Phase 5.2: GCS upload fails
├─ all_uploads_succeeded = False
├─ Update artifact with partial results
├─ DO NOT schedule cleanup (keep local file)
└─ Manual intervention required
```

### Scenario 4: Firestore Write Failure

```
Phase 2.2: Firestore write fails
├─ Check dual_write_failure_mode
├─ If "fail_fast": Rollback PostgreSQL, return 500
├─ If "log_and_continue": Log warning, continue (PostgreSQL only)
└─ If "queue_retry": Queue for retry (NOT IMPLEMENTED)
```

---

## Performance Characteristics

### Typical Timings

| Phase | Duration | Bottleneck |
|-------|----------|------------|
| 1. API Gateway | <100ms | Database query |
| 2. Database Write | 50-200ms | PostgreSQL + Firestore |
| 3. Task Queuing | 5-20ms | Memory operations |
| 4. Background Processing | Immediate | Queue pickup |
| 5. Archive Execution | 5-60s per archiver | Network I/O, rendering |
| 6. Storage Upload | 1-10s | Cloud upload bandwidth |
| 7. Summarization | 10-30s | LLM API latency |
| 8. Cleanup | Hours later | Scheduled task |
| 9. Status Polling | <50ms per poll | Database query |

**Total End-to-End:** 30 seconds - 10 minutes (varies by archiver and URL complexity)

### Scalability Considerations

**Current Model:**
- Single worker thread per TaskManager
- Sequential processing (NOT parallel)
- In-memory queues (NOT distributed)

**Limitations:**
- Can't scale horizontally across machines
- Queue lost on process restart
- Single point of failure

**Future Improvements:**
- Implement Celery/Redis (already configured but not used)
- Parallel archiver execution
- Distributed worker pools

---

## Monitoring & Observability

### Key Metrics to Track

1. **API Latency** - Phase 1 response time
2. **Database Write Latency** - Phase 2 timing
3. **Queue Depth** - Number of pending tasks
4. **Worker Utilization** - Thread busy/idle ratio
5. **Archiver Success Rate** - Success/failure per archiver
6. **Storage Upload Success Rate** - Cloud upload reliability
7. **Firestore Sync Lag** - PostgreSQL vs Firestore consistency
8. **End-to-End Duration** - Time from submission to completion

### Logging Checkpoints

```python
# Phase 1
logger.info(f"Request received: {item_id}")

# Phase 2
logger.info(f"Database write complete: {item_id}")

# Phase 3
logger.info(f"Task queued: {task_id}")

# Phase 4
logger.info(f"Processing started: {item_id}/{archiver}")

# Phase 5
logger.info(f"Archive complete: {item_id}/{archiver}, size={file_size}")

# Phase 6
logger.info(f"Uploaded to {provider}: {gcs_path}")

# Phase 7
logger.info(f"Summary generated: {item_id}")

# Phase 8
logger.info(f"Cleanup scheduled: {local_path}")

# Phase 9
logger.debug(f"Status polled: {task_id}")
```

---

## Next Steps

For deeper understanding:
- **Database architecture:** [DUAL_DATABASE_ARCHITECTURE.md](./DUAL_DATABASE_ARCHITECTURE.md)
- **Visual flows:** [diagrams/SEQUENCE_DIAGRAMS.md](./diagrams/SEQUENCE_DIAGRAMS.md)
- **System overview:** [ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md)
- **API endpoints:** [FIREBASE_API_FLOW.md](./FIREBASE_API_FLOW.md)
