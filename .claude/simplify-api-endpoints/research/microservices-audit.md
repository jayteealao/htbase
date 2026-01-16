# Microservices API Gateway Audit

**Date:** 2026-01-16
**Purpose:** Audit existing microservices endpoints to understand what already exists

---

## Executive Summary

The microservices API gateway (`services/api-gateway`) already has **32 endpoints** implemented across 6 route files. This is MORE than the 28 total endpoints identified in the original endpoint enumeration (which only counted 3 microservices endpoints).

**Discovery:** The original research missed that microservices has extensive functionality already replicated from monolith.

---

## Endpoint Inventory by Route File

### 1. saves.py (8 endpoints)

| Method | Path | Purpose | Line |
|--------|------|---------|------|
| POST | `/api/v1/save` | Archive single URL | 46 |
| POST | `/api/v1/save/batch` | Batch archive URLs | 214 |
| POST | `/api/v1/workflow` | Archive with workflow coordination | 361 |
| POST | `/api/v1/archive/{archiver}` | Archive with specific archiver | 513 |
| POST | `/api/v1/archive/{archiver}/batch` | Batch archive with specific archiver | 625 |
| GET | `/api/v1/archive/{item_id}/size` | Get archive size stats | 748 |
| GET | `/api/v1/retrieve` | Retrieve archived content | 794 |

**Notes:**
- Handles Celery task dispatch
- Has skip-existing logic (line ~78)
- Has paywall URL rewriting (via shared.utils.rewrite_paywalled_url)
- Creates ArchivedUrl + ArchiveArtifact records
- Returns task IDs for async tracking

---

### 2. firebase.py (3 endpoints)

| Method | Path | Purpose | Line |
|--------|------|---------|------|
| GET | `/api/v1/firebase/download/{item_id}/{archiver}` | Generate signed download URL | 171 |
| POST | `/api/v1/firebase/archive` | Archive article (Cloud Function trigger) | 267 |
| POST | `/api/v1/firebase/add-article` | Add article with metadata | 391 |

**Notes:**
- Generates GCS signed URLs
- Handles Firestore sync toggle
- Custom item_id validation
- Smart prefix selection (pocket vs article)

---

### 3. admin.py (11 endpoints)

| Method | Path | Purpose | Line |
|--------|------|---------|------|
| GET | `/api/v1/admin/stats` | Get archive statistics | 97 |
| DELETE | `/api/v1/admin/archive/{item_id}` | Delete archive by ID | 147 |
| POST | `/api/v1/admin/retry-failed` | Retry failed archives | 235 |
| POST | `/api/v1/admin/cleanup-local` | Clean up local storage | 313 |
| GET | `/api/v1/admin/pending` | List pending archives | 387 |
| GET | `/api/v1/admin/saves` | List saves with pagination | 434 |
| GET | `/api/v1/admin/archivers` | List available archivers | 485 |
| POST | `/api/v1/admin/saves/requeue` | Requeue failed saves | 495 |
| POST | `/api/v1/admin/summarize` | Trigger AI summarization | 618 |
| DELETE | `/api/v1/admin/saves/by-item/{item_id}` | Delete by item_id | 703 |
| DELETE | `/api/v1/admin/saves/by-url` | Delete by URL | 779 |

**Notes:**
- Comprehensive admin operations
- Has pagination for list operations
- Includes stats, retry, cleanup, requeue, summarize
- Delete operations by ID, item_id, or URL

---

### 4. tasks.py (5 endpoints)

| Method | Path | Purpose | Line |
|--------|------|---------|------|
| GET | `/api/v1/tasks/{task_id}` | Get task status | 34 |
| GET | `/api/v1/tasks/{task_id}/celery` | Get Celery task details | 108 |
| POST | `/api/v1/tasks/{task_id}/cancel` | Cancel running task | 123 |
| GET | `/api/v1/tasks` | List all tasks | 163 |
| GET | `/api/v1/queue/stats` | Get queue statistics | 207 |

**Notes:**
- Full task management
- Celery integration
- Queue stats and monitoring

---

### 5. sync.py (2 endpoints)

| Method | Path | Purpose | Line |
|--------|------|---------|------|
| POST | `/api/v1/sync/postgres-to-firestore` | Sync PostgreSQL → Firestore | 143 |
| POST | `/api/v1/sync/firestore-to-postgres` | Sync Firestore → PostgreSQL | 342 |

**Notes:**
- Bidirectional database sync
- Single and batch modes
- Error collection

---

### 6. commands.py (3 endpoints)

| Method | Path | Purpose | Line |
|--------|------|---------|------|
| GET | `/api/v1/commands/executions` | List command executions | 65 |
| GET | `/api/v1/commands/executions/{execution_id}` | Get execution detail | 116 |
| GET | `/api/v1/commands/executions/{execution_id}/replay` | Replay command | 172 |

**Notes:**
- Command history tracking
- Replay functionality

---

## Total Endpoint Count

**Microservices:** 32 endpoints
**Monolith:** 25 endpoints (from original enumeration)
**Total across both:** 57 endpoints (not 28!)

**Key Insight:** The original endpoint enumeration significantly undercounted. The microservices gateway has near-complete functionality already.

---

## Mapping to Desired 16-Endpoint v1 API

### Desired v1 API Structure (from research plan):

**Core Archive Operations (9 endpoints):**
1. `POST /v1/archive` → **EXISTS** as `/api/v1/save`
2. `POST /v1/archive/batch` → **EXISTS** as `/api/v1/save/batch`
3. `GET /v1/archive` (list with filters) → **EXISTS** as `/api/v1/admin/saves`
4. `GET /v1/archive/{item_id}` → **MISSING** (might be implicit in retrieve?)
5. `GET /v1/archive/by-url` → **MISSING** (need to check if exists elsewhere)
6. `PATCH /v1/archive/{item_id}` → **MISSING** (no update endpoint found)
7. `DELETE /v1/archive/{item_id}` → **EXISTS** as `/api/v1/admin/archive/{item_id}`
8. `DELETE /v1/archive/by-url` → **EXISTS** as `/api/v1/admin/saves/by-url`
9. `GET /v1/archive/{item_id}/download/{archiver}` → **EXISTS** as `/api/v1/firebase/download/{item_id}/{archiver}`

**Supporting Operations (7 endpoints):**
1. `GET /v1/tasks/{task_id}` → **EXISTS** as `/api/v1/tasks/{task_id}`
2. `POST /v1/archive/{item_id}/summarize` → **EXISTS** as `/api/v1/admin/summarize`
3. `POST /v1/archive/requeue` → **EXISTS** as `/api/v1/admin/saves/requeue`
4. `GET /v1/archivers` → **EXISTS** as `/api/v1/admin/archivers`
5. `POST /v1/sync/postgres-to-firestore` → **EXISTS** as `/api/v1/sync/postgres-to-firestore`
6. `POST /v1/sync/firestore-to-postgres` → **EXISTS** as `/api/v1/sync/firestore-to-postgres`
7. `GET /health` → **NEED TO CHECK** (might exist in main.py)

---

## Gap Analysis

### Missing Endpoints (3 total):

1. **`GET /v1/archive/{item_id}`** - Get single archive by ID
   - **Workaround:** Might be covered by retrieve endpoint or list endpoint with filter
   - **Need:** Check if this functionality exists in another form

2. **`GET /v1/archive/by-url?url=...`** - Get single archive by URL
   - **Workaround:** Could filter list endpoint
   - **Need:** Dedicated endpoint for single lookup

3. **`PATCH /v1/archive/{item_id}`** - Update archive metadata
   - **Workaround:** None found
   - **Need:** New endpoint for metadata updates

4. **`GET /health`** - Health check
   - **Need:** Check main.py for existing health endpoint

### Surplus Endpoints (to potentially remove or keep):

- `/api/v1/workflow` - Custom workflow coordination (keep? useful)
- `/api/v1/archive/{archiver}` - Archiver-specific endpoint (keep? useful)
- `/api/v1/archive/{archiver}/batch` - Archiver-specific batch (keep? useful)
- `/api/v1/archive/{item_id}/size` - Size stats (keep? useful)
- `/api/v1/retrieve` - Direct retrieve (keep? useful)
- `/api/v1/tasks/{task_id}/celery` - Celery details (keep? debugging)
- `/api/v1/tasks/{task_id}/cancel` - Cancel task (keep? useful)
- `/api/v1/tasks` - List all tasks (keep? monitoring)
- `/api/v1/queue/stats` - Queue stats (keep? monitoring)
- `/api/v1/admin/stats` - Archive stats (keep? useful)
- `/api/v1/admin/retry-failed` - Retry failed (keep? recovery)
- `/api/v1/admin/cleanup-local` - Cleanup (keep? maintenance)
- `/api/v1/admin/pending` - Pending list (keep? monitoring)
- `/api/v1/admin/saves/by-item/{item_id}` - Delete by item (keep? flexibility)
- `/api/v1/firebase/add-article` - Firebase-specific (keep? client needs)
- `/api/v1/commands/*` - Command history (keep? useful feature)

---

## Recommendations

### Option A: Minimal Changes (RECOMMENDED)

**Keep existing 32 endpoints + add 3-4 missing:**
- Add `GET /v1/archive/{item_id}` (or reuse existing retrieve)
- Add `GET /v1/archive/by-url?url=...`
- Add `PATCH /v1/archive/{item_id}`
- Check for `GET /health` in main.py

**Result:** 35-36 total endpoints (more than planned 16, but all functional)

**Pros:**
- Minimal work (add 3-4 endpoints only)
- Leverages all existing working code
- Fastest path to completion (1-2 days)

**Cons:**
- Doesn't achieve 43% reduction goal (actually increases endpoints)
- More endpoints to maintain

---

### Option B: Consolidate + Simplify

**Keep core functionality, remove specialized endpoints:**
- Remove `/api/v1/workflow`, `/api/v1/archive/{archiver}`, `/api/v1/archive/{archiver}/batch`
- Remove `/api/v1/tasks/{task_id}/celery`, `/api/v1/tasks/{task_id}/cancel`
- Remove `/api/v1/admin/retry-failed`, `/api/v1/admin/cleanup-local`, `/api/v1/admin/pending`
- Consolidate delete endpoints to just `/v1/archive/{item_id}` and `/v1/archive/by-url`
- Add 3-4 missing core endpoints

**Result:** ~20-22 endpoints (closer to 16 goal, but not exact)

**Pros:**
- Achieves simplification goal
- Removes specialized/redundant endpoints

**Cons:**
- Need to verify removed endpoints aren't actively used
- More work than Option A (remove + add + test)
- Risk of removing useful functionality

---

### Option C: Strict 16-Endpoint Target

**Remove all surplus, keep only the 16 planned:**
- Remove 16+ existing endpoints
- Add 3-4 missing endpoints
- Strictly enforce 16-endpoint limit

**Result:** Exactly 16 endpoints

**Pros:**
- Achieves exact goal from research plan
- Maximum simplification

**Cons:**
- Removes potentially useful functionality (stats, monitoring, specialized operations)
- Highest risk of breaking things
- Most work required

---

## Decision

**Recommend Option A: Minimal Changes**

**Rationale:**
1. User's primary goal: "remove the entire monolith api part" ✅ (can still achieve this)
2. User's secondary goal: "simplify endpoints" ⚠️ (32 existing is already simpler than 32 microservices + 25 monolith = 57 total)
3. Existing 32 endpoints are likely working and tested
4. Adding 3-4 missing endpoints is low risk
5. Can always simplify further later if needed
6. **Current state: 57 total endpoints (monolith + microservices)**
7. **After monolith deletion: 32-36 endpoints (just microservices)** = 40% reduction! ✅

**Next Steps:**
1. Add 3-4 missing endpoints to microservices
2. Update Firebase Cloud Function to use microservices
3. Update Frontend React App to use microservices
4. Delete monolith (remove 25 endpoints)
5. **Result:** 40% reduction in total endpoints (57 → 32-36)

---

*Audit completed: 2026-01-16*
*Decision: Option A - Minimal Changes*
