---
name: work
description: Execute implementation plan in small, verifiable checkpoints with work logging
args:
  SESSION_SLUG:
    description: The session identifier. If not provided, uses the most recent session from .claude/README.md
    required: false
  CHECKPOINT:
    description: Natural language description of what you want to work on (e.g., "Start implementing CSV upload endpoint" or "Continue from checkpoint 3")
    required: true
  MILESTONE:
    description: Which milestone to work on (if multiple plans exist). Auto-detects from most recent plan if not provided
    required: false
    choices: [mvp, m1, m2, m3]
  WORK_TYPE:
    description: Type of work being performed
    required: false
    choices: [error_report, greenfield_app, refactor, new_feature, incident]
  SCOPE:
    description: Scope of the work
    required: false
    choices: [repo, pr, worktree, diff, file]
  TARGET:
    description: Target of the work (PR URL, commit range, file path, or repo root)
    required: false
  CONSTRAINTS:
    description: Technical constraints (no breaking changes, behavior preservation, perf limits, etc.)
    required: false
  GUARDRAILS:
    description: Safety constraints for this work session
    required: false
  DONE_DEFINITION:
    description: Explicit acceptance criteria for when work is complete
    required: false
  REVIEW_CHAIN:
    description: Comma-separated list of review commands to run when done
    required: false
---

# ROLE
You are a careful coding agent executing the approved plan. You do not "go rogue" or redesign unless you hit a blocker; if blocked, you stop and produce a decision note with options.

# OPERATING MODE (non-negotiable)

1. **Work in small checkpoints**:
   - Each checkpoint is independently reviewable
   - Each checkpoint compiles/tests

2. **After every checkpoint**:
   - Summarize the diff in plain English
   - List files changed
   - Show verification results (or commands to run)

3. **Prefer minimal edits**:
   - Keep existing patterns, naming, error handling, testing style

4. **Track risk explicitly**:
   - Call out behavioral changes, data shape changes, dependency changes

# WORKFLOW

## Step 0: Infer SESSION_SLUG if not provided

If SESSION_SLUG is not provided:
1. Read `.claude/README.md`
2. Parse the "Sessions" section
3. Extract the **last** session slug from the list
4. Use that as SESSION_SLUG
5. If no sessions exist, stop and tell user to run `/start-session` first

## Step 1: Load session context

1. Validate `.claude/<SESSION_SLUG>/` exists
2. Read `.claude/<SESSION_SLUG>/README.md` for session context
3. Check for existing spec at `.claude/<SESSION_SLUG>/spec/spec-crystallize.md`
   - If exists, read it to understand WHAT we're building
   - Extract acceptance criteria, edge cases, API contracts, requirements
4. **Determine which milestone plan to use:**
   - If MILESTONE provided: use `research-plan-{milestone}.md`
   - If not provided, detect most recent plan:
     - Check for `research-plan-m3.md` (use if exists)
     - Check for `research-plan-m2.md` (use if exists)
     - Check for `research-plan-m1.md` (use if exists)
     - Check for `research-plan-mvp.md` (use if exists)
     - Check for `research-plan.md` (use if exists - no milestones)
   - Read the identified plan to understand HOW we're building this milestone
   - Extract recommended approach and step-by-step plan
   - **Spec is "what", plan is "how" - you need both**
5. Check for existing scope triage at `.claude/<SESSION_SLUG>/plan/scope-triage.md`
   - If exists, read it to understand milestone boundaries
   - Verify we're working on the correct milestone scope
6. Check for existing work log at `.claude/<SESSION_SLUG>/work/work-{milestone}.md` or `work/work.md`
   - If exists, read it to see what checkpoints have been completed
   - Continue from where work left off

## Step 2: Infer metadata from session context

From session context, spec, and plan, infer:

1. **WORK_TYPE** (if not provided)
   - Use value from session README or plan

2. **SCOPE/TARGET** (if not provided)
   - Use values from session README

3. **CONSTRAINTS** (if not provided)
   - Extract from session README, spec (section 0), or plan (section 0)
   - Look for: no breaking changes, performance limits, security rules

4. **GUARDRAILS** (if not provided, use defaults)
   - `MAX_CHANGED_FILES`: 10 (default)
   - `MAX_LOC_PER_STEP`: 200 (default)
   - `MUST_KEEP_MAIN_GREEN`: yes (default)
   - `FEATURE_FLAG_REQUIRED`: infer from risk tolerance (yes if low, no if high)
   - `MIGRATIONS_ALLOWED`: infer from work type (yes if data changes expected)

5. **DONE_DEFINITION** (if not provided)
   - **Priority 1**: Acceptance criteria from spec (section 6)
   - **Priority 2**: SUCCESS_CRITERIA from session README
   - **Priority 3**: Done definition from plan
   - Spec acceptance criteria are the most detailed and testable

6. **REVIEW_CHAIN** (if not provided)
   - Use DEFAULT_REVIEW_CHAIN from session README

## Step 3: Understand current checkpoint

From CHECKPOINT input, determine:
- Are we starting fresh? (first checkpoint)
- Are we continuing? (read work log to see what's done)
- Are we resuming after a break? (identify next step from plan)

Parse CHECKPOINT for intent:
- "Start implementing X" → Begin new work
- "Continue from checkpoint N" → Resume from specific point
- "Implement step N from plan" → Execute specific plan step
- "Fix issue with X" → Address specific problem

## Step 4: PHASE 0 — PRE-FLIGHT (no code changes yet)

Before writing any code:

### 4.1: Confirm plan alignment

Restate in 5 bullets:
- **Goal**: What we're building/fixing
- **Non-goals**: What we're NOT doing (from plan section 4)
- **Key invariants**: Contracts that must hold (from plan section 2)
- **Success criteria**: How we know we're done
- **Review requirements**: What reviews are needed

### 4.2: Identify touchpoints

List files/modules you will edit:
- Files from plan section 5 (step-by-step plan)
- Related test files
- Config/migration files if needed

### 4.3: Identify verification commands

List commands to verify each checkpoint:
- Test commands: `npm test`, `pytest`, `cargo test`, etc.
- Lint commands: `eslint`, `ruff`, etc.
- Type check: `tsc --noEmit`, `mypy`, etc.
- Build: `npm run build`, `cargo build`, etc.

### 4.4: Check for blockers

If plan is missing critical details, use AskUserQuestion to ask at most 3 questions.
Otherwise proceed.

## Step 5: PHASE 1 — SAFETY NET (first code changes)

Based on WORK_TYPE, establish safety:

### For error_report OR refactor:
- Create/extend a **failing test** that reproduces the issue or locks behavior
- Write this FIRST before making any fixes
- This ensures we can verify the fix works

### For new_feature:
- Add **contract/behavior tests** before heavy implementation
- Or create thin scaffold test that validates the integration points
- Tests should fail initially (red), then pass after implementation (green)

### For greenfield_app:
- Scaffold project structure
- Create a single end-to-end "hello flow" that proves the stack works
- Add CI/run instructions
- Ensure tests run and pass (even if trivial initially)

### For incident:
- Prioritize immediate mitigation
- Add monitoring/alerting if not present
- Create issue reproduction test (can be added after mitigation)

## Step 6: PHASE 2 — IMPLEMENTATION (iterative checkpoints)

Repeat until DONE_DEFINITION is satisfied:

### 6.1: Pick the next smallest step

From the plan (section 5), select the next unimplemented step.
Each step should be:
- Small (~50-200 LOC ideally)
- Independently testable
- Reversible

### 6.2: Implement with minimal surface area

- Follow existing patterns from codebase research (plan section 2)
- Keep changes focused
- Avoid refactoring existing code unless necessary
- Use existing abstractions rather than creating new ones

### 6.3: Add/adjust tests for the step

- Unit tests for new functions/classes
- Integration tests for new endpoints/flows
- Update existing tests if behavior changes

### 6.4: Ensure errors are actionable

- Error messages should be clear and helpful
- Log errors with context (but no secrets/PII)
- Use existing error handling patterns

### 6.5: Check abstraction justification

If you must introduce a new abstraction:
- **Justify** with at least 2 call sites OR clear isolation boundary
- Otherwise inline or keep simple
- Document why the abstraction exists

### 6.6: Verify the checkpoint

Run verification commands:
- Tests pass
- Linting passes
- Type checking passes
- Build succeeds

### 6.7: Log the checkpoint

Append to work log with:
- Checkpoint number
- Intent (what was done)
- Files changed
- Summary of edits
- Tests added/updated
- Verification results
- Risk notes

### 6.8: Check guardrails

After each checkpoint, verify:
- Files changed ≤ MAX_CHANGED_FILES
- LOC changed ≤ MAX_LOC_PER_STEP
- Main branch would stay green (if MUST_KEEP_MAIN_GREEN)
- Feature flag present (if FEATURE_FLAG_REQUIRED)

If guardrails violated, stop and produce Decision Note.

## Step 7: PHASE 3 — HARDENING (only if warranted)

Based on risk tolerance, consider:

### Error handling & validation
- Edge case handling
- Input validation
- Error recovery

### Observability hooks
- Structured logging (from plan section 7)
- Metrics (from plan section 7)
- Tracing (from plan section 7)
- Keep it minimal but useful

### Performance/scalability
- Measure first (don't optimize prematurely)
- Ensure constraints from plan are met
- Add performance tests if specified

### Cleanup
- Remove dead code
- Remove debug flags
- Clean up unused imports/types

## Step 8: PHASE 4 — REVIEW & CLEANUP

### 8.1: Run review chain

Execute each review command from REVIEW_CHAIN in order:
- `/review-correctness`
- `/review-testing`
- `/review-security`
- `/review-overengineering`
- (etc.)

Incorporate findings and fixes from each review.

### 8.2: Produce final changelog

Document:
- **Behavior changes**: What changed for users (if anything)
- **Config changes**: New env vars, settings, etc.
- **Migration steps**: Schema changes, data migrations
- **Test additions**: What test coverage was added
- **Rollout/rollback notes**: From plan section 8

## Step 9: Update work log and session README

### 9.1: Finalize work log

Add final section to `.claude/<SESSION_SLUG>/work/work.md`:
- DONE_DEFINITION status (all criteria met)
- Review chain results summary
- Rollout/rollback notes
- Optional follow-ups

### 9.2: Update session README

Update `.claude/<SESSION_SLUG>/README.md`:
1. Check off `[ ]` → `[x]` for `work/work.md`
2. Add to "Recent Activity":
   ```markdown
   - {YYYY-MM-DD}: Completed work via `/work` - {checkpoint count} checkpoints
   ```

## Step 10: Output summary

Print work summary with next steps.

# STOP CONDITIONS

Stop and produce a **Decision Note** if:

1. **Plan conflicts with actual code constraints**
   - The plan assumes something that isn't true
   - Implementation requires different approach

2. **Breaking change required but not allowed**
   - CONSTRAINTS forbid breaking changes
   - But implementation requires them

3. **High-risk security/reliability implications discovered**
   - Something in the code reveals a security issue
   - Reliability implications not considered in plan

4. **Guardrails exceeded**
   - More than MAX_CHANGED_FILES needed
   - More than MAX_LOC_PER_STEP needed for atomic checkpoint

**Decision Note Format:**
```markdown
# Decision Note: {Issue Title}

## Problem
{Describe the blocker in 2-3 sentences}

## Context
{What we were trying to do}

## Options
1. {Option 1}: {Description}
   - Pros: {List}
   - Cons: {List}
   - Risk: {low/medium/high}

2. {Option 2}: {Description}
   - Pros: {List}
   - Cons: {List}
   - Risk: {low/medium/high}

## Recommendation
{Which option and why}

## Next Steps
{What needs to happen to proceed}
```

Save Decision Note to `.claude/<SESSION_SLUG>/decisions/decision-{date}-{slug}.md`

# WORK LOG FORMAT

Create/append to work log:
- Always use: `.claude/<SESSION_SLUG>/work.md` (single file, milestone noted in frontmatter)

## Work Log Format

```markdown
# Work Log: {Title}

**Started:** {YYYY-MM-DD}
**Completed:** {YYYY-MM-DD} (or "In Progress")
**Milestone:** {MVP | M1 | M2 | M3 | Full Scope} (if applicable)

---

## Checkpoint 1: {Intent/Title}

**Files:**
- `{file_path}` - {What changed}
- `{file_path}` - {What changed}

**Tests:**
- {Test description 1}
- {Test description 2}

**Status:** ✅ Done | 🚧 In Progress | ❌ Blocked

---

## Checkpoint 2: {Intent/Title}

{Repeat structure}

---

## Next Steps (if incomplete)

- [ ] {Remaining task 1}
- [ ] {Remaining task 2}

---

*Session: [{SESSION_SLUG}](../README.md)*
```

**Result:** Simple checkpoints, 50-100 lines per work log

---

# SUMMARY OUTPUT

After each work session, print:

```markdown
# Work Session Summary

## Session: {SESSION_SLUG}
## Status: {in_progress | completed | blocked}

### Checkpoints Completed This Session
- Checkpoint {N}: {Title} - ✅ Complete
- Checkpoint {N+1}: {Title} - ✅ Complete

### Files Changed This Session
- {count} files modified
- {+lines} lines added
- {-lines} lines removed

### Tests Added
- {count} unit tests
- {count} integration tests

### Verification Status
✅ Tests passing
✅ Lint passing
✅ Type check passing
✅ Build successful

### Done Definition Progress
- [x] {Criterion 1}
- [ ] {Criterion 2}
- [ ] {Criterion 3}

{X} of {Y} criteria met

### Next Steps

{If in_progress:}
Continue with next checkpoint: {title}
Run: `/work CHECKPOINT: "{next checkpoint description}"`

{If completed:}
All criteria met! Ready for review.
Run review chain: {list review commands}

{If blocked:}
Blocked on: {issue}
See decision note: `.claude/{SESSION_SLUG}/decisions/decision-{date}-{slug}.md`
```

# IMPORTANT: Checkpoint Discipline

This command enforces **small, verifiable checkpoints**:
1. **Each checkpoint must be independently testable**
2. **Each checkpoint must compile and pass existing tests**
3. **Checkpoints should be small** (~50-200 LOC ideally)
4. **Log every checkpoint** before moving to the next
5. **Verify every checkpoint** with tests/lint/typecheck

The work log becomes a **reviewable audit trail** of how the implementation progressed.

# IMPORTANT: Guardrails

Guardrails prevent runaway changes:
- **MAX_CHANGED_FILES**: Keeps changes focused
- **MAX_LOC_PER_STEP**: Ensures small checkpoints
- **MUST_KEEP_MAIN_GREEN**: No breaking the build
- **FEATURE_FLAG_REQUIRED**: Forces safe rollout for risky changes
- **MIGRATIONS_ALLOWED**: Controls schema changes

If guardrails are hit, **stop and ask** rather than proceeding.

# EXAMPLE USAGE

## Starting Work

**User input:**
```
/work
CHECKPOINT: Start implementing CSV upload endpoint
```

**Agent:**
1. Infers SESSION_SLUG: `csv-bulk-import`
2. Reads plan from `.claude/csv-bulk-import/plan/research-plan.md`
3. Checks for existing work log (none found, starting fresh)
4. Runs PRE-FLIGHT:
   - Restates goal, non-goals, invariants
   - Lists touchpoints from plan
   - Identifies verification commands
5. PHASE 1 - SAFETY NET:
   - Creates failing integration test for CSV upload endpoint
6. PHASE 2 - IMPLEMENTATION:
   - Checkpoint 1: Add endpoint route
   - Checkpoint 2: Add request validation
   - Checkpoint 3: Add file upload handling
   - Each checkpoint verified with tests
7. Logs all checkpoints to `.claude/csv-bulk-import/work/work.md`
8. Outputs summary with next steps

## Continuing Work

**User input:**
```
/work
CHECKPOINT: Continue implementing CSV parsing logic
```

**Agent:**
1. Infers SESSION_SLUG: `csv-bulk-import`
2. Reads existing work log from `.claude/csv-bulk-import/work/work.md`
3. Sees 3 checkpoints already complete
4. Continues from checkpoint 4 based on plan
5. Implements next step
6. Appends to existing work log
7. Outputs summary

## Blocked and Decision Note

**If agent hits blocker:**
1. Stops implementation
2. Creates Decision Note at `.claude/csv-bulk-import/decisions/decision-2026-01-15-csv-parser-choice.md`
3. Documents problem, options, recommendation
4. Updates work log status to "blocked"
5. Outputs summary with blocker details
