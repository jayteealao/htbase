---
issue_id: "002"
status: "ready"
priority: "p2"
tags: ["code-review", "naming", "architecture", "dual-persistence"]
dependencies: []
---

# Problem Statement

**MISLEADING NAME: "migration-worker" should be "sync-worker"**

The current service name `migration-worker` is misleading. It suggests a one-time data migration operation, but this worker actually provides ongoing PostgreSQL → Firestore sync for dual persistence. This is a critical live service that runs continuously to keep mobile apps in sync.

## Why This Matters

**Dual Persistence Architecture:**
- **PostgreSQL** = Source of truth (all data)
- **Firestore** = Read replica for mobile apps (filtered data)
- **Sync Worker** = Keeps Firestore in sync with PostgreSQL (every write)

**Why the name matters:**
- "migration" implies one-time operation (like Alembic schema migrations)
- "sync" accurately describes ongoing data synchronization
- Misleading names confuse operators and developers
- Better names = clearer architecture understanding

**Current service purpose:**
- Called whenever data is added/updated in PostgreSQL
- Syncs the data to Firestore for mobile app access
- Runs continuously as part of dual persistence pattern
- Critical for mobile app functionality

## Evidence

**Current naming:**
```
services/
└── migration-worker/    ← Misleading name!
```

**What it actually does:**
```python
# From shared/storage/dual_database_storage.py
def create_article(self, metadata):
    # 1. Write to PostgreSQL (source of truth)
    success = self.postgres.create_article(metadata)

    # 2. Sync to Firestore (for mobile apps)
    if success:
        self.firestore.create_article(metadata)  # ← This is sync, not migration!
```

**Migration vs Sync:**
| Aspect | Migration | Sync (this worker) |
|--------|-----------|-------------------|
| Frequency | One-time | Every write |
| Purpose | Move data | Keep in sync |
| Duration | Finite | Ongoing/Continuous |
| Trigger | Manual | Automatic |

## Affected Files

**Directory to RENAME:**
- `services/migration-worker/` → `services/sync-worker/`

**Files to UPDATE:**
- `docker-compose.microservices.yml` (service name, labels, descriptions)
- `services/migration-worker/` directory name
- Documentation references to "migration-worker"
- Comments referencing the migration worker

## Proposed Solutions

### Solution A: Rename to sync-worker (RECOMMENDED)

**Effort:** Small | **Risk:** LOW | **Impact:** MEDIUM

```bash
# Step 1: Rename directory
mv services/migration-worker/ services/sync-worker/

# Step 2: Update docker-compose.microservices.yml
# Change: migration-worker → sync-worker
# Update: Container name, labels, descriptions

# Step 3: Update documentation
# Find and replace: "migration-worker" → "sync-worker"
```

**Pros:**
- Accurately reflects service purpose
- Aligns terminology with dual persistence architecture
- Clearer for operators and developers
- Small, atomic change

**Cons:**
- Requires updating docker-compose configuration
- Documentation updates needed

**Risk Assessment:** LOW - Purely a naming change with no functional impact.

### Solution B: Keep Current Name (NOT RECOMMENDED)

**Effort:** None | **Risk:** LOW | **Impact:** NONE

Maintain "migration-worker" name.

**Pros:**
- No immediate work required

**Cons:**
- Continues to be misleading
- Confuses architecture understanding
- Doesn't reflect actual service behavior

## Recommended Action

**Solution A: Rename to sync-worker**

The name "migration-worker" is fundamentally misleading. This service provides ongoing sync for dual persistence, not a one-time migration. The rename improves clarity and aligns with actual functionality.

## Acceptance Criteria

- [ ] `services/migration-worker/` renamed to `services/sync-worker/`
- [ ] `docker-compose.microservices.yml` updated with new service name
- [ ] Container name updated to `htbase-sync`
- [ ] All labels and descriptions updated
- [ ] Documentation updated to reference "sync-worker"
- [ ] Comments referencing "migration worker" updated
- [ ] Service still functions correctly after rename
- [ ] Tests pass with new naming

## Work Log

**2025-01-09**
- Architecture review identified misleading name
- Original todo suggested consolidation (incorrect approach)
- User clarified: this is ongoing sync, not one-time migration
- Dual persistence requires continuous sync worker
- Todo updated to rename instead of consolidate

### 2025-01-09 - Approved for Work
**By:** Claude Triage System (with user clarification)
**Actions:**
- Issue approved during triage session
- Scope clarified: rename only, no consolidation
- Migration → Sync (ongoing dual persistence)
- Status changed from pending → ready

**Learnings:**
- Important to distinguish migration (one-time) from sync (ongoing)
- Dual persistence architecture requires continuous sync worker
- Naming should reflect actual service behavior
- All workers serve different purposes and should remain separate:
  - api-gateway (HTTP API)
  - archive-worker (5 archivers - CPU intensive)
  - summarization-worker (LLM calls - external API)
  - storage-worker (GCS uploads - I/O intensive)
  - sync-worker (PostgreSQL → Firestore dual persistence)

## Resources

- **Review agents:** architecture-strategist
- **Similar issues:** N/A (new finding)
- **Documentation:**
  - `docs/DUAL_DATABASE_ARCHITECTURE.md`
  - `docs/WEBHOOK_GUIDE.md`
  - `shared/storage/dual_database_storage.py` (sync implementation)
- **Current architecture:**
  - `services/migration-worker/` (to be renamed)
  - `docker-compose.microservices.yml`
  - `services/migration-worker/worker.py`
