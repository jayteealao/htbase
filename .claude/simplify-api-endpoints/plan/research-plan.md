# Research + Plan: Simplify API Endpoints [Full]

---
command: /research-plan
session_slug: simplify-api-endpoints
date: 2026-01-16
milestone: full
work_type: refactor
scope: repo
target: .
risk_tolerance: medium
assumptions_allowed: yes
related:
  session: ../README.md
  endpoint_enumeration: ../research/endpoint-enumeration.md
  web_research: ../research/web-research.md
  codebase_mapper: ../research/codebase-mapper.md
---

## 0) Task Classification

**Work Type:** refactor

**Scope/Target:** repo / .

**Inputs Summarized:**
- Need to drastically simplify the number of API endpoints
- **NOT in production** - can make breaking changes
- Remove entire monolith (`app/api/`) and centralize on microservices API gateway
- Build clean REST API with minimal endpoints: create/archive, list, get, delete, update
- Only 2 clients to update: Firebase Cloud Function and Frontend React app
- Reduce from 28 → 16 endpoints (43% reduction)

**Constraints:**
- None (NOT in production, breaking changes acceptable)
- Must update Firebase Cloud Function to use new endpoints
- Must update Frontend React app to use new endpoints
- All existing functionality must be preserved (download, async, both DBs, summarization, sync, admin)

**Non-Goals:**
- Gradual migration or strangler pattern (no need - not in production)
- Backward compatibility layer or deprecation timeline (no external users)
- Feature flags or traffic shifting (no production traffic)
- Maintaining old endpoint paths (will delete monolith entirely)

**Success Criteria:**
1. API endpoint count reduced by 43% (28 → 16 endpoints)
2. Entire monolith (`app/api/`) deleted
3. Single clean microservices API with RESTful design
4. Firebase Cloud Function updated and working
5. Frontend React app updated and working
6. All tests passing (unit, integration, E2E, regression)
7. Implementation complete in 2-3 weeks
8. All existing functionality preserved (no regressions)

---

## 1) Facts / Assumptions / Unknowns

### Facts (Supported by Evidence)

**Endpoint Inventory**:
- **Monolith API** (`app/api/`): 25 endpoints across 8 files
  - Health: 1 endpoint (`/healthz`)
  - HyperTerm: 1 endpoint (`/ht/send`)
  - Commands: 3 endpoints (list, detail, replay)
  - Saves/Archive: 13 endpoints (archive, retrieve, batch, admin operations)
  - Firebase: 4 endpoints (3 marked deprecated)
  - Sync: 2 endpoints (PostgreSQL ↔ Firestore bidirectional)
  - Tasks: 1 endpoint (`/tasks/{task_id}`)

- **Microservices API Gateway** (`services/api-gateway/app/routes/firebase.py`): 3 endpoints
  - Download URL generation
  - Archive article (replacement for deprecated monolith endpoint)
  - Add article (consolidated replacement for 2 deprecated monolith endpoints)

- **Total**: 28 unique endpoint paths

**Deprecated Endpoints** (Source: `app/api/firebase.py`):
1. `POST /firebase/add-pocket-article` (lines 69-209) - marked deprecated in OpenAPI, logs warnings
2. `POST /firebase/save` (lines 331-412) - marked deprecated in OpenAPI, logs warnings
3. `POST /firebase/archive` (lines 415-544) - marked deprecated in OpenAPI, logs warnings

**Duplicate Implementations**:
1. **Firebase Archive**:
   - Monolith: `POST /firebase/archive` (deprecated, lines 415-544 in `app/api/firebase.py`)
   - Microservices: `POST /archive` (active, lines 267-388 in `services/api-gateway/app/routes/firebase.py`)

2. **Download URL Generation**:
   - Monolith: `GET /firebase/download/{item_id}/{archiver}` (lines 212-328 in `app/api/firebase.py`)
   - Microservices: `GET /download/{item_id}/{archiver}` (lines 171-264 in `services/api-gateway/app/routes/firebase.py`)

**Client Dependencies** (Source: codebase-mapper research):
- **Firebase Cloud Function** (`functions/index.js:97`): Uses deprecated `/firebase/archive` endpoint (HIGH RISK)
- **Frontend React App** (`frontend/src/api/`): Uses `/api/save/*` endpoints (SAFE, not deprecated)
- **Integration Tests** (`tests/integration/test_api_deprecation.py`): 4 tests verify deprecation markers

**Existing Patterns**:
- Pydantic models for request/response validation (consistent across codebase)
- Repository pattern for database access (`app/db/repositories.py`)
- Storage provider abstraction (`shared/storage/` directory)
- Feature flags mentioned but not systematically implemented
- Deprecation markers use `deprecated=True` in route decorators
- Migration guide exists at `docs/FIREBASE_API_MIGRATION.md`

### Assumptions (Explicit)

- **ASSUMPTION**: External API consumers exist beyond Firebase Cloud Function and frontend app
  - **Rationale**: Production API likely has undocumented clients (mobile apps, scripts, third-party integrations)
  - **Validation needed**: Monitor API access logs to identify all consumers

- **ASSUMPTION**: 12-18 month deprecation timeline is acceptable for this application
  - **Rationale**: Based on industry standards (Stripe uses 24 months, Twilio uses 12 months)
  - **Validation needed**: Confirm with stakeholders if faster timeline is required

- **ASSUMPTION**: Firebase Cloud Function can be updated within 1-2 weeks
  - **Rationale**: Single-file change (`functions/index.js:97`), straightforward migration
  - **Validation needed**: Check deployment pipeline and approval process

- **ASSUMPTION**: PostgreSQL is the primary database, Firestore is secondary/replica
  - **Rationale**: Code shows PostgreSQL writes followed by optional Firestore sync
  - **Validation needed**: Confirm data architecture and source of truth

- **ASSUMPTION**: Performance overhead of FastAPI as API gateway is acceptable
  - **Rationale**: No current performance issues mentioned, FastAPI is async and efficient
  - **Validation needed**: Load test FastAPI proxy performance vs direct calls

### Unknowns / Questions

**Critical Questions** (Affect plan significantly):

1. **What is the actual usage of deprecated endpoints?**
   - Need: Access logs showing requests per endpoint for last 30-90 days
   - Impact: Determines urgency and risk of deprecation
   - Action: Set up analytics/monitoring before proceeding

2. **Are there external API consumers beyond Firebase Cloud Function?**
   - Need: Complete list of API keys, client applications, integrations
   - Impact: Affects communication plan and timeline
   - Action: Query database for API keys, review integration documentation

3. **Can we afford to run both monolith and microservices during migration?**
   - Need: Infrastructure capacity and cost analysis
   - Impact: Affects strangler pattern implementation timeline
   - Action: Review hosting costs, resource utilization

4. **What is the acceptable downtime for endpoint changes?**
   - Need: SLA requirements, maintenance window availability
   - Impact: Determines whether we need zero-downtime deployment
   - Action: Review SLA agreements, confirm with stakeholders

**Non-Critical Questions** (Can be decided during implementation):

5. Should Firestore be kept as replica or fully migrated to PostgreSQL?
6. What monitoring/alerting should we set up for deprecated endpoint usage?
7. Should we version the entire API or just consolidated endpoints?
8. What testing strategy for parallel monolith/microservices validation?

---

## 2) Current System Snapshot (From Research)

### Codebase Analysis

**Endpoint Distribution**:
```
Monolith (app/api/):
├── misc.py          → 1 endpoint   (/healthz)
├── ht.py            → 1 endpoint   (/ht/send)
├── commands.py      → 3 endpoints  (command history and replay)
├── saves.py         → 13 endpoints (archive operations, admin)
├── firebase.py      → 4 endpoints  (3 deprecated)
├── sync.py          → 2 endpoints  (PostgreSQL ↔ Firestore)
└── tasks.py         → 1 endpoint   (/tasks/{task_id})

Microservices (services/api-gateway/):
└── routes/firebase.py → 3 endpoints (download, archive, add-article)

Total: 28 endpoints
```

**Complexity Hotspots** (lines of code):
1. `/archive/retrieve` handler in `saves.py` → 175 lines (326-501)
   - Handles single archiver retrieval
   - Handles "all" archivers (tar.gz bundle)
   - Storage provider fallback logic
   - Lazy Firestore migration
   - Temporary file cleanup

2. `_archive_with()` helper in `saves.py` → 212 lines (98-310)
   - URL rewriting for paywalls
   - Pre-flight URL checks (404 detection)
   - Skip existing saves logic (DB + filesystem)
   - Storage integration
   - Summarization scheduling
   - Per-archiver sequential execution

3. `/sync/postgres-to-firestore` in `sync.py` → 174 lines (49-223)
   - Single article sync
   - Batch article sync
   - Artifact mapping
   - Error collection

**Key Patterns Found**:

- **Naming Convention**: Inconsistent
  - Resource names: `/saves` (plural), `/archive` (singular), `/summarize` (verb)
  - Parameter names: `item_id` vs `id` vs `rowid` vs `archived_url_id`
  - Path prefixes: `/firebase/*` in monolith, no prefix in microservices

- **Error Handling**: Consistent HTTPException usage with status codes and detail messages

- **Authentication**: Not visible in analyzed files (likely middleware)

- **Database Access**: Repository pattern with transaction support

- **Storage Integration**: Well-abstracted with multiple provider support (local, GCS)

### Industry Best Practices (from web-research)

**Key Recommendations from Research**:

1. **Deprecation Timeline** (Source: Stripe, Twilio, Microsoft):
   - Phase 1 (Month 0): Announcement with headers
   - Phase 2 (Months 0-6): Active deprecation (200 OK + headers)
   - Phase 3 (Months 6-12): Sunset period (301 Redirect)
   - Phase 4 (Month 12+): Removal (410 Gone)

2. **HTTP Status Codes**:
   - During deprecation: `200 OK` with `Deprecation` and `Sunset` headers (RFC 8594, RFC 9745)
   - After sunset: `301 Moved Permanently` if content moved, `410 Gone` if removed
   - Never use: `404 Not Found` (implies accidental removal)

3. **API Versioning** (Source: FastAPI best practices, Azure, Stack Overflow):
   - Prefer URL path versioning (`/v1/`, `/v2/`) over header versioning for FastAPI
   - Use semantic versioning for breaking changes (major version bump)
   - Support N and N-1 major versions simultaneously
   - Only expose major version in URL path

4. **Endpoint Consolidation** (Source: Microsoft, Treblle, Stack Overflow):
   - Use query parameters for variations instead of separate endpoints
   - Avoid deep nesting (max 2 levels)
   - Resource-based URLs with consistent plural nouns for collections

5. **Strangler Fig Pattern** (Source: AWS, Confluent, Martin Fowler):
   - Route → Replace → Retire phases
   - Use routing facade/middleware to direct traffic
   - Keep instant rollback capability
   - Run parallel validation (shadow mode)

6. **Feature Flags** (Source: LaunchDarkly, PostHog, Harness):
   - Percentage-based rollout: 0.5% → 1% → 5% → 25% → 100%
   - Consistent hashing by user ID for sticky routing
   - Environment variable flags for quick rollback

7. **Database Migration** (Source: Google Cloud, Thorben Janssen):
   - Avoid dual-write pattern (consistency risks)
   - Use Outbox Pattern: write to outbox table in same transaction, separate process propagates
   - Alternative: Change Data Capture (CDC) with Debezium

8. **Celery Architecture** (Source: Reintech, Celery docs):
   - Separate task queues per microservice
   - Queue-based routing: `queue:monolith`, `queue:microservices`
   - Feature flags for gradual task migration

### Key Invariants and Contracts

**Must Not Change**:
- `/archive` and `/save` endpoints return 202 Accepted for async operations
- Task status endpoint returns `TaskStatusResponse` with `items` array
- Archived content retrieval returns binary file or tar.gz bundle
- All archive operations create database records in `archive_artifacts` table
- Storage paths follow pattern: `{data_dir}/{item_id}/{archiver}/{filename}`

**Database Constraints**:
- `archived_urls.url` is unique (enforced at DB level)
- `archived_urls.item_id` is unique (enforced at DB level)
- `archive_artifacts.archived_url_id` is foreign key to `archived_urls.id`
- PostgreSQL is source of truth for metadata

**External Dependencies**:
- Firestore (optional replica database)
- GCS (optional file storage)
- Celery + Redis (async task processing)
- Chromium (for PDF and screenshot archivers)
- Monolith binary (for HTML archiving)

### Dependencies & Touchpoints

**What calls what**:
```
Client Apps → FastAPI Server → Repositories → PostgreSQL
                            → Storage Providers → GCS / Local
                            → ArchiverTaskManager → Celery → Workers
                            → Firestore (optional)
```

**Changes will affect**:
- **Firebase Cloud Function**: Must update endpoint URL
- **API documentation**: OpenAPI spec, migration guides
- **Monitoring/logging**: May need new dashboards for v2 endpoints
- **Tests**: Integration tests may need updates
- **Infrastructure**: May need separate deployments for monolith/microservices

---

## 3) Options Considered

### Option 1: Direct Replacement (Remove Monolith, Build Clean API) ⭐ RECOMMENDED

**Summary:**
Delete entire monolith (`app/api/`) and build clean microservices API with 16 RESTful endpoints. Update 2 known clients (Firebase Cloud Function, Frontend React app). Complete in 2-3 weeks.

**Implementation Approach**:
1. Build new clean `/v1/` API in `services/api-gateway/` with 16 endpoints
2. Reuse existing business logic from monolith (extract to services)
3. Update Firebase Cloud Function to use new API (`functions/index.js:97`)
4. Update Frontend React app to use new API (`frontend/src/api/`)
5. Delete entire `app/api/` directory (monolith)
6. Deploy microservices API only

**Final API Structure (16 endpoints)**:
```python
# Core Archive Operations (9 endpoints)
POST   /v1/archive                          # Create archive
POST   /v1/archive/batch                    # Batch create
GET    /v1/archive                          # List (pagination + filtering)
GET    /v1/archive/{item_id}                # Get by ID
GET    /v1/archive/by-url?url=...           # Get by URL
PATCH  /v1/archive/{item_id}                # Update metadata
DELETE /v1/archive/{item_id}                # Delete by ID
DELETE /v1/archive/by-url?url=...           # Delete by URL
GET    /v1/archive/{item_id}/download/{archiver}  # Download

# Supporting Operations (7 endpoints)
GET    /v1/tasks/{task_id}                  # Task status
POST   /v1/archive/{item_id}/summarize      # Trigger summarization
POST   /v1/archive/requeue                  # Requeue failed
GET    /v1/archivers                        # List available archivers
POST   /v1/sync/postgres-to-firestore       # Sync P→F
POST   /v1/sync/firestore-to-postgres       # Sync F→P
GET    /health                              # Health check
```

**Pros:**
- ✅ Fast implementation (2-3 weeks total)
- ✅ Clean break from legacy code (no technical debt)
- ✅ Simple architecture (one API service)
- ✅ No deprecation complexity (not in production)
- ✅ Clear outcome (16 endpoints, RESTful design)
- ✅ Lower infrastructure cost (single service)

**Cons:**
- ❌ Must update all clients at once (2 clients total)
- ❌ No rollback to monolith after deletion
- ❌ Requires thorough testing before deployment

**Trade-offs:**
- **Complexity**: Medium (consolidation work) → Low (clean API after)
- **Risk**: Medium (breaking changes, but not in production)
- **Maintenance**: Low throughout (single codebase)
- **Scalability**: High (microservices architecture)
- **Cost**: Lower (single infrastructure)

**Codebase Fit**: 5/5 - Already have microservices started, can expand it

**Best Practice Fit**: 5/5 - RESTful design, clean architecture, follows FastAPI conventions

**When to Choose:**
- ✅ **NOT in production** (confirmed by user)
- ✅ Small number of known clients (2 clients: Firebase Function, Frontend)
- ✅ Team wants clean break from legacy (user wants to "remove entire monolith")
- ✅ Risk tolerance allows breaking changes (no production users)

---

### Option 2: Gradual Strangler Pattern Migration (Original Plan)

**Summary:**
Keep monolith, build microservices in parallel, use routing layer for gradual migration over 12-18 months. This was the original plan assuming production users.

**Implementation Approach**:
1. Create `/v2/` versioned endpoints with consolidated resource design
2. Implement FastAPI strangler proxy middleware to route traffic
3. Use feature flags for percentage-based rollout (0.5% → 100%)
4. Keep deprecated endpoints functional with 200 OK + headers for 6 months
5. Convert to 301 redirects for 6 months
6. Remove with 410 Gone after 12 months

**Pros:**
- ✅ Zero-downtime migration (safe for production)
- ✅ Instant rollback capability
- ✅ Industry-proven pattern (AWS, Netflix, Monzo)
- ✅ Gradual validation at each percentage

**Cons:**
- ❌ Long timeline (12-18 months)
- ❌ Maintains both codebases (higher maintenance)
- ❌ Complex routing layer needed
- ❌ Higher infrastructure cost (dual-running)

**Trade-offs:**
- **Complexity**: High
- **Risk**: Low
- **Timeline**: 12-18 months
- **Cost**: Higher

**Codebase Fit**: 5/5 - FastAPI supports middleware well

**Best Practice Fit**: 5/5 - Follows industry standards for production APIs

**When to Choose:**
- ❌ **Production system with active users** (NOT our case)
- ❌ **Need zero downtime** (NOT our case)
- ❌ **Unknown external clients** (NOT our case - only 2 known clients)

---

### Option 3: Minimal Refactoring (Status Quo+)

**Summary:**
Keep existing architecture largely intact. Only remove the 3 deprecated Firebase endpoints (add-pocket-article, save, archive) and redirect to microservices equivalents. No broader consolidation.

**Implementation Approach**:
1. Update Firebase Cloud Function to use microservices endpoints
2. Remove 3 deprecated endpoints from monolith
3. Add 301 redirects from old URLs to new microservices URLs
4. No further consolidation or versioning

**Example Changes**:
```python
# Remove from monolith
# POST /firebase/add-pocket-article
# POST /firebase/save
# POST /firebase/archive

# Add redirects
@app.get("/firebase/archive")
def firebase_archive_redirect():
    return RedirectResponse("/api/v1/firebase/archive", status_code=301)
```

**Pros:**
- ✅ Fastest to implement (1-2 weeks)
- ✅ Minimal risk (small scope of changes)
- ✅ Addresses immediate concern (deprecated endpoints)
- ✅ Low infrastructure requirements
- ✅ Easy to test and validate

**Cons:**
- ❌ Doesn't achieve goal of "drastically simplify endpoints" (28 → 25, only 11% reduction)
- ❌ Still have duplicate implementations (download URL endpoints)
- ❌ No consolidation of similar endpoints (no query parameter pattern)
- ❌ Misses opportunity for proper API versioning
- ❌ Technical debt remains (monolith/microservices split)
- ❌ No improvement in maintainability or consistency

**Trade-offs:**
- **Complexity**: Same as current (no reduction in overall complexity)
- **Risk**: Very Low (minimal changes)
- **Maintenance**: Same as current (still maintaining 2 codebases)
- **Scalability**: Same as current
- **Cost**: Same as current

**Codebase Fit**: 5/5 - Requires minimal changes to existing code

**Best Practice Fit**: 3/5 - Addresses deprecation properly, but misses consolidation opportunity

**When to Choose:**
- Only goal is to remove deprecated endpoints (not broader simplification)
- Extremely limited development resources
- Risk tolerance is very low (can't afford any issues)
- Need quick win before tackling larger refactoring

---

### Decision Matrix

| Criterion | Option 1: Direct Replacement ⭐ | Option 2: Strangler Pattern | Option 3: Minimal |
|-----------|-------------------------------|----------------------------|-------------------|
| **Complexity** | Medium → Low | High → Low | Low → Same |
| **Risk** | Medium (not in prod) | Low (if in prod) | Very Low |
| **Maintenance** | Low | High → Low | Same |
| **Timeline** | **2-3 weeks** | 12-18 months | 1-2 weeks |
| **Cost** | Lower | Higher → Same | Same |
| **Codebase Fit** | 5/5 | 5/5 | 5/5 |
| **Best Practice Fit** | 5/5 (for non-prod) | 5/5 (for prod) | 3/5 |
| **Endpoint Reduction** | **43% (28→16)** | ~30% (28→18-20) | ~11% (28→25) |
| **Backward Compat** | No (not needed) | Excellent | Good |
| **Achieves Goal** | ✅ YES | ⚠️ Overkill | ❌ NO |

---

## 4) Recommended Approach

**Selected Option:** Option 1 - Direct Replacement (Remove Monolith, Build Clean API)

**Rationale:**

1. **NOT in production**: User confirmed "we are not in production so we can make changes". This changes everything - no need for gradual migration, deprecation, or backward compatibility.

2. **Achieves stated goal**: User wants to "remove the entire monolith api part and centralize on shared microservices api gateway". Option 1 does exactly this. Option 2 (strangler pattern) is overkill.

3. **43% reduction**: Option 1 achieves 43% endpoint reduction (28 → 16), significantly better than Option 3's 11% (28 → 25).

4. **Fast implementation**: 2-3 weeks vs 12-18 months for Option 2. No production users means we can move quickly.

5. **Only 2 clients to update**: Firebase Cloud Function and Frontend React app. Both are under our control and can be updated during implementation.

6. **User wants "one endpoint" per operation**: User's questions show preference for minimal, consolidated API. Option 1 delivers this.

**What We Are NOT Doing:**

Since we're NOT in production, we can skip all the complexity:

- ❌ **NOT doing gradual migration** - Just replace monolith entirely
- ❌ **NOT implementing strangler pattern** - No routing layer, no feature flags, no dual-running
- ❌ **NOT supporting deprecated endpoints** - Delete them immediately
- ❌ **NOT maintaining backward compatibility** - Will update all clients
- ❌ **NOT sending deprecation emails** - No external users to notify
- ❌ **NOT using 301 redirects or 410 Gone** - Just remove old endpoints
- ❌ **NOT monitoring deprecated endpoint usage** - No production traffic to monitor
- ❌ **NOT running both codebases** - Delete monolith immediately after microservices ready

---

## 5) Step-by-Step Implementation Plan

**Timeline**: 2-3 weeks
**Approach**: Direct replacement (no gradual migration)

---

### Week 1: Build Clean Microservices API

#### Step 1: Design Final API Structure

**Goal**: Design the 16-endpoint REST API structure with proper models

**Files to Create:**
- `services/api-gateway/app/routes/v1_archive.py` - Archive operations (9 endpoints)
- `services/api-gateway/app/routes/v1_admin.py` - Admin/supporting operations (7 endpoints)
- `services/api-gateway/app/models/archive.py` - Pydantic models

**Final API Structure:**

```python
# Core Archive Operations (9 endpoints)
POST   /v1/archive                                    # Create archive
POST   /v1/archive/batch                              # Batch create
GET    /v1/archive                                    # List with pagination/filtering
GET    /v1/archive/{item_id}                          # Get by ID
GET    /v1/archive/by-url?url=...                     # Get by URL
PATCH  /v1/archive/{item_id}                          # Update metadata
DELETE /v1/archive/{item_id}                          # Delete by ID
DELETE /v1/archive/by-url?url=...                     # Delete by URL
GET    /v1/archive/{item_id}/download/{archiver}      # Download

# Supporting Operations (7 endpoints)
GET    /v1/tasks/{task_id}                            # Task status
POST   /v1/archive/{item_id}/summarize                # Trigger summarization
POST   /v1/archive/requeue                            # Requeue failed
GET    /v1/archivers                                  # List available archivers
POST   /v1/sync/postgres-to-firestore                 # Sync P→F
POST   /v1/sync/firestore-to-postgres                 # Sync F→P
GET    /health                                        # Health check
```

**Key Design Decisions:**
1. Use `/v1/archive` as base path (not `/v2/archive`, this is the final API)
2. Consolidate create operations (POST `/v1/archive` accepts url, optional item_id, archiver list)
3. Use query parameters for filtering (GET `/v1/archive?user_id=X&start_date=Y`)
4. Preserve specialized endpoints (download, summarize, requeue, sync, archivers)

**Tests/Checks:**
- OpenAPI spec generated and reviewed
- Pydantic models defined for all request/response bodies
- Design review with team

**Done When:**
- [ ] API structure finalized and documented
- [ ] Pydantic models created
- [ ] OpenAPI spec reviewed

---

#### Step 2: Implement Archive Endpoints

**Goal**: Implement the 9 core archive operation endpoints

**Files to Create/Edit:**
- `services/api-gateway/app/routes/v1_archive.py`

**Implementation Details:**

1. **POST `/v1/archive`** - Consolidates old add-pocket-article, save, archive endpoints:
   ```python
   @router.post("/v1/archive")
   async def create_archive(
       url: str,
       item_id: Optional[str] = None,  # Auto-generate if not provided
       archivers: List[str] = ["all"],
       metadata: Optional[Dict] = None
   ):
       # 1. Validate URL
       # 2. Generate item_id if not provided (prefix logic: pocket_ vs article_)
       # 3. Check for existing archive (skip if exists)
       # 4. Create DB record
       # 5. Queue Celery tasks for archivers
       # 6. Return task IDs and status
   ```

2. **POST `/v1/archive/batch`** - Batch create:
   ```python
   @router.post("/v1/archive/batch")
   async def create_archive_batch(items: List[ArchiveRequest]):
       # Process multiple items in one request
   ```

3. **GET `/v1/archive`** - List with pagination/filtering:
   ```python
   @router.get("/v1/archive")
   async def list_archives(
       user_id: Optional[str] = None,
       start_date: Optional[datetime] = None,
       end_date: Optional[datetime] = None,
       status: Optional[str] = None,
       limit: int = Query(100, ge=1, le=1000),
       offset: int = 0,
       sort_by: str = "created_at",
       sort_order: Literal["asc", "desc"] = "desc"
   ):
       # Query PostgreSQL, optionally merge with Firestore
   ```

4. **GET `/v1/archive/{item_id}`** - Get by ID
5. **GET `/v1/archive/by-url?url=...`** - Get by URL
6. **PATCH `/v1/archive/{item_id}`** - Update metadata
7. **DELETE `/v1/archive/{item_id}`** - Delete by ID
8. **DELETE `/v1/archive/by-url?url=...`** - Delete by URL
9. **GET `/v1/archive/{item_id}/download/{archiver}`** - Generate signed download URL

**Code to Reuse from Monolith:**
- Skip existing saves logic (saves.py:172-240)
- Paywall URL rewriting (saves.py:143-147)
- Storage provider integration (saves.py:243-250, 409-427)
- Lazy Firestore migration (saves.py:348-386)

**Tests/Checks:**
- Unit tests for each endpoint
- Integration tests for full archive flow
- Test skip-existing logic
- Test Celery task queueing

**Done When:**
- [ ] All 9 archive endpoints functional
- [ ] Tests passing
- [ ] Code reviewed

---

#### Step 3: Implement Supporting Endpoints

**Goal**: Implement the 7 supporting operation endpoints

**Files to Create/Edit:**
- `services/api-gateway/app/routes/v1_admin.py`
- `services/api-gateway/app/routes/v1_sync.py`
- `services/api-gateway/app/routes/v1_tasks.py`
- `services/api-gateway/app/routes/health.py`

**Implementation:**

1. **GET `/v1/tasks/{task_id}`** - Migrate from `app/api/tasks.py`:
   - Query Celery for task status
   - Return status with item details

2. **POST `/v1/archive/{item_id}/summarize`** - Migrate from `app/api/saves.py:183-232`:
   - Trigger AI summarization for archived article
   - Queue Celery task

3. **POST `/v1/archive/requeue`** - Migrate from `app/api/saves.py:107-180`:
   - Requeue failed/pending archives
   - Handle paywall URL rewriting

4. **GET `/v1/archivers`** - Migrate from `app/api/saves.py:101-104`:
   - List available archiver plugins

5. **POST `/v1/sync/postgres-to-firestore`** - Migrate from `app/api/sync.py:49-223`:
   - Sync PostgreSQL → Firestore
   - Handle single or batch

6. **POST `/v1/sync/firestore-to-postgres`** - Migrate from `app/api/sync.py:226-351`:
   - Sync Firestore → PostgreSQL

7. **GET `/health`** - Simple health check:
   - Check DB connections
   - Check Celery queue
   - Return healthy/degraded status

**Tests/Checks:**
- Unit tests for each endpoint
- Integration tests for sync operations
- Test task status tracking

**Done When:**
- [ ] All 7 supporting endpoints functional
- [ ] Tests passing
- [ ] Code reviewed

---

### Week 2: Update Clients and Remove Monolith

#### Step 4: Update Firebase Cloud Function

**Goal**: Update Cloud Function to use new `/v1/archive` endpoint

**Files to Change:**
- `functions/index.js` (around line 97)

**Exact Edits:**

```javascript
// Before:
const response = await fetch(`${API_BASE_URL}/firebase/archive`, {
    method: 'POST',
    body: JSON.stringify({
        item_id: itemId,
        url: url,
        archiver: 'all'
    })
});

// After:
const response = await fetch(`${API_BASE_URL}/v1/archive`, {
    method: 'POST',
    body: JSON.stringify({
        url: url,
        item_id: itemId,
        archivers: ['all']
    })
});
```

**Tests/Checks:**
- Deploy Cloud Function to staging
- Test end-to-end: Firestore trigger → Cloud Function → API → Archive
- Verify articles archive correctly
- Test in production with monitoring

**Done When:**
- [ ] Cloud Function updated and tested
- [ ] Deployed to production
- [ ] Monitoring shows successful archival

---

#### Step 5: Update Frontend React App

**Goal**: Update Frontend to use new API endpoints

**Files to Change:**
- `frontend/src/api/` - API client files

**Exact Edits:**

1. Update archive creation:
   ```javascript
   // Before:
   POST /save or /firebase/save

   // After:
   POST /v1/archive
   ```

2. Update list/get operations:
   ```javascript
   // Before:
   GET /saves

   // After:
   GET /v1/archive
   ```

3. Update download:
   ```javascript
   // Before:
   GET /firebase/download/{item_id}/{archiver}

   // After:
   GET /v1/archive/{item_id}/download/{archiver}
   ```

4. Update delete operations:
   ```javascript
   // Before:
   DELETE /saves/{rowid}
   DELETE /saves/by-item/{item_id}
   DELETE /saves/by-url

   // After:
   DELETE /v1/archive/{item_id}
   DELETE /v1/archive/by-url?url=...
   ```

**Tests/Checks:**
- Test all frontend archive operations
- Verify pagination works
- Test download functionality
- Run E2E tests

**Done When:**
- [ ] All API calls updated
- [ ] Frontend tests passing
- [ ] Manual testing complete

---

#### Step 6: Delete Monolith API

**Goal**: Remove entire `app/api/` directory

**Files to Delete:**
- `app/api/firebase.py` (4 endpoints, all deprecated)
- `app/api/saves.py` (13 endpoints, all migrated)
- `app/api/sync.py` (2 endpoints, migrated)
- `app/api/tasks.py` (1 endpoint, migrated)
- `app/api/admin.py` (migrated to supporting endpoints)
- `app/api/commands.py` (3 endpoints - **DECISION NEEDED**: Keep or remove?)
- `app/api/ht.py` (1 endpoint - **DECISION NEEDED**: Keep or remove?)
- `app/api/misc.py` (1 health endpoint, replaced by `/health`)

**Exceptions (Keep for now if needed):**
- `/commands/executions` endpoints - If actively used, migrate to microservices first
- `/ht/send` endpoint - If HyperTerm integration still needed, migrate first

**Exact Edits:**
1. Remove `app/api/` directory entirely (or specific files)
2. Remove router imports from `app/main.py`
3. Update documentation to remove old endpoint references
4. Archive code to Git history (don't worry, it's all in version control)

**Tests/Checks:**
- Verify monolith API doesn't start (or returns 404 for old paths)
- Confirm all functionality works via microservices
- Run full integration test suite
- Monitor for errors in production

**Done When:**
- [ ] Monolith API deleted
- [ ] All tests passing
- [ ] No errors in production monitoring

---

### Week 3: Testing, Documentation, and Validation

#### Step 7: Comprehensive Testing

**Goal**: Ensure all functionality works correctly and performance is acceptable

**Test Categories:**

1. **Unit Tests**: All new endpoints (90%+ coverage)
2. **Integration Tests**: End-to-end archive flow
3. **E2E Tests**: Cloud Function + Frontend integration
4. **Performance Tests**: Load test with 1000 req/s
5. **Regression Tests**: Verify all features preserved

**Tests/Checks:**
- All test suites passing
- Load test p95 latency < 200ms
- No increase in error rate
- Database connection pool healthy

**Done When:**
- [ ] All tests passing
- [ ] Performance validated
- [ ] No regressions found

---

#### Step 8: Documentation and Deployment

**Goal**: Update documentation and deploy to production

**Documentation Updates:**
- Update API documentation with new endpoint structure
- Remove old endpoint documentation
- Update client integration guides
- Create migration guide (for reference, though not needed for external clients)

**Deployment:**
1. Deploy microservices API gateway to production
2. Verify health checks pass
3. Monitor metrics for 24-48 hours
4. Confirm no issues

**Done When:**
- [ ] Documentation updated
- [ ] Deployed to production
- [ ] Monitoring shows healthy system
- [ ] Endpoint count reduced from 28 → 16 (43% reduction)
- [ ] Success! 🎉

---

## 6) Test Plan

**Context:** Since we're NOT in production, we can focus on functional testing rather than extensive compatibility/migration testing. No need for strangler proxy or gradual rollout tests.

---

### Unit Tests

**Files to Create/Update:**
- `tests/unit/routes/test_v1_archive.py` - Test v1 archive endpoints
- `tests/unit/routes/test_v1_admin.py` - Test v1 admin endpoints
- `tests/unit/routes/test_v1_sync.py` - Test sync endpoints
- `tests/unit/routes/test_v1_tasks.py` - Test task status endpoint

**Test Cases:**

1. **Archive Endpoint Tests**:
   - POST `/v1/archive` creates archive with auto-generated item_id
   - POST `/v1/archive` accepts custom item_id
   - POST `/v1/archive` validates URL format
   - POST `/v1/archive/batch` processes multiple items
   - GET `/v1/archive` returns paginated results (limit, offset)
   - GET `/v1/archive` filters by user_id, date range, status
   - GET `/v1/archive` sorts correctly (sort_by, sort_order)
   - GET `/v1/archive/{item_id}` returns item or 404
   - GET `/v1/archive/by-url` returns item by URL or 404
   - PATCH `/v1/archive/{item_id}` updates metadata
   - DELETE `/v1/archive/{item_id}` deletes item
   - DELETE `/v1/archive/by-url` deletes by URL
   - GET `/v1/archive/{item_id}/download/{archiver}` generates signed URL
   - Invalid parameters return 400 with error details

2. **Admin Endpoint Tests**:
   - POST `/v1/archive/requeue` requeues failed archives
   - POST `/v1/archive/{item_id}/summarize` triggers summarization
   - GET `/v1/archivers` returns available archiver list
   - GET `/v1/tasks/{task_id}` returns task status

3. **Sync Endpoint Tests**:
   - POST `/v1/sync/postgres-to-firestore` syncs single item
   - POST `/v1/sync/postgres-to-firestore` syncs batch
   - POST `/v1/sync/firestore-to-postgres` syncs single item
   - POST `/v1/sync/firestore-to-postgres` syncs batch

**Coverage Target:** 90%+ for all new v1 code

---

### Integration Tests

**Files to Create/Update:**
- `tests/integration/test_v1_endpoints.py` - End-to-end v1 tests
- `tests/integration/test_archive_flow.py` - Full archive workflow

**Test Scenarios:**

1. **End-to-End Archive Flow**:
   - POST `/v1/archive` with URL and archivers
   - Verify Celery task queued
   - Wait for completion (or mock task completion)
   - GET `/v1/archive/{item_id}` verifies archived content
   - GET `/v1/archive/{item_id}/download/{archiver}` returns signed URL
   - Verify database records created in PostgreSQL
   - Verify sync to Firestore (if enabled)

2. **Batch Operations**:
   - POST `/v1/archive/batch` with 10 items
   - Verify all tasks queued
   - Verify all items created in database

3. **Skip Existing Logic**:
   - POST `/v1/archive` for URL that already exists
   - Verify it skips archival, returns existing item_id
   - Verify no duplicate Celery tasks queued

4. **Error Handling**:
   - Invalid URL returns 400
   - Missing required fields return 400
   - Non-existent item_id returns 404
   - Database connection failure returns 503

---

### E2E Tests

**Files to Create/Update:**
- `tests/e2e/test_firebase_cloud_function.py` - Test Cloud Function integration
- `tests/e2e/test_frontend_integration.py` - Test Frontend integration

**Scenarios:**

1. **Firebase Cloud Function Integration**:
   - Trigger Cloud Function (Firestore write)
   - Cloud Function calls POST `/v1/archive`
   - Archive task completes successfully
   - Firestore updated with archive status
   - Verify Cloud Function receives 200 response

2. **Frontend React App Integration**:
   - Frontend calls POST `/v1/archive`
   - Archive task queued
   - Frontend polls GET `/v1/tasks/{task_id}` for status
   - Frontend retrieves archived content with GET `/v1/archive/{item_id}`
   - Frontend downloads with GET `/v1/archive/{item_id}/download/{archiver}`

---

### Regression Tests

**Purpose**: Ensure new API preserves all functionality from monolith

**Files to Create:**
- `tests/regression/test_archive_behavior.py` - Archive functionality
- `tests/regression/test_admin_operations.py` - Admin operations

**Test Cases:**

1. **Archive Behavior** (Critical features to preserve):
   - Skip existing saves logic still works (from saves.py:172-240)
   - Paywall URL rewriting still works (from saves.py:143-147)
   - Storage provider fallback still works (from saves.py:409-427)
   - Lazy Firestore migration still works (from saves.py:348-386)
   - Multi-archiver support works (all, monolith, singlefile, etc.)

2. **Admin Operations**:
   - List archives with pagination
   - Filter by user_id, date range, status
   - Delete by item_id and by URL
   - Requeue failed saves (with paywall URL rewriting)
   - Trigger summarization

3. **Sync Operations**:
   - PostgreSQL → Firestore sync preserves all fields
   - Firestore → PostgreSQL sync preserves all fields
   - Batch sync handles errors gracefully
   - Artifact mapping works correctly

---

### Performance Tests

**Files to Create:**
- `tests/performance/test_v1_load.py` - Load testing

**Test Scenarios:**

1. **Load Test - POST `/v1/archive`**:
   - 100 requests/second for 2 minutes
   - Measure p50, p95, p99 latency
   - Target: p95 < 200ms, p99 < 500ms
   - Monitor Celery queue depth

2. **Load Test - GET `/v1/archive`** (list endpoint):
   - 1000 requests/second for 2 minutes
   - Measure p50, p95, p99 latency
   - Target: p95 < 200ms, p99 < 500ms
   - Monitor database connection pool usage

3. **Database Query Performance**:
   - Measure query time for list endpoint with filters
   - Ensure indexes are used (EXPLAIN ANALYZE)
   - Target: < 50ms for typical query
   - Verify pagination doesn't cause full table scan

4. **Download URL Generation**:
   - Measure signed URL generation time
   - Target: < 100ms
   - Verify GCS API calls are cached if possible

---

## 7) Observability & Operability

**Context:** Since we're doing direct replacement (no gradual migration), we don't need strangler proxy monitoring, feature flags, or migration tracking metrics.

---

### Logs to Add/Change

**New Log Statements:**

```python
# In v1 archive endpoint
logger.info("v1_archive_create", extra={
    "url": anonymize_url(url),
    "item_id": item_id,
    "archivers": archivers,
    "user_id": user_id
})

logger.info("v1_archive_create_response", extra={
    "item_id": item_id,
    "status": status,
    "task_ids": task_ids,
    "duration_ms": duration
})

# In v1 archive list endpoint
logger.info("v1_archive_list", extra={
    "user_id": user_id,
    "filters": {
        "start_date": start_date,
        "end_date": end_date,
        "status": status
    },
    "limit": limit,
    "offset": offset
})

logger.info("v1_archive_list_response", extra={
    "count": len(results),
    "total": total_count,
    "duration_ms": duration
})

# In download endpoint
logger.info("v1_archive_download", extra={
    "item_id": item_id,
    "archiver": archiver,
    "expiration_hours": expiration_hours
})

# In sync endpoints
logger.info("v1_sync_postgres_to_firestore", extra={
    "mode": "single" or "batch",
    "item_count": count
})
```

**Redaction Rules:**
- Never log full URLs (may contain tokens in query params)
- Never log request bodies (may contain PII)
- Log only anonymized user_id, not email or name
- Anonymize URLs: log domain only, not full path

---

### Metrics to Add

**New Metrics:**

```python
# Endpoint usage
v1_archive_requests_total (counter, labels: endpoint, method, status_code)
v1_archive_duration_seconds (histogram, labels: endpoint, method)

# Archive operations
v1_archive_creates_total (counter, labels: archiver, status)
v1_archive_skips_total (counter, labels: reason)  # Reason: existing, invalid_url, etc.

# Celery tasks
v1_celery_tasks_queued_total (counter, labels: archiver)
v1_celery_queue_depth (gauge, labels: queue_name)

# Database operations
v1_db_queries_total (counter, labels: operation, table)
v1_db_query_duration_seconds (histogram, labels: operation)

# Download operations
v1_download_url_generated_total (counter, labels: archiver, storage_provider)
v1_download_url_errors_total (counter, labels: archiver, error_type)

# Sync operations
v1_sync_operations_total (counter, labels: direction, mode)  # direction: p2f or f2p, mode: single or batch
v1_sync_duration_seconds (histogram, labels: direction, mode)
v1_sync_errors_total (counter, labels: direction, error_type)
```

**Cardinality Control:**
- Use bounded labels (endpoint values from known set)
- Use bounded archiver names (monolith, singlefile, pdf, etc.)
- Use bounded error_type values
- Don't use user_id or item_id as labels (high cardinality)

---

### Tracing

**New Spans:**

```python
# Archive create operation
with tracer.start_as_current_span("v1.archive.create") as span:
    span.set_attribute("url", anonymize_url(url))
    span.set_attribute("archivers", archivers)
    span.set_attribute("user_id", user_id)

    # Child span for checking existing
    with tracer.start_as_current_span("v1.archive.check_existing"):
        existing = await db.get_archive_by_url(url)

    # Child span for database insert
    if not existing:
        with tracer.start_as_current_span("v1.archive.db_insert"):
            item_id = await db.create_archive(...)

    # Child span for queuing Celery tasks
    with tracer.start_as_current_span("v1.archive.queue_tasks"):
        for archiver in archivers:
            task_id = celery_app.send_task(...)

# Archive list operation
with tracer.start_as_current_span("v1.archive.list") as span:
    span.set_attribute("user_id", user_id)
    span.set_attribute("limit", limit)
    span.set_attribute("filters", str(filters))

    # Child span for database query
    with tracer.start_as_current_span("v1.archive.db_query"):
        results = await db.query_archives(...)

# Download URL generation
with tracer.start_as_current_span("v1.archive.download") as span:
    span.set_attribute("item_id", item_id)
    span.set_attribute("archiver", archiver)

    # Child span for GCS signed URL
    with tracer.start_as_current_span("v1.gcs.generate_signed_url"):
        url = storage_provider.generate_access_url(...)

# Sync operation
with tracer.start_as_current_span("v1.sync.postgres_to_firestore") as span:
    span.set_attribute("mode", mode)
    span.set_attribute("item_count", count)

    # Child spans for each item
    for item in items:
        with tracer.start_as_current_span("v1.sync.sync_item"):
            await sync_item_to_firestore(item)
```

---

### Alerts

**Critical Alerts:**

1. **Error Rate Alert**:
   - Condition: `v1_archive_requests_total{status_code="5xx"} / v1_archive_requests_total > 0.05` for 5 minutes
   - Action: Page on-call engineer
   - Reason: 5% error rate indicates serious issue

2. **Latency Degradation Alert**:
   - Condition: `v1_archive_duration_seconds p95 > 500ms` for 10 minutes
   - Action: Notify team Slack channel
   - Reason: Significant latency increase, investigate database

3. **Celery Queue Depth Alert**:
   - Condition: `v1_celery_queue_depth > 1000` for 10 minutes
   - Action: Notify team Slack channel
   - Reason: Tasks backing up, may need more workers

4. **Database Connection Alert**:
   - Condition: `database_connections_active / database_connections_max > 0.8` for 5 minutes
   - Action: Notify team Slack channel
   - Reason: Connection pool nearly exhausted

**Non-Critical Alerts:**

5. **High Skip Rate Alert**:
   - Condition: `v1_archive_skips_total / v1_archive_creates_total > 0.5` for 1 hour
   - Action: Email report to team
   - Reason: Many duplicate archive requests, investigate client behavior

6. **Sync Errors Alert**:
   - Condition: `v1_sync_errors_total > 10` in 1 hour
   - Action: Email report to team
   - Reason: Firestore sync failing, investigate

---

### Health Checks

**New Endpoint:**

```python
@app.get("/health")
async def health_check():
    """
    Comprehensive health check for v1 API.
    Returns 200 if healthy, 503 if degraded.
    """
    checks = {
        "database": await check_database_connection(),
        "firestore": await check_firestore_connection(),
        "celery": await check_celery_queue_reachable(),
        "storage": await check_storage_providers()
    }

    all_healthy = all(check["status"] == "healthy" for check in checks.values())

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "healthy" if all_healthy else "degraded",
            "checks": checks,
            "version": "v1",
            "timestamp": datetime.utcnow().isoformat(),
            "endpoint_count": 16
        }
    )

# Helper check functions
async def check_database_connection():
    try:
        await db.execute("SELECT 1")
        return {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def check_firestore_connection():
    try:
        firestore_client.collection("health").document("test").get()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def check_celery_queue_reachable():
    try:
        # Ping Celery broker (Redis/RabbitMQ)
        celery_app.broker_connection().ensure_connection(max_retries=3)
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def check_storage_providers():
    # Check that at least one storage provider is healthy
    healthy_providers = []
    for provider in storage_providers:
        if await provider.is_healthy():
            healthy_providers.append(provider.name)

    if healthy_providers:
        return {"status": "healthy", "providers": healthy_providers}
    else:
        return {"status": "unhealthy", "error": "No storage providers available"}
```

**Kubernetes Readiness/Liveness:**
- Use `/health` for both readiness and liveness probes
- Readiness: Return 503 if any check fails (remove from load balancer)
- Liveness: Only restart if endpoint doesn't respond (timeout)

---

## 8) Rollout & Rollback

**Context:** Since we're NOT in production and doing direct replacement, rollout is simple: deploy microservices, update clients, remove monolith. No gradual traffic shifting needed.

---

### Rollout Strategy

**Simple Direct Rollout:**

| Phase | Timeline | Actions |
|-------|----------|---------|
| **Deploy Microservices** | Week 1 | Build and test v1 API in staging, deploy to production |
| **Update Clients** | Week 2 | Update Firebase Cloud Function and Frontend React app |
| **Remove Monolith** | Week 2 | Delete `app/api/` after clients updated |
| **Monitor** | Week 3 | Monitor for 1 week to ensure stability |

**Deployment Checklist:**
- [ ] Build v1 API endpoints (all 16 endpoints)
- [ ] All tests passing (unit, integration, E2E)
- [ ] Deploy to staging environment
- [ ] Run smoke tests in staging
- [ ] Deploy to production
- [ ] Verify `/health` endpoint returns healthy
- [ ] Monitor error rates and latency for 24 hours
- [ ] Update Firebase Cloud Function
- [ ] Update Frontend React app
- [ ] Test end-to-end flows (Cloud Function + Frontend)
- [ ] Delete monolith `app/api/` directory
- [ ] Verify old endpoints return 404
- [ ] Monitor for 1 week

---

### Backward Compatibility Notes

**NOT Maintaining Backward Compatibility:**

Since we're NOT in production, we can make breaking changes:

1. **Old endpoint paths removed**: `/firebase/archive`, `/saves`, etc. will return 404
2. **Clients must be updated**: Firebase Cloud Function and Frontend React app
3. **No redirect layer**: Old paths just stop working
4. **No deprecation period**: Remove immediately after clients updated

**What IS Preserved:**

1. **Functionality**: All archive operations work the same
2. **Data**: No data loss, all existing archives remain accessible
3. **Database schema**: No schema migrations needed
4. **Behavior**: Skip existing, paywall rewriting, storage fallback all preserved

---

### Rollback Steps

**Emergency Rollback Scenarios:**

**Scenario 1: Critical Bug in v1 API (High Error Rate)**

1. **Revert deployment**: Roll back to previous version (monolith-only)
2. **Fix bug**: Identify and fix issue in v1 endpoints
3. **Test thoroughly**: Run full test suite
4. **Re-deploy**: Deploy fixed version

**Rollback Time:** 5-10 minutes (Kubernetes rollback or revert Git commit + redeploy)

**Scenario 2: Performance Issues (p95 > 500ms)**

1. **Investigate immediately**: Check database slow query log
2. **Quick fix if possible**: Add missing index, optimize query
3. **If not quick fix**: Roll back to monolith, fix properly, re-deploy

**Rollback Time:** 5-10 minutes (rollback) + fix time

**Scenario 3: Clients Not Working After Update**

1. **Revert client changes**: Roll back Firebase Cloud Function and/or Frontend
2. **Fix integration**: Debug API calls, fix payload format
3. **Re-deploy clients**: Deploy fixed clients

**Rollback Time:** 5-10 minutes per client

**Rollback Communication:**
- Post in team Slack channel
- Document issue in incident log
- Send postmortem email after resolution

---

### Data Migration/Backfill Plan

**No Schema Changes Needed:**

This refactoring does NOT require database migrations because:
- We're consolidating endpoints, not changing data models
- Same database tables are used by monolith and microservices
- No new columns or tables needed
- Both connect to same PostgreSQL database

**Firestore Sync Strategy:**

Since we have dual-persistence (PostgreSQL + Firestore), sync must continue to work:

1. **Existing Sync Endpoints Preserved**:
   - POST `/v1/sync/postgres-to-firestore` (migrated from monolith)
   - POST `/v1/sync/firestore-to-postgres` (migrated from monolith)
   - Same functionality, same behavior

2. **Outbox Pattern** (if implemented):
   ```python
   # Write to PostgreSQL + outbox table in single transaction
   with db.transaction():
       db.insert_archive_artifact(...)
       db.insert_outbox_event("article_archived", ...)

   # Separate worker process syncs to Firestore
   ```

3. **No Backfill Needed**: Existing data is already in both systems

**Verification After Rollout:**
- Run sync verification script to ensure both databases match
- Check that new archives sync correctly to Firestore
- Monitor sync error metrics

---

## 9) Risk Register

**Context:** Since we're NOT in production, risk scores are significantly lower. Only 2 known clients to update, no external users to notify, no gradual migration needed.

---

### Top Risks (Risk Score ≥ 6)

| # | Risk | Likelihood | Impact | Risk Score | Mitigation | Detection |
|---|------|------------|--------|------------|------------|-----------|
| 1 | **Firebase Cloud Function fails after endpoint change** | 3 (Possible) | 3 (Moderate) | **9** | - Test Cloud Function in staging first<br>- Test end-to-end before removing monolith<br>- Keep rollback plan ready | - E2E test of Cloud Function<br>- Monitor Cloud Function logs<br>- Alert on Cloud Function errors |
| 2 | **Frontend React app breaks after API update** | 3 (Possible) | 3 (Moderate) | **9** | - Test all frontend flows before removing monolith<br>- Run E2E tests (Playwright/Cypress)<br>- Keep rollback plan ready | - Frontend E2E tests<br>- Monitor frontend error logs<br>- Manual testing of key workflows |
| 3 | **Performance regression in v1 endpoints** | 2 (Unlikely) | 3 (Moderate) | **6** | - Load test before deployment<br>- Monitor latency after deployment<br>- Optimize slow queries proactively<br>- Add database indexes if needed | - P95/P99 latency metrics<br>- Alert on latency > 500ms<br>- APM traces for slow requests |
| 4 | **Database connection pool issues** | 2 (Unlikely) | 3 (Moderate) | **6** | - Monitor connection pool usage<br>- Increase pool size proactively<br>- Use connection pooler (PgBouncer) if needed | - Database connection metrics<br>- Alert on connection pool near capacity<br>- Slow query logs |
| 5 | **Regression: Skip existing logic breaks** | 2 (Unlikely) | 3 (Moderate) | **6** | - Write comprehensive regression tests<br>- Test skip-existing logic explicitly<br>- Manual testing with duplicate URLs | - Regression test suite<br>- Integration tests<br>- Monitor duplicate archive attempts |
| 6 | **Regression: Firestore sync breaks** | 2 (Unlikely) | 3 (Moderate) | **6** | - Test sync endpoints thoroughly<br>- Run sync verification after deployment<br>- Monitor sync error metrics | - Sync integration tests<br>- Monitor `v1_sync_errors_total`<br>- Verify data consistency script |

**Legend**:
- Likelihood: 1=Very Unlikely, 2=Unlikely, 3=Possible, 4=Likely, 5=Very Likely
- Impact: 1=Minimal, 2=Low, 3=Moderate, 4=High, 5=Critical
- Risk Score = Likelihood × Impact (1-25)
- **Note:** Impact scores are lower because we're NOT in production (no external users affected)

---

### Risks ELIMINATED by Not Being in Production

These high-risk scenarios from production migrations **do NOT apply**:

- ❌ **Unknown external API consumers** - We only have 2 known clients (Cloud Function + Frontend)
- ❌ **Long deprecation timeline needed** - Can remove old endpoints immediately
- ❌ **Backward compatibility required** - Can make breaking changes
- ❌ **Gradual rollout complexity** - No strangler pattern, no feature flags, no dual-running
- ❌ **Customer complaints** - No external customers to notify
- ❌ **Production downtime risk** - No production traffic to affect

---

### Risk Mitigation Roadmap

**Pre-Deployment (P0 - Must Complete)**:
- [ ] Test Firebase Cloud Function with new endpoint in staging
- [ ] Test Frontend React app with new API in staging
- [ ] Run full regression test suite (skip-existing, paywall rewriting, storage fallback)
- [ ] Load test v1 endpoints (100 req/s for 2 minutes)
- [ ] Verify Firestore sync works correctly
- [ ] Create rollback plan (Git revert + redeploy)

**Post-Deployment (P1 - First Week)**:
- [ ] Monitor error rate and latency for 24 hours
- [ ] Monitor database connection pool usage
- [ ] Monitor Celery queue depth
- [ ] Run sync verification script to check data consistency
- [ ] Manual testing of key workflows (create, list, download, delete)

**Ongoing (P2 - First Month)**:
- [ ] Monitor slow query logs weekly
- [ ] Optimize any queries with p95 > 100ms
- [ ] Track skip-existing logic effectiveness
- [ ] Review sync errors (should be near-zero)

---

### Detection & Monitoring

**Alerts to Create**:

1. **High Priority** (Page/Notify Immediately):
   - Error rate > 5% for 5 minutes → Notify Slack
   - P95 latency > 500ms for 10 minutes → Notify Slack
   - Database connections > 80% of pool → Notify Slack
   - Celery queue depth > 1000 for 10 minutes → Notify Slack

2. **Medium Priority** (Email Report):
   - Sync errors > 10 in 1 hour → Email report
   - High skip rate (> 50% of requests) for 1 hour → Email report
   - Download URL generation failures > 5% for 1 hour → Email report

**Metrics to Track**:
- `v1_archive_requests_total` (counter) → Track usage
- `v1_archive_duration_seconds` (histogram) → Monitor performance
- `v1_archive_skips_total` (counter) → Track skip-existing logic
- `v1_celery_queue_depth` (gauge) → Monitor task backlog
- `v1_sync_errors_total` (counter) → Track sync failures
- `database_connections_active` (gauge) → Detect connection issues

**Tests to Write**:
- **Load test**: 100 requests/second for 2 minutes (modest, not production-scale)
- **Regression test**: Verify skip-existing, paywall rewriting, storage fallback
- **Integration test**: Full archive flow (create → queue → complete → download)
- **E2E test**: Cloud Function and Frontend workflows
- **Sync test**: PostgreSQL ↔ Firestore bidirectional sync

---

## Next Steps

**Context:** NOT in production, 2-3 week timeline, direct replacement approach

---

### Week 1: Build Clean Microservices API

**Immediate Actions (Days 1-2):**

1. **Review this plan** with team
   - Confirm 2-3 week timeline is acceptable
   - Review 16-endpoint API structure
   - Get approval to proceed

2. **Design API structure** (Step 1)
   - Finalize 16-endpoint design
   - Create OpenAPI spec
   - Define Pydantic models
   - Review with team

**Implementation (Days 3-7):**

3. **Implement archive endpoints** (Step 2)
   - Build 9 core archive operation endpoints
   - Reuse monolith logic (skip-existing, paywall rewriting, storage fallback)
   - Write unit tests
   - Write integration tests

4. **Implement supporting endpoints** (Step 3)
   - Build 7 supporting endpoints (tasks, summarize, requeue, archivers, sync, health)
   - Write unit tests
   - Write integration tests
   - Run full test suite

---

### Week 2: Update Clients and Remove Monolith

**Client Updates (Days 8-10):**

5. **Update Firebase Cloud Function** (Step 4)
   - Change endpoint URL from `/firebase/archive` to `/v1/archive`
   - Update payload structure (archivers array)
   - Deploy to staging
   - Test end-to-end
   - Deploy to production

6. **Update Frontend React App** (Step 5)
   - Update all API calls to v1 endpoints
   - Test all frontend workflows
   - Run E2E tests
   - Deploy to production

**Cleanup (Days 11-12):**

7. **Delete monolith API** (Step 6)
   - Remove `app/api/firebase.py`, `saves.py`, `sync.py`, `tasks.py`, etc.
   - Update `app/main.py` to remove router imports
   - Verify old endpoints return 404
   - Archive code to Git history (it's safe in version control)

---

### Week 3: Testing, Documentation, and Validation

**Validation (Days 13-16):**

8. **Comprehensive testing** (Step 7)
   - Run full test suite (unit, integration, E2E, regression)
   - Load test (100 req/s for 2 minutes)
   - Performance validation (p95 < 200ms)
   - Manual testing of key workflows

9. **Documentation and monitoring** (Step 8)
   - Update API documentation
   - Update client integration guides
   - Verify monitoring/alerts working
   - Run sync verification script

**Monitoring (Days 17-21):**

10. **Monitor for 1 week**
    - Watch error rate metrics
    - Watch latency metrics
    - Watch database connection pool
    - Watch Celery queue depth
    - Watch sync errors

---

### Success Criteria ✅

When all of these are true, the refactoring is **complete**:

- [ ] All 16 v1 endpoints functional and tested
- [ ] Firebase Cloud Function updated and working
- [ ] Frontend React App updated and working
- [ ] Monolith `app/api/` directory deleted
- [ ] Old endpoints return 404
- [ ] All tests passing (unit, integration, E2E, regression)
- [ ] Load test shows p95 < 200ms
- [ ] No increase in error rate
- [ ] Firestore sync working correctly
- [ ] Documentation updated
- [ ] 1 week of stable operation
- [ ] **Endpoint count reduced from 28 → 16 (43% reduction)** 🎉

---

*Plan generated: 2026-01-16*
*Session: [simplify-api-endpoints](../README.md)*
*Estimated Duration: **2-3 weeks** (NOT 12-18 months - we're not in production!)*
*Target Endpoint Reduction: **43% (28 → 16 endpoints)***
