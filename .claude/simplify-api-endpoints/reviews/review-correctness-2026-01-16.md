---
command: /review:correctness
session_slug: simplify-api-endpoints
date: 2026-01-16
scope: repo
target: services/api-gateway/app/routes/*.py
paths: services/api-gateway/app/routes/archives.py, services/api-gateway/app/routes/artifacts.py, services/api-gateway/app/routes/system.py, services/api-gateway/app/routes/tasks.py, services/api-gateway/app/routes/sync.py
related:
  session: ../README.md
  spec: null
  plan: ../plan/research-plan.md
  work: ../work/work.md
---

# Correctness Review Report

**Reviewed:** repo / services/api-gateway/app/routes/*.py
**Date:** 2026-01-16
**Reviewer:** Claude Code

---

## 0) Scope, Intent, and Invariants

**What was reviewed:**
- Scope: repo
- Target: services/api-gateway/app/routes/*.py
- Files: 6 route files reviewed (archives.py, artifacts.py, system.py, tasks.py, sync.py, main.py)
- Context: Post-refactor from monolith API (61 endpoints → 36 endpoints = 41% reduction)
- Lines: ~2,000 lines of new/refactored API code

**Intended behavior:**
From work log and research plan:
- Consolidate 61 monolith endpoints into 36 microservices REST endpoints
- Preserve all existing functionality (archive operations, sync, admin, tasks)
- Maintain dual-database persistence (PostgreSQL + Firestore)
- Support async archiving with Celery workers
- Handle batch operations and retries
- Generate signed URLs for cloud storage downloads

**Must-hold invariants:**

1. **Data integrity: ArchivedUrl must be created before ArchiveArtifact**
   - Why: Foreign key constraint `ArchiveArtifact.archived_url_id` references `ArchivedUrl.id`
   - Impact: Database constraint violation if violated

2. **Idempotency: Archive operations must skip existing successful archives**
   - Why: Prevents duplicate work and resource waste
   - Impact: Duplicate artifacts, wasted compute, storage bloat

3. **Concurrency: Artifact creation must use row-level locking to prevent duplicates**
   - Why: Multiple concurrent requests for same URL could create duplicate artifacts
   - Impact: Race conditions, duplicate work, database integrity issues

4. **Transaction safety: Database operations must commit or rollback atomically**
   - Why: Partial state leads to orphaned records and sync issues
   - Impact: Data inconsistency between PostgreSQL and Firestore

5. **File cleanup: Local files can only be deleted after all cloud uploads succeed**
   - Why: Prevents data loss if cloud upload fails
   - Impact: Permanent data loss if local file deleted prematurely

6. **Rate limiting: All endpoints must have appropriate rate limits**
   - Why: Prevents abuse and resource exhaustion
   - Impact: DoS attacks, resource exhaustion

7. **Error handling: Client errors (4xx) vs server errors (5xx) must be distinguished**
   - Why: Affects retry logic and observability
   - Impact: Clients retry non-retryable errors, false alerts

8. **Task ID uniqueness: Each task batch must have unique workflow ID**
   - Why: Task status tracking relies on unique task_id
   - Impact: Cannot track task progress, status endpoint confusion

**Key constraints:**
- Max file size: Not enforced in code (could lead to OOM)
- Max batch size: Not enforced (could overwhelm workers)
- Supported archivers: ["singlefile", "monolith", "readability", "pdf", "screenshot"]
- Database: PostgreSQL with SQLAlchemy ORM
- Storage: Local filesystem + Google Cloud Storage (GCS)
- Queue: Celery with Redis broker
- Dual persistence: PostgreSQL (source of truth) + Firestore (client access)

**Known edge cases:**
From context and code analysis:
- Empty batch requests (items=[])
- Duplicate URL submissions
- Concurrent archive requests for same URL
- Firestore not configured (optional)
- Storage provider failures
- Worker crashes mid-batch
- Database connection failures
- Invalid archiver names

---

## 1) Executive Summary

**Merge Recommendation:** REQUEST_CHANGES

**Rationale:**
The API consolidation refactor successfully reduced endpoint count by 41% and improved code organization. However, several HIGH severity correctness issues were found that could lead to data loss, race conditions, and resource exhaustion. Most critically:
1. No max batch size enforcement (DoS risk, worker exhaustion)
2. Race condition in concurrent archive creation despite row locking attempt
3. Missing rollback on task dispatch failure (orphaned DB records)
4. No file size validation (OOM risk)
5. Dangerous CORS configuration in production

These issues should be addressed before merging to prevent production incidents.

**Critical Issues (BLOCKER/HIGH):**
1. **CR-1**: Missing max batch size validation → worker exhaustion and resource DoS
2. **CR-2**: Race condition in artifact creation despite row locking attempt
3. **CR-3**: Missing transaction rollback on Celery dispatch failure → orphaned records
4. **CR-4**: No file size validation in upload workflow → OOM crashes
5. **CR-5**: Dangerous CORS configuration (allow all origins) in production

**Overall Assessment:**
- Correctness: Good (solid logic, but critical edge cases missed)
- Error Handling: Adequate (most paths covered, but missing cleanup)
- Edge Case Coverage: Incomplete (batch limits, file sizes not validated)
- Invariant Safety: Mostly Safe (race condition needs fix, cleanup issues)

---

## 2) Findings Table

| ID | Severity | Confidence | Category | File:Line | Failure Scenario |
|----|----------|------------|----------|-----------|------------------|
| CR-1 | HIGH | High | Input Validation | `archives.py:77-78` | Large batch → worker exhaustion |
| CR-2 | HIGH | High | Concurrency | `archives.py:196-241` | Concurrent requests → duplicate artifacts |
| CR-3 | HIGH | High | Transaction Safety | `archives.py:260-301` | Task dispatch fail → orphaned DB records |
| CR-4 | HIGH | Med | Resource Exhaustion | `archives.py:175-306` | No file size check → OOM |
| CR-5 | HIGH | High | Security | `main.py:85-91` | CORS allows all origins → XSS/CSRF |
| CR-6 | MED | High | Error Handling | `artifacts.py:304-338` | File delete fails but DB updated |
| CR-7 | MED | High | Idempotency | `sync.py:416-445` | Firestore sync creates duplicates on retry |
| CR-8 | MED | Med | State Transition | `tasks.py:72-82` | Incomplete status mapping logic |
| CR-9 | LOW | High | Input Validation | `archives.py:163-168` | Invalid archiver returns 400 (good) |
| CR-10 | LOW | Med | Boundary | `tasks.py:95-107` | Empty task list edge case |

**Findings Summary:**
- BLOCKER: 0
- HIGH: 5
- MED: 3
- LOW: 2
- NIT: 0

---

## 3) Findings (Detailed)

### CR-1: Missing Max Batch Size Validation → Worker Exhaustion [HIGH]

**Location:** `services/api-gateway/app/routes/archives.py:77-78`

**Invariant Violated:**
- "Batch requests must have reasonable size limits to prevent resource exhaustion"
- No enforcement in code - attackers can submit unlimited batch sizes

**Evidence:**
```python
# Lines 77-79
class CreateArchiveRequest(BaseModel):
    """Request model for creating archives."""
    items: List[ArchiveItem] = Field(..., min_items=1, description="URLs to archive")
    # ❌ No max_items constraint!
    archivers: List[str] = Field(["all"], description="Archivers to use (default: all)")
```

```python
# Lines 155-173 - No batch size check before processing
async def create_archives(
    request: CreateArchiveRequest,
    db: Session = Depends(get_db),
):
    is_batch = len(request.items) > 1
    archivers = request.archivers

    # Handle "all" archiver
    if "all" in archivers:
        archivers = AVAILABLE_ARCHIVERS  # 5 archivers

    # ❌ No check: if len(request.items) > MAX_BATCH_SIZE
    # If someone submits 10,000 URLs with "all" archivers:
    # → 10,000 × 5 = 50,000 Celery tasks queued
    # → Workers overwhelmed, queue exhaustion, Redis memory issues
```

**Failure Scenario:**
```json
// Attacker submits massive batch
POST /api/v1/archives
{
  "items": [
    {"id": "1", "url": "https://example.com/1"},
    {"id": "2", "url": "https://example.com/2"},
    ...
    {"id": "10000", "url": "https://example.com/10000"}
  ],
  "archivers": ["all"]  // 5 archivers
}

// Result:
// → 50,000 Celery tasks created (10,000 URLs × 5 archivers)
// → Redis queue memory exhausted
// → Workers overwhelmed processing massive batch
// → Legitimate requests starved
// → Service degradation or outage
```

**Impact:**
- Resource exhaustion (Redis memory, worker CPU)
- Denial of service for legitimate users
- Database connection pool exhaustion
- Celery worker crashes
- Queue backlog that takes hours to clear

**Severity:** HIGH
**Confidence:** High
**Category:** Input Validation + Resource Exhaustion

**Smallest Fix:**
Add max_items constraint:

```diff
--- a/services/api-gateway/app/routes/archives.py
+++ b/services/api-gateway/app/routes/archives.py
@@ -75,7 +75,7 @@ class CreateArchiveRequest(BaseModel):
 class CreateArchiveRequest(BaseModel):
     """Request model for creating archives."""
-    items: List[ArchiveItem] = Field(..., min_items=1, description="URLs to archive")
+    items: List[ArchiveItem] = Field(..., min_items=1, max_items=100, description="URLs to archive (max 100)")
     archivers: List[str] = Field(["all"], description="Archivers to use (default: all)")
     options: Optional[ArchiveOptions] = Field(None, description="Optional workflow features")
```

**Alternative (more flexible):**
Add configurable limit with better error message:

```python
# In shared/config.py
class ArchiveSettings(BaseSettings):
    max_batch_size: int = Field(100, env="ARCHIVE_MAX_BATCH_SIZE")

# In archives.py:155
async def create_archives(...):
    # Validate batch size
    if len(request.items) > settings.archive.max_batch_size:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds limit: {len(request.items)} > {settings.archive.max_batch_size}"
        )
```

**Test case:**
```python
def test_batch_size_limit():
    """Test that batch size is limited."""
    items = [{"id": str(i), "url": f"https://example.com/{i}"} for i in range(101)]
    response = client.post("/api/v1/archives", json={"items": items})
    assert response.status_code == 400
    assert "exceeds limit" in response.json()["detail"]
```

---

### CR-2: Race Condition in Artifact Creation Despite Row Locking [HIGH]

**Location:** `services/api-gateway/app/routes/archives.py:196-241`

**Invariant Violated:**
- "Concurrent archive requests for same URL must not create duplicate artifacts"
- Row-level locking used but with incorrect timing (TOCTOU race condition)

**Evidence:**
```python
# Lines 184-203 - Race condition window
# STEP 1: Get or create archived URL (OUTSIDE lock)
existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
if existing:
    archived_url_id = existing.id
else:
    archived_url = ArchivedUrl(url=url, item_id=item_id)
    db.add(archived_url)
    db.flush()
    archived_url_id = archived_url.id

# STEP 2: Lock row for artifact check (INSIDE lock)
# ❌ RACE CONDITION: Between STEP 1 and STEP 2, another request could:
# - Create the same ArchivedUrl
# - Start checking for artifacts
# - Both requests proceed thinking they need to create artifacts

# Lines 196-203
for archiver in archivers:
    # Lock row to prevent race conditions
    locked_url = (
        db.query(ArchivedUrl)
        .filter(ArchivedUrl.id == archived_url_id)
        .with_for_update()  # ✅ Good: Row-level lock
        .first()
    )
```

**Failure Scenario:**
```python
# Time T0: Request A arrives for URL "https://example.com/article"
# Request A: Check if URL exists → NOT FOUND
# Request A: Create ArchivedUrl (id=123)
# Request A: db.flush() - not yet committed

# Time T1: Request B arrives for SAME URL (concurrent)
# Request B: Check if URL exists → NOT FOUND (A hasn't committed)
# Request B: Create ArchivedUrl (id=124, DUPLICATE!)
# Request B: db.flush()

# Time T2: Both requests now have different archived_url_ids
# Request A: Lock row 123, check for artifacts
# Request B: Lock row 124, check for artifacts (different row, no conflict!)
# Both: Create artifacts for their respective rows

# Result: DUPLICATE ArchivedUrl records and duplicate artifacts!
```

**Impact:**
- Duplicate ArchivedUrl records for same URL
- Duplicate artifacts created
- Wasted compute and storage
- Database bloat
- Sync issues between PostgreSQL and Firestore

**Severity:** HIGH
**Confidence:** High (classic TOCTOU race condition)
**Category:** Concurrency + Data Integrity

**Root Cause:**
The row lock (`with_for_update()`) happens AFTER the ArchivedUrl is created, but before commit. Two concurrent requests can both create ArchivedUrl records, then each lock their own row (no conflict).

**Smallest Fix:**
Use database unique constraint + handle conflict:

```diff
--- a/services/api-gateway/app/routes/archives.py
+++ b/services/api-gateway/app/routes/archives.py
@@ -183,15 +183,23 @@ async def create_archives(
         )

         # Get or create archived URL
-        existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
-        if existing:
-            archived_url_id = existing.id
-        else:
-            archived_url = ArchivedUrl(url=url, item_id=item_id)
-            db.add(archived_url)
-            db.flush()
-            archived_url_id = archived_url.id
+        try:
+            # Lock entire table briefly for this URL (prevents race)
+            existing = (
+                db.query(ArchivedUrl)
+                .filter(ArchivedUrl.url == url)
+                .with_for_update()  # Lock before check
+                .first()
+            )
+            if existing:
+                archived_url_id = existing.id
+            else:
+                archived_url = ArchivedUrl(url=url, item_id=item_id)
+                db.add(archived_url)
+                db.flush()
+                archived_url_id = archived_url.id
+        except IntegrityError:
+            # Concurrent insert, re-fetch
+            db.rollback()
+            existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
+            archived_url_id = existing.id
```

**Alternative (better - use database unique constraint):**
Ensure `ArchivedUrl.url` has unique constraint in schema:

```sql
-- Migration
ALTER TABLE archived_urls ADD CONSTRAINT archived_urls_url_key UNIQUE (url);
```

Then handle conflict gracefully:

```python
from sqlalchemy.exc import IntegrityError

# Get or create archived URL with conflict handling
try:
    archived_url = ArchivedUrl(url=url, item_id=item_id)
    db.add(archived_url)
    db.flush()
    archived_url_id = archived_url.id
except IntegrityError:
    # URL already exists (concurrent insert), fetch it
    db.rollback()
    existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
    archived_url_id = existing.id
```

**Test case:**
```python
import concurrent.futures

def test_concurrent_archive_creation():
    """Test that concurrent requests don't create duplicates."""
    url = "https://example.com/test-concurrent"

    def create_archive():
        return client.post("/api/v1/archives", json={
            "items": [{"id": "test", "url": url}],
            "archivers": ["readability"]
        })

    # Send 10 concurrent requests for same URL
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_archive) for _ in range(10)]
        results = [f.result() for f in futures]

    # All should succeed
    assert all(r.status_code == 200 for r in results)

    # But only ONE ArchivedUrl record should exist
    with db_session() as db:
        count = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).count()
        assert count == 1, f"Expected 1 ArchivedUrl, found {count}"
```

---

### CR-3: Missing Transaction Rollback on Celery Dispatch Failure [HIGH]

**Location:** `services/api-gateway/app/routes/archives.py:260-301`

**Invariant Violated:**
- "Database changes must be rolled back if task dispatch fails"
- Commit happens before verifying Celery dispatch success

**Evidence:**
```python
# Lines 258-260 - Commit BEFORE task dispatch
db.commit()  # ❌ Commits artifacts to DB

if not all_tasks:
    return TaskAccepted(...)

# Lines 269-301 - Task dispatch AFTER commit
task_group = group(all_tasks)

if request.options:
    steps = [task_group]
    # Build workflow chain...
    workflow = chain(*steps) if len(steps) > 1 else steps[0]
    workflow.apply_async()  # ❌ Could fail! No rollback!
else:
    task_group.apply_async()  # ❌ Could fail! No rollback!

# If apply_async() fails (Redis down, network error):
# → Database has artifacts in "pending" state
# → No Celery tasks actually queued
# → Artifacts stuck in "pending" forever
# → No way to recover without manual intervention
```

**Failure Scenario:**
```python
# Request: Archive 100 URLs
POST /api/v1/archives
{
  "items": [...100 URLs...],
  "archivers": ["readability"]
}

# Execution:
# 1. Create 100 ArchivedUrl records ✅
# 2. Create 100 ArchiveArtifact records (status="pending") ✅
# 3. db.commit() ✅
# 4. Build Celery task group (100 tasks) ✅
# 5. task_group.apply_async() ❌ FAILS (Redis connection lost)

# Result:
# → Database has 100 artifacts in "pending" state
# → No Celery tasks queued (Redis connection failed)
# → Artifacts stuck forever in "pending"
# → Client gets 500 error but DB already committed
# → No automatic retry, manual cleanup required
```

**Impact:**
- Orphaned database records in "pending" state
- No tasks actually queued despite DB commit
- Impossible to detect failed dispatches
- Requires manual cleanup or retry
- User confusion (status shows "pending" forever)

**Severity:** HIGH
**Confidence:** High
**Category:** Transaction Safety + Error Handling

**Smallest Fix:**
Move commit after successful dispatch:

```diff
--- a/services/api-gateway/app/routes/archives.py
+++ b/services/api-gateway/app/routes/archives.py
@@ -257,9 +257,6 @@ async def create_archives(
                 )
             )

-    db.commit()
-
     if not all_tasks:
+        db.commit()
         return TaskAccepted(
             task_id=workflow_id,
@@ -270,17 +267,25 @@ async def create_archives(
     # Build workflow
     task_group = group(all_tasks)

-    # Add optional workflow steps
-    if request.options:
-        steps = [task_group]
-        # ... build chain ...
-        workflow = chain(*steps) if len(steps) > 1 else steps[0]
-        workflow.apply_async()
-    else:
-        task_group.apply_async()
+    try:
+        # Add optional workflow steps
+        if request.options:
+            steps = [task_group]
+            # ... build chain ...
+            workflow = chain(*steps) if len(steps) > 1 else steps[0]
+            workflow.apply_async()
+        else:
+            task_group.apply_async()
+
+        # Only commit if dispatch succeeded
+        db.commit()
+    except Exception as e:
+        # Rollback on dispatch failure
+        db.rollback()
+        logger.error(f"Failed to dispatch tasks: {e}")
+        raise HTTPException(500, f"Failed to queue archiving tasks: {e}")

     return TaskAccepted(...)
```

**Alternative (two-phase commit pattern):**
Use Celery result backend to track dispatch status:

```python
# Dispatch tasks first
try:
    result = task_group.apply_async()
    task_ids = [r.id for r in result.results]
except Exception as e:
    # Failed to dispatch, don't commit DB
    db.rollback()
    raise HTTPException(500, f"Failed to queue tasks: {e}")

# Dispatch succeeded, now commit DB
try:
    db.commit()
except Exception as e:
    # DB commit failed, revoke queued tasks
    for task_id in task_ids:
        celery_app.control.revoke(task_id, terminate=True)
    raise HTTPException(500, f"Failed to commit: {e}")
```

**Test case:**
```python
def test_rollback_on_celery_failure(monkeypatch):
    """Test that DB is rolled back if Celery dispatch fails."""
    def mock_apply_async_failure(*args, **kwargs):
        raise ConnectionError("Redis connection failed")

    monkeypatch.setattr("celery.group.apply_async", mock_apply_async_failure)

    response = client.post("/api/v1/archives", json={
        "items": [{"id": "test", "url": "https://example.com/test"}],
        "archivers": ["readability"]
    })

    # Should return error
    assert response.status_code == 500

    # Database should NOT have artifacts
    with db_session() as db:
        count = db.query(ArchiveArtifact).filter(
            ArchiveArtifact.task_id == "test-workflow"
        ).count()
        assert count == 0, "Expected rollback but found DB records"
```

---

### CR-4: No File Size Validation in Upload Workflow [HIGH]

**Location:** `services/api-gateway/app/routes/archives.py:175-306` (entire workflow)

**Invariant Violated:**
- "Files downloaded by archivers must be size-limited to prevent OOM"
- No file size check before or during archiving

**Evidence:**
The code dispatches Celery tasks to archive workers without any file size limits:

```python
# Lines 246-258 - Create Celery task (no size limit)
task_name = f"services.archive_worker.tasks.archive_{archiver}"
all_tasks.append(
    celery_app.signature(
        task_name,
        kwargs={
            "item_id": item_id,
            "url": fetch_url,  # ❌ No size check before downloading
            "archived_url_id": archived_url_id,
            "artifact_id": artifact.id,
        },
    )
)
```

**Failure Scenario:**
```python
# Attacker submits URL to huge file
POST /api/v1/archives
{
  "items": [{"id": "attack", "url": "https://evil.com/10GB-file.html"}],
  "archivers": ["singlefile", "screenshot", "pdf"]
}

# Execution:
# 1. API Gateway accepts request ✅
# 2. Creates ArchiveArtifact records ✅
# 3. Dispatches 3 Celery tasks ✅
# 4. Worker downloads 10GB HTML file ❌
#    → Worker OOM (Out of Memory)
#    → Worker process killed by OS
#    → Other tasks on that worker also killed
# 5. Retry logic kicks in, same OOM crash repeats

# Impact:
# → Worker crashes repeatedly
# → All tasks on that worker fail
# → Queue backlog builds up
# → Service degradation
```

**Impact:**
- Worker OOM crashes
- Other tasks killed when worker crashes
- Retry amplification (crashes repeat)
- Resource exhaustion
- Denial of service

**Severity:** HIGH
**Confidence:** Med (depends on worker implementation)
**Category:** Resource Exhaustion + Input Validation

**Note:**
This issue likely exists in the **worker code** (not in API Gateway). The workers should validate Content-Length before downloading. However, the API Gateway could add URL reputation checks or size hints.

**Smallest Fix (in workers):**
Add size check before download:

```python
# In services/archive_worker/tasks.py (worker code)
import httpx

async def archive_singlefile(item_id: str, url: str, ...):
    """Archive URL with SingleFile."""
    MAX_SIZE = 100 * 1024 * 1024  # 100 MB

    # Check Content-Length before downloading
    async with httpx.AsyncClient() as client:
        head_response = await client.head(url, follow_redirects=True)
        content_length = int(head_response.headers.get("content-length", 0))

        if content_length > MAX_SIZE:
            raise ValueError(f"File too large: {content_length} bytes (max {MAX_SIZE})")

        # Now download (with streaming to prevent OOM)
        # ...
```

**Alternative (in API Gateway - pre-check):**
Add URL validation with HEAD request:

```python
# In archives.py, before creating tasks
import httpx

for item in request.items:
    url = str(item.url)

    # Pre-check file size
    try:
        async with httpx.AsyncClient() as client:
            head = await client.head(url, follow_redirects=True, timeout=5)
            size = int(head.headers.get("content-length", 0))
            if size > 100 * 1024 * 1024:  # 100 MB
                raise HTTPException(400, f"URL too large: {size} bytes")
    except httpx.RequestError:
        # Can't check size, proceed with caution
        pass
```

**Test case:**
```python
def test_rejects_large_files(httpx_mock):
    """Test that large files are rejected."""
    httpx_mock.add_response(
        url="https://example.com/huge.html",
        method="HEAD",
        headers={"content-length": str(200 * 1024 * 1024)}  # 200 MB
    )

    response = client.post("/api/v1/archives", json={
        "items": [{"id": "test", "url": "https://example.com/huge.html"}]
    })

    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()
```

---

### CR-5: Dangerous CORS Configuration (Allow All Origins) [HIGH]

**Location:** `services/api-gateway/app/main.py:85-91`

**Invariant Violated:**
- "CORS should only allow trusted origins in production"
- Currently allows ALL origins, exposing API to XSS and CSRF attacks

**Evidence:**
```python
# Lines 84-91 - CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ❌ Allows ANY origin!
    allow_credentials=True,  # ❌ With credentials enabled!
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Failure Scenario:**
```javascript
// Attacker creates malicious website: evil.com
// Victim is logged into htbase.com with valid API key

// Attacker's JavaScript on evil.com:
fetch('https://htbase.com/api/v1/archives', {
  method: 'DELETE',
  headers: {
    'Authorization': 'Bearer VICTIM_API_KEY',  // Stolen via XSS or phishing
    'Content-Type': 'application/json'
  },
  credentials: 'include',  // Include cookies
  body: JSON.stringify({
    identifier: 'important-article',
    type: 'item_id',
    delete_files: true  // Delete files permanently!
  })
})

// Browser allows request because:
// 1. allow_origins=["*"] → No CORS block
// 2. allow_credentials=True → Cookies sent
// 3. API key in header → Request succeeds

// Result:
// → Victim's important article DELETED
// → Files permanently removed
// → No way to recover
```

**Impact:**
- Cross-site request forgery (CSRF) attacks
- Unauthorized API access from malicious sites
- Data deletion or modification
- Privacy violations (data exfiltration)
- Reputation damage

**Severity:** HIGH
**Confidence:** High
**Category:** Security + Configuration

**Smallest Fix:**
Configure allowed origins from environment:

```diff
--- a/services/api-gateway/app/main.py
+++ b/services/api-gateway/app/main.py
@@ -82,11 +82,22 @@ def create_app() -> FastAPI:
     # Add rate limit middleware for response headers
     app.add_middleware(RateLimitMiddleware)

+    # Configure allowed origins from settings
+    allowed_origins = []
+    if settings.environment == "production":
+        # Production: Only allow specific domains
+        allowed_origins = [
+            "https://htbase.com",
+            "https://www.htbase.com",
+        ]
+    else:
+        # Development: Allow localhost
+        allowed_origins = ["http://localhost:3000", "http://localhost:8080"]
+
     # CORS middleware
     app.add_middleware(
         CORSMiddleware,
-        allow_origins=["*"],  # Configure appropriately in production
-        allow_credentials=True,
+        allow_origins=allowed_origins,
+        allow_credentials=True if settings.environment != "production" else False,
         allow_methods=["*"],
         allow_headers=["*"],
     )
```

**Alternative (environment variable):**
```python
# In shared/config.py
class Settings(BaseSettings):
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"],
        env="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins"
    )

    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

# In main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.environment != "production",
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**Test case:**
```python
def test_cors_blocks_untrusted_origins():
    """Test that CORS blocks requests from untrusted origins."""
    response = client.get(
        "/health",
        headers={"Origin": "https://evil.com"}
    )

    # Should not have CORS header for untrusted origin
    assert "access-control-allow-origin" not in response.headers
```

---

### CR-6: File Delete Failure Not Rolled Back in Database [MED]

**Location:** `services/api-gateway/app/routes/artifacts.py:304-338`

**Invariant Violated:**
- "Database state should reflect actual file system state"
- Database updated even if file deletion fails

**Evidence:**
```python
# Lines 308-326 - File deletion loop
for artifact in artifacts:
    if not artifact.saved_path:
        continue

    path = Path(artifact.saved_path)
    if not path.exists():
        continue

    try:
        size = artifact.size_bytes or 0
        path.unlink()
        artifact.local_file_deleted = True  # ✅ Mark as deleted
        deleted_count += 1
        space_freed += size
        logger.info(f"Deleted local file: {path} ({size} bytes)")
    except Exception as e:
        error_msg = f"Failed to delete {artifact.saved_path}: {e}"
        errors.append(error_msg)
        logger.error(error_msg)
        # ❌ Continue to next file, but artifact.local_file_deleted not set

# Line 326 - Commit ALL changes (even partial failures)
db.commit()  # ❌ Commits artifacts.local_file_deleted=True even if some failed
```

**Failure Scenario:**
```python
# Request: Cleanup 100 artifacts
POST /api/v1/artifacts/cleanup
{
  "older_than_hours": 24,
  "dry_run": false
}

# Execution:
# Artifact 1-50: File deleted ✅, DB updated (local_file_deleted=True) ✅
# Artifact 51: Permission denied ❌, DB NOT updated, error logged
# Artifact 52-100: Files deleted ✅, DB updated ✅

# db.commit() called

# Result:
# → Database shows artifacts 1-50, 52-100 as deleted
# → But artifact 51 STILL EXISTS on disk
# → Database inconsistency: DB says deleted, file still there
# → Future cleanup won't retry (local_file_deleted=True in DB)
# → File orphaned forever
```

**Impact:**
- Database-filesystem inconsistency
- Orphaned files not cleaned up
- Inaccurate storage metrics
- Cleanup doesn't retry failed deletions

**Severity:** MED
**Confidence:** High
**Category:** State Transition + Error Handling

**Smallest Fix:**
Only mark as deleted if file deletion succeeds:

```diff
--- a/services/api-gateway/app/routes/artifacts.py
+++ b/services/api-gateway/app/routes/artifacts.py
@@ -307,21 +307,22 @@ async def cleanup_artifacts(

     for artifact in artifacts:
         if not artifact.saved_path:
+            artifact.local_file_deleted = True  # No file to delete
             continue

         path = Path(artifact.saved_path)
         if not path.exists():
+            artifact.local_file_deleted = True  # Already gone
             continue

         try:
             size = artifact.size_bytes or 0
             path.unlink()
+            # ✅ Only mark as deleted if unlink succeeded
             artifact.local_file_deleted = True
             deleted_count += 1
             space_freed += size
             logger.info(f"Deleted local file: {path} ({size} bytes)")
         except Exception as e:
+            # ❌ Don't mark as deleted if deletion failed
             error_msg = f"Failed to delete {artifact.saved_path}: {e}"
             errors.append(error_msg)
             logger.error(error_msg)
+            # Don't set artifact.local_file_deleted = True here!

     db.commit()
```

**Alternative (atomic - all or nothing):**
Rollback entire operation if ANY file fails:

```python
# Track which artifacts were successfully deleted
deleted_artifacts = []

for artifact in artifacts:
    # ... file deletion logic ...
    try:
        path.unlink()
        deleted_artifacts.append(artifact)
    except Exception as e:
        # Rollback: restore all previously deleted files (if possible)
        logger.error(f"Cleanup failed at {path}, rolling back")
        db.rollback()
        raise HTTPException(500, f"Cleanup failed: {e}")

# All succeeded, mark as deleted
for artifact in deleted_artifacts:
    artifact.local_file_deleted = True
db.commit()
```

**Test case:**
```python
def test_cleanup_rollback_on_permission_error(tmp_path, monkeypatch):
    """Test that DB is not updated if file deletion fails."""
    # Create test file with no delete permission
    test_file = tmp_path / "test.html"
    test_file.write_text("test")
    test_file.chmod(0o444)  # Read-only

    # Mock artifact with this file
    # ... setup ...

    response = client.post("/api/v1/artifacts/cleanup", json={
        "dry_run": False,
        "older_than_hours": 1
    })

    # Should report error
    assert len(response.json()["errors"]) > 0

    # Database should NOT mark as deleted
    with db_session() as db:
        artifact = db.query(ArchiveArtifact).filter(...).first()
        assert artifact.local_file_deleted == False
```

---

### CR-7: Firestore Sync Creates Duplicates on Retry [MED]

**Location:** `services/api-gateway/app/routes/sync.py:416-445`

**Invariant Violated:**
- "Sync operations must be idempotent (safe to retry)"
- Firestore import creates new artifact on retry even if already exists

**Evidence:**
```python
# Lines 416-445 - Artifact sync logic
archives = article.get("archives", {})
for archiver, archive_data in archives.items():
    # Check if artifact exists
    artifact = (
        db.query(ArchiveArtifact)
        .filter(
            ArchiveArtifact.archived_url_id == archived_url.id,
            ArchiveArtifact.archiver == archiver,
        )
        .first()
    )

    if artifact:
        # Update existing
        artifact.status = archive_data.get("status", "pending")
        artifact.success = archive_data.get("success", False)
        if archive_data.get("gcs_path"):
            artifact.gcs_path = archive_data.get("gcs_path")
    else:
        # Create new
        artifact = ArchiveArtifact(
            archived_url_id=archived_url.id,
            archiver=archiver,
            status=archive_data.get("status", "pending"),
            success=archive_data.get("success", False),
            gcs_path=archive_data.get("gcs_path"),
        )
        db.add(artifact)

db.commit()  # ❌ No error handling for duplicate artifacts
```

**Failure Scenario:**
```python
# Time T0: Sync article "article-123" from Firestore
POST /api/v1/sync/import
{"item_id": "article-123"}

# Execution:
# 1. Fetch article from Firestore ✅
# 2. Create ArchivedUrl in PostgreSQL ✅
# 3. Create 3 ArchiveArtifacts (readability, pdf, screenshot) ✅
# 4. Commit ✅

# Time T1: Sync SAME article again (retry due to client error)
POST /api/v1/sync/import
{"item_id": "article-123"}

# Execution:
# 1. Fetch article from Firestore ✅
# 2. Find existing ArchivedUrl ✅
# 3. Check for artifacts:
#    - Query by archived_url_id + archiver
#    - But if there's a race or query issue, might not find them
# 4. Create DUPLICATE artifacts ❌
# 5. Commit - IntegrityError if unique constraint exists

# Result:
# → If NO unique constraint: Duplicate artifacts created
# → If unique constraint exists: IntegrityError crash
```

**Impact:**
- Duplicate artifacts on retry
- Database integrity errors
- Sync failures
- Data inconsistency

**Severity:** MED
**Confidence:** High
**Category:** Idempotency + Error Handling

**Smallest Fix:**
Add unique constraint handling:

```diff
--- a/services/api-gateway/app/routes/sync.py
+++ b/services/api-gateway/app/routes/sync.py
@@ -415,6 +415,7 @@ async def sync_firestore_to_postgres(

         # Sync artifacts from Firestore archives map
         archives = article.get("archives", {})
         for archiver, archive_data in archives.items():
+            try:
                 # Check if artifact exists
                 artifact = (
@@ -429,7 +430,7 @@ async def sync_firestore_to_postgres(
                 if artifact:
                     # Update existing
                     artifact.status = archive_data.get("status", "pending")
@@ -444,11 +445,16 @@ async def sync_firestore_to_postgres(
                         gcs_path=archive_data.get("gcs_path"),
                     )
                     db.add(artifact)
+                    db.flush()  # Flush to detect conflicts early
+            except IntegrityError:
+                # Artifact already exists (concurrent sync), just update it
+                db.rollback()
+                artifact = (
+                    db.query(ArchiveArtifact)
+                    .filter(
+                        ArchiveArtifact.archived_url_id == archived_url.id,
+                        ArchiveArtifact.archiver == archiver,
+                    )
+                    .first()
+                )
+                if artifact:
+                    artifact.status = archive_data.get("status", "pending")
+                    artifact.success = archive_data.get("success", False)

         db.commit()
```

**Alternative (ensure unique constraint):**
Add database constraint:

```sql
-- Migration
ALTER TABLE archive_artifacts
ADD CONSTRAINT archive_artifacts_archived_url_id_archiver_key
UNIQUE (archived_url_id, archiver);
```

**Test case:**
```python
def test_sync_idempotent():
    """Test that syncing same article twice is idempotent."""
    item_id = "test-article"

    # Sync once
    response1 = client.post("/api/v1/sync/import", json={"item_id": item_id})
    assert response1.status_code == 200

    # Sync again (should not create duplicates)
    response2 = client.post("/api/v1/sync/import", json={"item_id": item_id})
    assert response2.status_code == 200

    # Should have exactly ONE archived URL and N artifacts
    with db_session() as db:
        urls = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).all()
        assert len(urls) == 1

        artifacts = db.query(ArchiveArtifact).filter(
            ArchiveArtifact.archived_url_id == urls[0].id
        ).all()
        # Each archiver should appear exactly once
        archivers = [a.archiver for a in artifacts]
        assert len(archivers) == len(set(archivers)), "Duplicate artifacts found"
```

---

### CR-8: Incomplete Task Status Mapping Logic [MED]

**Location:** `services/api-gateway/app/routes/tasks.py:72-82`

**Invariant Violated:**
- "Task status should accurately reflect artifact state"
- Status mapping has gaps for edge cases

**Evidence:**
```python
# Lines 72-82 - Status determination logic
for artifact, archived_url in artifacts:
    status = artifact.status or "pending"

    if artifact.success:
        status = "success"
        completed += 1
    elif status == "failed" or (artifact.exit_code and artifact.exit_code != 0):
        status = "failed"
        failed += 1
    else:
        pending += 1
        # ❌ What if artifact.success=False but status="completed"?
        # ❌ What if exit_code=0 but success=False (partial failure)?
```

**Failure Scenario:**
```python
# Artifact state: success=False, status="processing", exit_code=None
# → Mapped to status="processing" (not "pending", "success", or "failed")
# → But counting logic only counts pending/completed/failed
# → This artifact not counted properly

# Result in overall status calculation (lines 96-107):
total = len(items)  # 10
completed = 5
failed = 2
pending = 2  # Missing 1 artifact!

# total (10) != completed (5) + failed (2) + pending (2) = 9
# → Off by one error in progress calculation
```

**Impact:**
- Inaccurate task progress reporting
- Status never reaches "completed" (stuck at 99%)
- User confusion about task state
- Monitoring alerts on incorrect status

**Severity:** MED
**Confidence:** Med (depends on actual artifact states in production)
**Category:** State Transition + Edge Cases

**Smallest Fix:**
Ensure all artifacts are counted:

```diff
--- a/services/api-gateway/app/routes/tasks.py
+++ b/services/api-gateway/app/routes/tasks.py
@@ -69,17 +69,25 @@ async def get_task_status(
     completed = 0
     failed = 0
     pending = 0
+    unknown = 0

     for artifact, archived_url in artifacts:
-        status = artifact.status or "pending"
-
-        if artifact.success:
+        # Definitive success
+        if artifact.success == True:
             status = "success"
             completed += 1
-        elif status == "failed" or (artifact.exit_code and artifact.exit_code != 0):
+        # Definitive failure
+        elif artifact.success == False or (artifact.exit_code and artifact.exit_code != 0):
             status = "failed"
             failed += 1
+        # Still processing
+        elif artifact.status in ("pending", "processing", "queued"):
+            status = artifact.status
+            pending += 1
+        # Unknown state
         else:
+            status = "unknown"
+            unknown += 1
+            logger.warning(f"Unknown artifact state: success={artifact.success}, status={artifact.status}, exit_code={artifact.exit_code}")
-            pending += 1

         items.append(...)

@@ -95,7 +103,7 @@ async def get_task_status(
     total = len(items)
     if total == 0:
         overall_status = "pending"
         progress = 0.0
-    elif pending > 0:
+    elif pending > 0 or unknown > 0:
         overall_status = "in_progress"
         progress = (completed + failed) / total * 100
```

**Test case:**
```python
def test_task_status_all_states_counted():
    """Test that all artifact states are properly counted."""
    # Create artifacts in various states
    # success=True, status="completed" → "success"
    # success=False, status="failed" → "failed"
    # success=None, status="pending" → "pending"
    # success=None, status="processing" → "pending"
    # success=None, status="unknown" → "unknown"

    response = client.get("/api/v1/tasks/test-task-123")

    data = response.json()
    # Verify counts add up
    assert len(data["items"]) == data["completed"] + data["failed"] + data["pending"] + data.get("unknown", 0)
```

---

### CR-9: Invalid Archiver Returns 400 (Good - No Issue) [LOW]

**Location:** `services/api-gateway/app/routes/archives.py:163-168`

**Evidence:**
```python
# Lines 163-168 - Archiver validation
invalid = [a for a in archivers if a not in AVAILABLE_ARCHIVERS]
if invalid:
    raise HTTPException(
        status_code=400,  # ✅ Correct status code
        detail=f"Invalid archivers: {invalid}. Valid options: {AVAILABLE_ARCHIVERS}",
    )
```

**Assessment:**
✅ This is CORRECT behavior. Invalid input should return 400 (Bad Request).

**Severity:** LOW (not actually an issue, just noting good validation)
**Confidence:** High
**Category:** Input Validation

---

### CR-10: Empty Task List Edge Case [LOW]

**Location:** `services/api-gateway/app/routes/tasks.py:95-107`

**Evidence:**
```python
# Lines 95-107 - Progress calculation
total = len(items)
if total == 0:
    overall_status = "pending"
    progress = 0.0
elif pending > 0:
    overall_status = "in_progress"
    progress = (completed + failed) / total * 100
elif failed == total:
    overall_status = "failed"
    progress = 100.0
else:
    overall_status = "completed"
    progress = 100.0
```

**Potential Issue:**
If `total == 0` (no artifacts found), status is "pending" but that's misleading - task doesn't exist or has no items.

**Failure Scenario:**
```python
GET /api/v1/tasks/nonexistent-task-id
# Query returns 0 artifacts
# Status: "pending", progress: 0.0
# ❌ Misleading: Task doesn't exist, not "pending"
```

**Impact:**
- Misleading status for nonexistent tasks
- User confusion (waiting for task that doesn't exist)

**Severity:** LOW
**Confidence:** Med
**Category:** Boundary Condition

**Fix:**
Return 404 if no artifacts found:

```diff
--- a/services/api-gateway/app/routes/tasks.py
+++ b/services/api-gateway/app/routes/tasks.py
@@ -62,7 +62,10 @@ async def get_task_status(
     )

     if not artifacts:
-        raise HTTPException(status_code=404, detail="Task not found")
+        # Return 404 instead of empty result
+        raise HTTPException(
+            status_code=404,
+            detail=f"Task not found: {task_id}"
+        )
```

---

## 4) Invariants Coverage Analysis

Analysis of how well invariants are enforced:

| Invariant | Enforcement | Gaps |
|-----------|-------------|------|
| Data integrity (ArchivedUrl before Artifact) | ✅ Enforced | Foreign key constraint prevents violations |
| Idempotency (skip existing archives) | ⚠️ Partial | CR-2: Race condition allows duplicates |
| Concurrency (row locking) | ❌ Broken | CR-2: TOCTOU race, lock too late |
| Transaction safety (atomic commits) | ❌ Missing | CR-3: Commit before task dispatch |
| File cleanup (only after upload) | ✅ Good | Checks `all_uploads_succeeded` flag |
| Rate limiting | ✅ Good | All endpoints have rate limiters |
| Error status codes | ✅ Good | Proper 4xx/5xx distinction |
| Task ID uniqueness | ✅ Good | UUIDs generated per workflow |
| Max batch size | ❌ Missing | CR-1: No limit, DoS risk |
| File size limits | ❌ Missing | CR-4: No validation, OOM risk |
| CORS origin restrictions | ❌ Missing | CR-5: Allows all origins |

**Recommendations:**
1. Add database unique constraints for (archived_url_id, archiver) to prevent races
2. Move db.commit() after Celery dispatch to ensure atomicity
3. Add max_items limit on CreateArchiveRequest
4. Configure CORS from environment variables
5. Add file size checks in workers

---

## 5) Edge Cases Coverage

| Edge Case | Handled? | Evidence |
|-----------|----------|----------|
| Empty batch (items=[]) | ✅ Yes | min_items=1 in Pydantic model |
| Large batch (1000+ items) | ❌ No | CR-1: No max_items limit |
| Duplicate URL in batch | ✅ Yes | Idempotency check skips existing |
| Concurrent requests for same URL | ❌ No | CR-2: Race condition |
| Celery dispatch failure | ❌ No | CR-3: No rollback |
| File deletion permission error | ⚠️ Partial | CR-6: Logged but DB inconsistent |
| Invalid archiver name | ✅ Yes | Returns 400 with error message |
| Firestore not configured | ✅ Yes | Returns 400 "Firestore not configured" |
| Database connection failure | ✅ Yes | Health check reports degraded |
| Worker crash mid-task | ✅ Yes | Artifact stays "pending", can retry |
| Huge file download (OOM) | ❌ No | CR-4: No size validation |
| Task ID not found | ✅ Yes | Returns 404 |
| Empty task (0 artifacts) | ⚠️ Partial | CR-10: Returns "pending" not 404 |

**Recommendations:**
1. Add comprehensive edge case tests
2. Add stress tests for large batches
3. Add concurrency tests with ThreadPoolExecutor
4. Document supported file size limits
5. Add monitoring for "pending forever" artifacts

---

## 6) Error Handling Assessment

**Error Handling Patterns Found:**
- HTTPException for client/server errors (good)
- Try/catch with logging (good)
- Transaction commits before external calls (CR-3 - bad)
- File deletion errors logged but DB updated (CR-6 - bad)

**Good Practices:**
✅ Proper HTTP status codes (400 for client errors, 500 for server errors)
✅ Detailed error messages with context
✅ Error logging with structured logging (extra={})
✅ Rate limiting on all endpoints
✅ Health check endpoint for monitoring

**Missing:**
❌ Rollback on external call failures (CR-3)
❌ Transaction retry logic for deadlocks
❌ Circuit breaker for Firestore/GCS failures
❌ Error metrics/alerting
❌ Graceful degradation (e.g., sync continues if Firestore unavailable)

**Recommendations:**
1. Add rollback logic for failed Celery dispatches
2. Add transaction retry decorator for deadlocks
3. Add circuit breaker for external services
4. Add error rate metrics to Prometheus
5. Make Firestore optional (warn but don't fail)

---

## 7) Concurrency & Race Conditions

**Shared State:**
- Database connections: ✅ Pool managed correctly by SQLAlchemy
- Celery tasks: ✅ Each task has unique signature
- File system: ⚠️ Multiple workers may access same files

**Async Patterns:**
- All endpoints use FastAPI async/await ✅
- Database queries are synchronous (SQLAlchemy ORM) ✅
- Celery dispatch is async ✅

**Race Conditions Found:**
- CR-2: TOCTOU race in ArchivedUrl creation
- Potential race: Two workers processing same artifact (handled by DB locking)
- Potential race: File deletion during upload (not checked)

**Recommendations:**
1. Fix CR-2 with proper row locking or unique constraints
2. Add file locking for concurrent access
3. Use distributed locks (Redis) for cross-worker coordination
4. Add transaction isolation level configuration

---

## 8) Test Coverage Gaps

Based on findings, missing tests:

**Critical (should add):**
- [ ] Test max batch size validation (CR-1)
- [ ] Test concurrent archive creation for same URL (CR-2)
- [ ] Test rollback on Celery dispatch failure (CR-3)
- [ ] Test CORS origin restrictions (CR-5)
- [ ] Test file size validation (CR-4)

**Important (nice to have):**
- [ ] Test file deletion rollback on error (CR-6)
- [ ] Test Firestore sync idempotency (CR-7)
- [ ] Test task status edge cases (CR-8, CR-10)
- [ ] Test rate limiting enforcement
- [ ] Test transaction retry on deadlock

**Integration Tests:**
- [ ] End-to-end archive workflow (API → Celery → Storage)
- [ ] Concurrent request stress test
- [ ] Large batch stress test (100+ items)
- [ ] Worker crash recovery test
- [ ] Database failover test

---

## 9) Recommendations

### Must Fix (BLOCKER/HIGH)

1. **CR-1**: Add max batch size validation
   - Action: Add `max_items=100` to CreateArchiveRequest.items
   - Rationale: Prevents DoS and resource exhaustion
   - Estimated effort: 10 minutes
   - File: `archives.py:77`

2. **CR-2**: Fix race condition in ArchivedUrl creation
   - Action: Add unique constraint + IntegrityError handling OR move lock earlier
   - Rationale: Prevents duplicate records and data corruption
   - Estimated effort: 30 minutes
   - File: `archives.py:184-203`

3. **CR-3**: Add rollback on Celery dispatch failure
   - Action: Move db.commit() after apply_async(), add try/except
   - Rationale: Prevents orphaned database records
   - Estimated effort: 20 minutes
   - File: `archives.py:260-301`

4. **CR-4**: Add file size validation (in workers)
   - Action: Check Content-Length before downloading
   - Rationale: Prevents OOM crashes
   - Estimated effort: 1 hour (requires worker code changes)
   - File: Worker code (not in API gateway)

5. **CR-5**: Fix CORS configuration
   - Action: Configure allowed origins from environment
   - Rationale: Prevents CSRF/XSS attacks
   - Estimated effort: 15 minutes
   - File: `main.py:85-91`

### Should Fix (MED)

6. **CR-6**: Fix file deletion rollback logic
   - Action: Only mark as deleted if unlink succeeds
   - Rationale: Maintains database-filesystem consistency
   - Estimated effort: 15 minutes
   - File: `artifacts.py:304-338`

7. **CR-7**: Make Firestore sync idempotent
   - Action: Add IntegrityError handling for duplicate artifacts
   - Rationale: Allows safe retries
   - Estimated effort: 20 minutes
   - File: `sync.py:416-445`

8. **CR-8**: Improve task status mapping
   - Action: Handle all possible artifact states
   - Rationale: Accurate progress reporting
   - Estimated effort: 15 minutes
   - File: `tasks.py:72-107`

### Consider (LOW/NIT)

9. **CR-10**: Return 404 for nonexistent tasks
   - Action: Already returns 404 (line 64), but improve message
   - Rationale: Better error messages
   - Estimated effort: 5 minutes
   - File: `tasks.py:64`

### Overall Strategy

**If time is limited (quick fixes for deployment):**
- Fix CR-1, CR-3, CR-5 (30-45 minutes total)
- Ship with known issues documented
- Address CR-2, CR-4, CR-6, CR-7 in next iteration

**If time allows (thorough fixes):**
- Fix all HIGH issues (CR-1 through CR-5) in one PR
- Add tests for each fix
- Add integration tests for concurrent scenarios
- Deploy with confidence

**Long-term improvements:**
- Add comprehensive test suite
- Add load testing for batch operations
- Add monitoring and alerting for "stuck pending" artifacts
- Add distributed tracing for debugging
- Document operational runbooks

---

## 10) False Positives & Disagreements Welcome

**Where I might be wrong:**

1. **CR-2 (Race condition)**: If there's a database unique constraint on `ArchivedUrl.url` that I didn't see in the code, the race condition might already be handled at the database level. Check schema migrations.

2. **CR-4 (File size)**: If the worker code already validates file sizes (I didn't review worker code in this review), then this isn't an API Gateway issue. However, pre-checking in API Gateway is still good defense-in-depth.

3. **CR-5 (CORS)**: If this service is behind a reverse proxy/API gateway that handles CORS, then the FastAPI CORS config might be intentional. However, it's safer to be explicit.

4. **CR-8 (Task status)**: The incomplete status mapping might be intentional if those edge cases don't occur in practice. Review production logs to verify.

5. **Severity ratings**: I rated issues based on worst-case scenarios. In practice, if this is not a high-traffic service or not internet-facing, some HIGH issues might be MED.

**How to override my findings:**
- Show database schema with unique constraints I missed
- Provide worker code that validates file sizes
- Explain CORS setup (reverse proxy handles it)
- Show production metrics proving edge cases don't occur
- Provide context on service traffic patterns

I'm optimizing for production safety and correctness. If there's a good reason the code is safe despite my findings, let's discuss!

---

## 11) Additional Observations

**Positive Findings:**
1. ✅ Good use of Pydantic models for request/response validation
2. ✅ Comprehensive rate limiting on all endpoints
3. ✅ Structured logging with context (extra={})
4. ✅ Health check endpoint for monitoring
5. ✅ Proper async/await usage throughout
6. ✅ Good code organization (separate files per domain)
7. ✅ Idempotency checks for archive operations
8. ✅ Row-level locking attempt (despite TOCTOU issue)

**Architecture Strengths:**
1. Clean separation between API gateway and workers
2. Celery for async task processing
3. Dual persistence (PostgreSQL + Firestore) for different use cases
4. RESTful API design with clear endpoint naming
5. FastAPI with automatic OpenAPI docs

**Technical Debt Notes:**
1. No integration tests found (deleted in Checkpoint 6)
2. Worker code not reviewed (may have issues)
3. No database migration files reviewed
4. No monitoring/observability setup reviewed
5. Firestore sync is complex and needs more testing

---

*Review completed: 2026-01-16*
*Session: [simplify-api-endpoints](../README.md)*
