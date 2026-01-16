# API Endpoint Enumeration

**Generated:** 2026-01-16
**Purpose:** Complete inventory of all API endpoints across monolith and microservices

---

## Architecture Overview

The application currently has **two parallel API implementations**:

1. **Monolith API** (`app/api/`) - Original single-server FastAPI application
2. **Microservices API Gateway** (`services/api-gateway/app/routes/`) - New distributed architecture

This creates significant duplication and complexity.

---

## Complete Endpoint Inventory

### 1. Health & System (`app/api/misc.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Health check |

**Notes:** Simple, no duplication

---

### 2. HyperTerm Integration (`app/api/ht.py`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/ht/send` | Send command to HyperTerm runner |

**Notes:** Specialized integration, likely low traffic

---

### 3. Command History (`app/api/commands.py`)

| Method | Path | Purpose | Lines |
|--------|------|---------|-------|
| GET | `/commands/executions` | List command executions with filtering | 46-85 |
| GET | `/commands/executions/{execution_id}` | Get execution detail with full output | 88-128 |
| GET | `/commands/executions/{execution_id}/replay` | Replay command execution | 131-148 |

**Notes:** Command history and replay functionality, unique to monolith

---

### 4. Archive/Save Operations (Monolith `app/api/saves.py`)

**Core Archive Endpoints:**

| Method | Path | Purpose | Lines |
|--------|------|---------|-------|
| POST | `/archive/{archiver}` | Archive URL with specific archiver | 313-323 |
| POST | `/archive/retrieve` | Retrieve archived content | 326-501 |
| POST | `/save` | Default save (all archivers, async) | 503-530 |
| POST | `/archive/{archiver}/batch` | Batch archive with archiver | 533-562 |
| POST | `/save/batch` | Batch save (all archivers, async) | 565-575 |
| GET | `/archive/{archived_url_id}/size` | Get archive size stats | 578-611 |

**Admin Endpoints:**

| Method | Path | Purpose | Lines |
|--------|------|---------|-------|
| GET | `/saves` | List saves with pagination | 47-98 |
| GET | `/archivers` | List available archivers | 101-104 |
| POST | `/saves/requeue` | Requeue failed/pending saves | 107-180 |
| POST | `/summarize` | Trigger article summarization | 183-232 |
| DELETE | `/saves/{rowid}` | Delete save by rowid | 235-282 |
| DELETE | `/saves/by-item/{item_id}` | Delete saves by item_id | 285-331 |
| DELETE | `/saves/by-url` | Delete saves by URL | 334-379 |

**Key Features:**
- Paywall URL rewriting (lines 143-147)
- Skip existing saves logic (lines 172-240)
- Storage provider integration (lines 243-250)
- Lazy Firestore migration (lines 348-386)
- Multi-provider file serving (lines 409-427)

---

### 5. Firebase/Firestore Integration (Monolith `app/api/firebase.py`)

| Method | Path | Purpose | Status | Lines |
|--------|------|---------|--------|-------|
| POST | `/firebase/add-pocket-article` | Add Pocket article | **DEPRECATED** | 69-209 |
| GET | `/firebase/download/{item_id}/{archiver}` | Generate signed download URL | Active | 212-328 |
| POST | `/firebase/save` | Save basic article | **DEPRECATED** | 331-412 |
| POST | `/firebase/archive` | Archive article (Cloud Function trigger) | **DEPRECATED** | 415-544 |

**Notes:** Three endpoints marked deprecated, migrate to microservices API

---

### 6. Sync Operations (Monolith `app/api/sync.py`)

| Method | Path | Purpose | Lines |
|--------|------|---------|-------|
| POST | `/sync/postgres-to-firestore` | Sync PostgreSQL → Firestore | 49-223 |
| POST | `/sync/firestore-to-postgres` | Sync Firestore → PostgreSQL | 226-351 |

**Notes:** Bidirectional database sync for dual-persistence mode

---

### 7. Task Status (Monolith `app/api/tasks.py`)

| Method | Path | Purpose | Lines |
|--------|------|---------|-------|
| GET | `/tasks/{task_id}` | Get task status with item details | 15-43 |

**Notes:** Task tracking for async archival operations

---

### 8. Admin Operations (Monolith `app/api/admin.py`)

Included in Section 4 (saves.py contains admin endpoints)

---

### 9. Firebase/Firestore (Microservices `services/api-gateway/app/routes/firebase.py`)

| Method | Path | Purpose | Status | Lines |
|--------|------|---------|--------|-------|
| GET | `/download/{item_id}/{archiver}` | Generate signed download URL | Active | 171-264 |
| POST | `/archive` | Archive article (Cloud Function) | Active | 267-388 |
| POST | `/add-article` | **NEW:** Consolidated add article | Active | 391-549 |

**Key Features:**
- Custom item_id validation (lines 112-120)
- Smart prefix selection (pocket vs article) (line 430)
- Celery task dispatch (lines 123-168)
- Firestore sync toggle (line 90)
- URL uniqueness constraint (line 434)

---

## Duplication Analysis

### Critical Duplications

1. **Firebase Archive Endpoint**
   - Monolith: `POST /firebase/archive` (deprecated)
   - Microservices: `POST /archive`
   - **Action:** Remove monolith version

2. **Download URL Generation**
   - Monolith: `GET /firebase/download/{item_id}/{archiver}`
   - Microservices: `GET /download/{item_id}/{archiver}`
   - **Action:** Consolidate to one path

3. **Add Article Operations**
   - Monolith:
     - `POST /firebase/add-pocket-article` (deprecated)
     - `POST /firebase/save` (deprecated)
   - Microservices: `POST /add-article` (consolidated)
   - **Action:** Remove both monolith endpoints

---

## Endpoint Count Summary

### Monolith API (`app/api/`)
- **Health:** 1 endpoint
- **HyperTerm:** 1 endpoint
- **Commands:** 3 endpoints
- **Saves/Archive:** 13 endpoints
- **Firebase:** 4 endpoints (3 deprecated)
- **Sync:** 2 endpoints
- **Tasks:** 1 endpoint
- **TOTAL:** 25 endpoints

### Microservices API Gateway (`services/api-gateway/app/routes/firebase.py`)
- **Firebase:** 3 endpoints
- **TOTAL:** 3 endpoints

### Grand Total: 28 unique endpoint paths (with 3 deprecated + functional duplicates)

---

## Complexity Hotspots

### High Complexity Endpoints

1. **`/archive/retrieve`** (saves.py:326-501) - 175 lines
   - Handles single archiver retrieval
   - Handles "all" archivers (tar.gz bundle)
   - Storage provider fallback logic
   - Lazy Firestore migration
   - Temporary file cleanup

2. **`_archive_with()`** helper (saves.py:98-310) - 212 lines
   - URL rewriting for paywalls
   - Pre-flight URL checks (404 detection)
   - Skip existing saves logic (DB + filesystem)
   - Storage integration
   - Summarization scheduling
   - Per-archiver sequential execution

3. **`/sync/postgres-to-firestore`** (sync.py:49-223) - 174 lines
   - Single article sync
   - Batch article sync
   - Artifact mapping
   - Error collection

---

## Patterns & Conventions

### Naming Inconsistencies

1. **Path Prefixes:**
   - Monolith uses `/firebase/*` for Firebase endpoints
   - Microservices uses no prefix (cleaner)

2. **Resource Naming:**
   - Monolith: `/saves`, `/archive`, `/summarize`
   - Inconsistent singular/plural

3. **Parameter Naming:**
   - `item_id` vs `id` vs `rowid`
   - `archived_url_id` vs `article_id`

### Good Patterns to Keep

1. **Storage Provider Abstraction** (saves.py:243-250, 409-427)
   - Clean separation of concerns
   - Multiple provider support
   - Graceful fallback

2. **Pydantic Models** (Throughout)
   - Strong typing
   - Request/response validation
   - API documentation

3. **Repository Pattern** (saves.py:35-37)
   - Database access abstraction
   - Testable

### Anti-Patterns to Remove

1. **Deprecated Endpoints Still Functional** (firebase.py:69-544)
   - Should return 410 Gone immediately
   - Or redirect to new endpoints

2. **Business Logic in Route Handlers** (saves.py:98-310)
   - Should be in service layer
   - Hard to test

3. **Parallel Implementations**
   - Monolith + Microservices overlap
   - Increases maintenance burden

---

## Dependencies & Integration Points

### External Dependencies

- **Firestore:** 7 endpoints depend on Firestore
- **PostgreSQL:** All endpoints depend on PostgreSQL
- **GCS:** 2 endpoints generate signed URLs
- **Celery:** Microservices use Celery for async tasks
- **Task Manager:** Monolith uses ArchiverTaskManager

### Client Usage Patterns

Based on code analysis:

1. **Mobile App:** Uses Firebase endpoints
2. **Browser Extension:** Uses `/save` and `/archive` endpoints
3. **Admin UI:** Uses `/saves`, `/summarize`, delete endpoints
4. **Cloud Functions:** Call `/firebase/archive`

---

## Recommendations for Simplification

### Phase 1: Remove Deprecated Endpoints (Low Risk)
- Delete `/firebase/add-pocket-article`
- Delete `/firebase/save`
- Delete monolith `/firebase/archive` (keep microservices version)

**Impact:** Remove 3 endpoints immediately

### Phase 2: Consolidate Duplicates (Medium Risk)
- Standardize download URL endpoint path
- Choose one implementation (microservices preferred)
- Add redirects from old paths

**Impact:** Reduce by 2-3 endpoints

### Phase 3: Refactor Complex Endpoints (High Complexity)
- Extract `/archive/retrieve` logic to service layer
- Break down `_archive_with()` helper
- Simplify skip-existing logic

**Impact:** Improve maintainability, no API changes

### Phase 4: Standardize Naming (Medium Risk)
- Use consistent resource names
- Standardize parameter names across endpoints
- Version the API (v1, v2) to allow migration

**Impact:** Better developer experience

---

## Next Steps

1. Validate client usage of deprecated endpoints
2. Create deprecation timeline
3. Build redirect layer for renamed endpoints
4. Write migration guide for API consumers
