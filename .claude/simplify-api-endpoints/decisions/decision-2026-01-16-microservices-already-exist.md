# Decision Note: Microservices API Already Extensively Implemented

**Date:** 2026-01-16
**Status:** CRITICAL - Changes Implementation Approach
**Created By:** /work command during pre-flight

---

## Problem

The research plan assumes we need to build a new v1 API from scratch in the microservices gateway. However, **the microservices gateway already has 32 endpoints** across 6 route files:

**Current Microservices Endpoints (`services/api-gateway/app/routes/`):**

1. **saves.py** (8 endpoints):
   - POST `/api/v1/save`
   - POST `/api/v1/save/batch`
   - POST `/api/v1/workflow`
   - POST `/api/v1/archive/{archiver}`
   - POST `/api/v1/archive/{archiver}/batch`
   - GET `/api/v1/archive/{item_id}/size`
   - GET `/api/v1/retrieve`

2. **firebase.py** (3 endpoints):
   - GET `/api/v1/firebase/download/{item_id}/{archiver}`
   - POST `/api/v1/firebase/archive`
   - POST `/api/v1/firebase/add-article`

3. **admin.py** (11 endpoints):
   - GET `/api/v1/admin/stats`
   - DELETE `/api/v1/admin/archive/{item_id}`
   - POST `/api/v1/admin/retry-failed`
   - POST `/api/v1/admin/cleanup-local`
   - GET `/api/v1/admin/pending`
   - GET `/api/v1/admin/saves`
   - GET `/api/v1/admin/archivers`
   - POST `/api/v1/admin/saves/requeue`
   - POST `/api/v1/admin/summarize`
   - DELETE `/api/v1/admin/saves/by-item/{item_id}`
   - DELETE `/api/v1/admin/saves/by-url`

4. **tasks.py** (5 endpoints):
   - GET `/api/v1/tasks/{task_id}`
   - GET `/api/v1/tasks/{task_id}/celery`
   - POST `/api/v1/tasks/{task_id}/cancel`
   - GET `/api/v1/tasks`
   - GET `/api/v1/queue/stats`

5. **sync.py** (2 endpoints):
   - POST `/api/v1/sync/postgres-to-firestore`
   - POST `/api/v1/sync/firestore-to-postgres`

6. **commands.py** (3 endpoints):
   - GET `/api/v1/commands/executions`
   - GET `/api/v1/commands/executions/{execution_id}`
   - GET `/api/v1/commands/executions/{execution_id}/replay`

**Total:** 32 endpoints already implemented in microservices (more than the 28 in monolith!)

---

## Context

The research plan was based on endpoint enumeration that found:
- Monolith: 25 endpoints
- Microservices: 3 endpoints
- Total: 28 endpoints

However, it appears the endpoint enumeration only looked at `services/api-gateway/app/routes/firebase.py` and missed that the microservices gateway has **already replicated most monolith functionality**.

This fundamentally changes the implementation approach.

---

## Analysis

### What Microservices Already Has:

✅ **Archive operations**: save, batch, workflow, archive by archiver
✅ **Admin operations**: stats, retry, cleanup, pending, saves list, archivers, requeue, summarize, delete
✅ **Task operations**: task status, celery status, cancel, list tasks, queue stats
✅ **Sync operations**: PostgreSQL ↔ Firestore bidirectional sync
✅ **Commands**: executions list, detail, replay
✅ **Firebase integration**: download, archive, add-article
✅ **Download**: signed URL generation

### What Microservices Might Be Missing:

Based on the plan's desired 16-endpoint structure:

**Missing from desired v1 API:**
1. `GET /v1/archive` - List archives with pagination/filtering
2. `GET /v1/archive/{item_id}` - Get archive by ID
3. `GET /v1/archive/by-url` - Get archive by URL
4. `PATCH /v1/archive/{item_id}` - Update archive metadata
5. `GET /health` - Health check endpoint

**But these might exist with different paths:**
- List: Might be `/api/v1/admin/saves`
- Get by ID: Might be implicit in other endpoints
- Get by URL: Need to check
- Update: Need to check
- Health: Might exist in main.py

---

## Options

### Option 1: Audit Microservices, Fill Gaps (RECOMMENDED)

**Approach:**
1. Thoroughly audit existing microservices endpoints
2. Map them to the desired 16-endpoint v1 API structure
3. Identify genuine gaps (likely 3-5 missing endpoints)
4. Implement only the missing endpoints
5. Update clients to use existing microservices endpoints
6. Delete monolith

**Pros:**
- Leverages existing work (32 endpoints already done!)
- Much faster implementation (days vs weeks)
- Existing endpoints are likely battle-tested
- Less code to write = fewer bugs

**Cons:**
- Existing endpoints might not match desired REST structure exactly
- May have inconsistent naming/patterns
- Need to understand existing implementation first

**Risk:** Low - building on existing work

**Estimated Timeline:** 3-5 days

---

### Option 2: Build New v1 API From Scratch (Original Plan)

**Approach:**
1. Ignore existing microservices endpoints
2. Build new v1_archive.py, v1_admin.py, etc. from scratch
3. End up with duplicate implementations
4. Delete both monolith AND existing microservices routes

**Pros:**
- Clean slate, perfect REST design
- Consistent patterns throughout

**Cons:**
- Duplicate effort (32 endpoints already exist!)
- Throws away existing working code
- Much longer timeline (2-3 weeks)
- Higher risk (all new code)

**Risk:** Medium-High - rewriting working code

**Estimated Timeline:** 2-3 weeks

---

### Option 3: Refactor Existing Microservices to Match v1 API

**Approach:**
1. Audit existing microservices endpoints
2. Refactor/rename them to match desired v1 API structure
3. Keep existing implementations, just change paths/names
4. Update clients
5. Delete monolith

**Pros:**
- Keeps existing working code
- Achieves desired REST structure
- Moderate timeline

**Cons:**
- Refactoring risk (might break existing functionality)
- Need to update any existing clients of microservices
- More complex than Option 1

**Risk:** Medium

**Estimated Timeline:** 1-2 weeks

---

## Recommendation

**Option 1: Audit Microservices, Fill Gaps**

**Rationale:**
1. 32 endpoints already exist - don't throw away working code
2. Existing code likely already has:
   - Proper error handling
   - Rate limiting
   - Authentication
   - Database integration
   - Celery task queueing
   - Tests (possibly)
3. Much faster path to completion (3-5 days vs 2-3 weeks)
4. Lower risk (less new code = fewer bugs)
5. User's goal is "simplify endpoints" - consolidating monolith → microservices achieves this

**Approach:**
1. **Day 1**: Audit existing microservices endpoints thoroughly
   - Document what each endpoint does
   - Map to desired v1 API structure
   - Identify any missing functionality
2. **Day 2**: Implement 3-5 missing endpoints (if any)
   - GET `/api/v1/archive` (list with filters)
   - GET `/api/v1/archive/{item_id}` (get by ID)
   - GET `/api/v1/archive/by-url` (get by URL)
   - PATCH `/api/v1/archive/{item_id}` (update)
   - GET `/health` (health check)
3. **Day 3**: Update Firebase Cloud Function to use microservices
4. **Day 4**: Update Frontend React App to use microservices
5. **Day 5**: Delete monolith, test, document

**Caveat:**
If audit reveals existing microservices are poorly implemented or have major issues, we can pivot to Option 2 or 3.

---

## Next Steps

**Before proceeding with implementation:**

1. ✅ Create this decision note
2. ⏳ Thoroughly audit existing microservices endpoints:
   - Read each route file completely
   - Document functionality
   - Check for tests
   - Check for proper error handling
   - Map to desired v1 API structure
3. ⏳ Update work log with revised approach
4. ⏳ Proceed with Checkpoint 1: Audit existing endpoints

---

## Impact

**If we proceed with Option 2 (original plan):**
- 2-3 weeks of work
- Duplicate implementations
- Throw away 32 working endpoints

**If we proceed with Option 1 (recommended):**
- 3-5 days of work
- Leverage existing working code
- Fill gaps only where needed
- Achieve same end goal faster

**Decision:** Proceed with Option 1 (audit existing, fill gaps)

---

*Decision created during /work pre-flight check*
*Requires: Audit of existing microservices endpoints before implementation*
