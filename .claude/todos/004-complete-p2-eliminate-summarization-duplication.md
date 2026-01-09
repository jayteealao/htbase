---
issue_id: "004"
status: "ready"
priority: "p2"
tags: ["code-review", "simplification", "duplication", "summarization"]
dependencies: []
---

# Problem Statement

**DUPLICATE SUMMARIZATION CODE: `app/services/summarization/` duplicates `shared/summarization/`**

The summarization implementation exists in both `app/services/summarization/` and `shared/summarization/` with 95%+ similarity. The `shared/` version is the canonical implementation used by microservices.

## Why This Matters

**Duplication Metrics:**
```
shared/summarization/        1,262 lines (canonical)
app/services/summarization/    433 lines (duplicate)
Similarity:                    95%+
```

**Component Breakdown:**
| Component | app/ Lines | shared/ Lines | Similarity | Action |
|-----------|------------|---------------|------------|--------|
| chunker.py | 76 | 142 | app is subset | DELETE app/ |
| prompt_builder.py | 189 | 189 | 98%+ | DELETE app/ |
| response_parser.py | 168 | 168 | 98%+ | DELETE app/ |
| providers.py | - | 351 | N/A | Already in shared/ |
| service.py | - | 412 | N/A | Already in shared/ |

**The `app/services/summarization/` versions are subsets or exact duplicates** of the `shared/` implementations.

## Evidence

**Import Usage Analysis:**
```bash
# app/ services are only used by:
app/services/summarizer.py  ← Only user of app/services/summarization/

# shared/ services are used by:
services/summarization-worker/
shared/summarization/service.py
```

**The microservices architecture uses `shared/summarization/` exclusively.** The `app/` versions are legacy from before the shared module was created.

## Affected Files

**Files to DELETE:**
- `app/services/summarization/chunker.py` (76 lines)
- `app/services/summarization/prompt_builder.py` (189 lines)
- `app/services/summarization/response_parser.py` (168 lines)
- `app/services/summarization/__init__.py` (reference)

**Files to UPDATE:**
- `app/services/summarizer.py` (update imports to use shared/)

## Proposed Solutions

### Solution A: Delete app/services/summarization/ (RECOMMENDED)

**Effort:** Small | **Risk:** LOW | **Impact:** MEDIUM

```bash
# Delete duplicate summarization directory
rm -rf app/services/summarization/

# Update imports in app/services/summarizer.py
# Change: from app.services.summarization import X
# To:      from shared.summarization import X
```

**Pros:**
- Eliminates 433 lines of duplicate code
- Single source of truth for summarization
- Forces use of canonical shared implementation
- Consistent with microservices architecture

**Cons:**
- Requires import updates in `app/services/summarizer.py`
- Need to verify tests still pass

**Risk Assessment:** LOW - The `shared/` implementations are used by microservices and are the canonical versions. The `app/` versions are legacy code.

### Solution B: Gradual Migration (NOT RECOMMENDED)

**Effort:** Medium | **Risk:** LOW | **Impact:** LOW

Deprecate `app/services/summarization/` over time.

**Pros:**
- Lower immediate risk perception

**Cons:**
- Prolongs technical debt
- Confusion during transition
- More overall effort

## Recommended Action

**Solution A: Delete app/services/summarization/**

This is straightforward dead code removal. The `shared/summarization/` directory is the canonical implementation used by microservices. The `app/` versions are legacy code from before the shared module was created.

## Acceptance Criteria

- [ ] All files in `app/services/summarization/` deleted
- [ ] Imports in `app/services/summarizer.py` updated to use `shared.summarization.*`
- [ ] Tests pass with new imports
- [ ] No broken imports in codebase
- [ ] Code reduced by ~433 lines

## Work Log

**2025-01-09**
- Pattern recognition analysis identified 95%+ duplication
- Todo file created for tracking
- Awaiting approval to proceed with deletion

### 2025-01-09 - Approved for Work
**By:** Claude Triage System
**Actions:**
- Issue approved during triage session
- Status changed from pending → ready
- Ready to be picked up and worked on

**Learnings:**
- Straightforward duplicate code removal
- shared/ versions are canonical (used by microservices)
- Should be done after #001 (storage duplication) as both follow same pattern

## Resources

- **Review agents:** pattern-recognition-specialist, senior-code-reviewer
- **Similar issues:** #001 (storage duplication)
- **Documentation:**
  - `shared/summarization/README.md` (if exists)
- **Files affected:**
  - `app/services/summarization/*` (3 files, 433 lines)
  - `shared/summarization/*` (canonical)
  - `app/services/summarizer.py` (needs import update)
