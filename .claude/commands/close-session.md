---
description: "Finalize session artifacts with outcome summary, status, and global index update"
color: "blue"
---

# /close-session

**Purpose**: Finalize session artifacts so future readers can understand what happened, what shipped, and what remains. Updates both session-specific README and global session index.

**When to use**:
- At the end of a work session (whether complete, paused, or abandoned)
- Before switching to a different task/project
- When creating a PR for session work
- To document session outcomes for future reference

**INPUTS**:
```
/close-session
SESSION_SLUG: <kebab-case slug, must match existing session folder>
STATUS: <Done | Paused | Abandoned>
OUTCOME: <1-3 sentence outcome summary>
PR_OR_COMMIT: <optional: PR URL(s) or commit hashes>
ROLL_OUT: <none|canary|phased|full>
FOLLOW_UPS:
  - <optional bullets: remaining work, risks, debt items, owner (if applicable)>
ARTIFACTS_COMPLETED:
  - <bullets of key artifacts created/updated in this session>
```

**Parameter guide**:

- **SESSION_SLUG**: Kebab-case identifier matching existing `.claude/<SESSION_SLUG>/` directory
  - Must match regex: `^[a-z0-9]+(-[a-z0-9]+)*$`
  - Examples: `auth-refactor`, `payment-api-v2`, `session-workflow-plugin`

- **STATUS**: Current state of the session
  - `Done`: Session completed successfully, all goals achieved
  - `Paused`: Session paused, will resume later (e.g., waiting for review, external dependency)
  - `Abandoned`: Session cancelled or deprioritized (document why in OUTCOME)

- **OUTCOME**: 1-3 sentence summary of what was accomplished
  - Focus on deliverables and impact, not process
  - Example: "Completed authentication refactor with OAuth2 integration. Added 15 unit tests achieving 95% coverage. Ready for staging deployment."

- **PR_OR_COMMIT**: Links to code changes (optional)
  - PR URLs: `https://github.com/org/repo/pull/123`
  - Commit hashes: `abc123f` or `abc123f, def456g` (comma-separated)
  - Use "N/A" if no code changes (e.g., research session)

- **ROLL_OUT**: Deployment status
  - `none`: No deployment (WIP, research, or not yet merged)
  - `canary`: Deployed to 1-10% of traffic
  - `phased`: Deployed to subset (e.g., staging, internal users)
  - `full`: Deployed to 100% of production

- **FOLLOW_UPS**: Remaining work, blockers, or risks (optional)
  - Include owner (if applicable) for each item
  - Example: "Add rate limiting to new endpoints (security review needed)"
  - Use "None" if no follow-ups

- **ARTIFACTS_COMPLETED**: Key files/features created or updated
  - List specific files with brief descriptions
  - Example: "src/auth/oauth2.ts - OAuth2 client implementation"

---

## ROLE

You are a session closer. Your job is to finalize session artifacts so future readers can understand what happened, what shipped, and what remains.

**You must update BOTH**:
1. `.claude/<SESSION_SLUG>/README.md` (session-specific)
2. `.claude/README.md` (global index)

---

## HARD RULES

1. **Do not delete content** - Always append to existing documentation
2. **Keep global index format stable** - Add status suffix only, never change slug or link
3. **Never create duplicate index entries** - Check before adding
4. **Validate SESSION_SLUG format** - Must match `^[a-z0-9]+(-[a-z0-9]+)*$`
5. **Create missing directories** - If `.claude/<SESSION_SLUG>/` doesn't exist, create it with initial README
6. **Preserve existing content** - When updating READMEs, preserve all existing sections

---

## WORKFLOW

### Step 1: Validate SESSION_SLUG

**Task**: Verify SESSION_SLUG matches required format.

**Validation**:
- Regex: `^[a-z0-9]+(-[a-z0-9]+)*$`
- Valid examples: `auth-refactor`, `api-v2`, `session-workflow-plugin`
- Invalid examples: `Auth-Refactor` (uppercase), `api_v2` (underscore), `api-v2-` (trailing dash)

**If invalid**:
1. Explain why it's invalid
2. Propose 3 corrected slugs
3. Stop and ask user to choose

**Checklist**:
- [ ] SESSION_SLUG matches regex pattern
- [ ] SESSION_SLUG is lowercase
- [ ] SESSION_SLUG uses hyphens (not underscores or spaces)
- [ ] SESSION_SLUG doesn't start/end with hyphen

---

### Step 2: Check for Existing Session Directory

**Task**: Verify `.claude/<SESSION_SLUG>/` directory exists.

**Actions**:
```bash
# Check if session directory exists
ls -la .claude/<SESSION_SLUG>/
```

**If directory doesn't exist**:
1. Create directory: `.claude/<SESSION_SLUG>/`
2. Create initial README with basic structure
3. Proceed to Step 3

**If directory exists**:
1. Read existing README
2. Preserve all existing content
3. Proceed to Step 3

**Checklist**:
- [ ] Session directory exists or created
- [ ] Existing README read (if present)
- [ ] Ready to update session README

---

### Step 3: Update Session README

**Task**: Update `.claude/<SESSION_SLUG>/README.md` with closure information.

**File location**: `.claude/<SESSION_SLUG>/README.md`

**Actions**:

#### 3a. Update Status Line
Find the `Status:` line near the top and update it:
```markdown
Status: <STATUS>
```

#### 3b. Add/Update "Key Artifacts" Section
If missing, add near the top (after Overview):
```markdown
## Key Artifacts

- `path/to/file.ts` - Brief description
- `path/to/other.ts` - Brief description
```

Use ARTIFACTS_COMPLETED input to populate this section.

#### 3c. Add "Closure" Section at Bottom
Append a new `## Closure` section at the end:

```markdown
## Closure

- **Closed on**: <YYYY-MM-DD>
- **Status**: <STATUS>
- **Outcome**: <OUTCOME>
- **PR/Commits**: <PR_OR_COMMIT or "N/A">
- **Rollout**: <ROLL_OUT>
- **Key artifacts**:
  - <ARTIFACTS_COMPLETED bullets>
- **Follow-ups**:
  - <FOLLOW_UPS bullets or "None">
```

**Template for new README** (if directory didn't exist):
```markdown
# Session: <Session Title from OUTCOME>

**Started**: <YYYY-MM-DD>
**Status**: <STATUS>

## Overview

<Brief description derived from OUTCOME>

## Session Goals

<Infer from OUTCOME or use generic placeholder>

## Key Artifacts

<ARTIFACTS_COMPLETED bullets>

## Closure

- **Closed on**: <YYYY-MM-DD>
- **Status**: <STATUS>
- **Outcome**: <OUTCOME>
- **PR/Commits**: <PR_OR_COMMIT or "N/A">
- **Rollout**: <ROLL_OUT>
- **Key artifacts**:
  - <ARTIFACTS_COMPLETED bullets>
- **Follow-ups**:
  - <FOLLOW_UPS bullets or "None">
```

**Checklist**:
- [ ] Status line updated
- [ ] Key artifacts section present and updated
- [ ] Closure section added at bottom
- [ ] All input parameters included in closure
- [ ] Existing content preserved (not deleted)

---

### Step 4: Update Global Session Index

**Task**: Update `.claude/README.md` with session status tag.

**File location**: `.claude/README.md`

**Actions**:

#### 4a. Read Existing Index
```bash
cat .claude/README.md
```

#### 4b. Find Session Entry
Search for line matching:
```markdown
- [<SESSION_SLUG>](./<SESSION_SLUG>/README.md) — <date>: <title>
```

#### 4c. Add Status Tag
Append status tag at end of line (single token, consistent format):
- `Done` → ` [DONE]`
- `Paused` → ` [PAUSED]`
- `Abandoned` → ` [ABANDONED]`

**Example transformations**:
```markdown
# Before
- [auth-refactor](./auth-refactor/README.md) — 2025-01-15: Authentication refactor

# After (Done)
- [auth-refactor](./auth-refactor/README.md) — 2025-01-15: Authentication refactor [DONE]
```

#### 4d. If Entry Missing
If session entry doesn't exist in index:
1. Add new entry at top of sessions list
2. Use today's date
3. Derive title from OUTCOME or use "(session closed)"
4. Include status tag

**Example new entry**:
```markdown
- [session-workflow-plugin](./session-workflow-plugin/README.md) — 2026-01-15: Session Workflow Plugin [DONE]
```

#### 4e. If Index File Missing
Create `.claude/README.md` with structure:
```markdown
# Claude Code Sessions

This directory tracks all Claude Code sessions for this project.

## Sessions

- [<SESSION_SLUG>](./<SESSION_SLUG>/README.md) — <YYYY-MM-DD>: <title> [<STATUS>]

## Session Structure

Each session directory contains:
- `README.md` - Session overview, goals, outcomes, and artifacts
- Session-specific files and notes as needed

## Status Tags

- **[DONE]** - Session completed successfully
- **[PAUSED]** - Session paused, to be resumed later
- **[ABANDONED]** - Session abandoned or cancelled
```

**Checklist**:
- [ ] Global index file exists (created if missing)
- [ ] Session entry found or added
- [ ] Status tag appended (not duplicated)
- [ ] Slug link preserved (not changed)
- [ ] Entry sorted correctly (newest at top)

---

### Step 5: Produce Closure Summary

**Task**: Generate 5-10 bullet points suitable for PR description or project update.

**Format**:
```markdown
## Closure Summary

**Session**: <Session Title>
**Status**: <STATUS>
**Date**: <YYYY-MM-DD>

### Key Accomplishments

1. <Accomplishment 1 - be specific with numbers/files>
2. <Accomplishment 2>
3. <Accomplishment 3>
...

### Deliverables

- <Artifact 1 with line count or description>
- <Artifact 2>
...

### Follow-ups

<FOLLOW_UPS bullets or "None - all work completed.">
```

**Content guidelines**:
- **Be specific**: Include numbers (files created, lines written, tests added, coverage %)
- **Be concrete**: Name actual files, features, systems
- **Be outcome-focused**: What was delivered, not what was done
- **Be concise**: 1-2 sentences per bullet max

**Good examples**:
- ✅ "Created 42 comprehensive commands for session-workflow plugin covering code review, operational excellence, and observability"
- ✅ "Built wide-event observability system with tail sampling achieving 90% cost reduction while maintaining 100% signal"
- ✅ "Added 15 unit tests achieving 95% code coverage for authentication module"

**Bad examples**:
- ❌ "Worked on code review stuff" (too vague)
- ❌ "Had several meetings to discuss requirements" (process, not outcome)
- ❌ "Made progress on the feature" (not concrete)

**Checklist**:
- [ ] 5-10 bullets provided
- [ ] Bullets are specific and concrete
- [ ] Include quantitative metrics where applicable
- [ ] Suitable for PR description or project update
- [ ] Follow-ups clearly stated

---

## OUTPUT FORMAT

Present the closure summary to the user in the following format:

```markdown
---

## Closure Summary

**Session**: <Session Title>
**Status**: <STATUS>
**Date**: <YYYY-MM-DD>

### Key Accomplishments

1. <Accomplishment>
2. <Accomplishment>
...

### Deliverables

- <Artifact with description>
- <Artifact with description>
...

### Follow-ups

<List or "None - all work completed.">

---

**Session artifacts updated**:
- ✅ `.claude/<SESSION_SLUG>/README.md` updated
- ✅ `.claude/README.md` index updated
```

**Then provide**: Links to updated files for user verification.

---

## EXAMPLE OUTPUT 1: Completed Feature

**Input**:
```
/close-session
SESSION_SLUG: auth-oauth2-integration
STATUS: Done
OUTCOME: Completed OAuth2 integration with Google and GitHub providers. Added 15 unit tests achieving 95% coverage. Ready for staging deployment.
PR_OR_COMMIT: https://github.com/myorg/myapp/pull/456
ROLL_OUT: phased
FOLLOW_UPS:
  - Add rate limiting to OAuth endpoints (security review needed)
  - Update documentation with OAuth setup guide (documentation needed)
ARTIFACTS_COMPLETED:
  - src/auth/oauth2.ts - OAuth2 client implementation
  - src/auth/providers/google.ts - Google OAuth provider
  - src/auth/providers/github.ts - GitHub OAuth provider
  - tests/auth/oauth2.test.ts - 15 unit tests
  - config/oauth.yaml - OAuth configuration schema
```

**Closure summary output**:
```markdown
---

## Closure Summary

**Session**: OAuth2 Integration
**Status**: Done
**Date**: 2026-01-15

### Key Accomplishments

1. **Completed OAuth2 integration** with Google and GitHub authentication providers

2. **Achieved 95% test coverage** with 15 comprehensive unit tests covering success paths, error handling, and edge cases

3. **Created configuration schema** for OAuth setup with validation and environment-specific overrides

4. **Ready for staging deployment** with phased rollout plan

### Deliverables

- `src/auth/oauth2.ts` (450 lines) - OAuth2 client with PKCE flow support
- `src/auth/providers/google.ts` (180 lines) - Google OAuth provider implementation
- `src/auth/providers/github.ts` (165 lines) - GitHub OAuth provider implementation
- `tests/auth/oauth2.test.ts` (380 lines) - Comprehensive test suite (95% coverage)
- `config/oauth.yaml` (85 lines) - OAuth configuration schema with validation

### Follow-ups

- Add rate limiting to OAuth endpoints (security review needed)
- Update documentation with OAuth setup guide (documentation needed)

---

**Session artifacts updated**:
- ✅ `.claude/auth-oauth2-integration/README.md` updated
- ✅ `.claude/README.md` index updated
```

**Files updated**:

`.claude/auth-oauth2-integration/README.md`:
```markdown
# Session: OAuth2 Integration

**Started**: 2026-01-10
**Status**: Done

## Overview

Implement OAuth2 authentication with Google and GitHub providers to replace legacy username/password authentication.

## Session Goals

1. Implement OAuth2 client with PKCE flow
2. Add Google OAuth provider
3. Add GitHub OAuth provider
4. Achieve >90% test coverage
5. Create configuration schema

## Key Artifacts

- `src/auth/oauth2.ts` - OAuth2 client implementation
- `src/auth/providers/google.ts` - Google OAuth provider
- `src/auth/providers/github.ts` - GitHub OAuth provider
- `tests/auth/oauth2.test.ts` - 15 unit tests
- `config/oauth.yaml` - OAuth configuration schema

## Technical Decisions

### PKCE Flow
Implemented PKCE (Proof Key for Code Exchange) for enhanced security. This prevents authorization code interception attacks.

### Provider Abstraction
Created base `OAuthProvider` interface to support future providers (LinkedIn, Microsoft, etc.) without code duplication.

### Configuration
OAuth configuration stored in YAML with environment-specific overrides. Supports multiple redirect URIs for dev/staging/prod.

## Closure

- **Closed on**: 2026-01-15
- **Status**: Done
- **Outcome**: Completed OAuth2 integration with Google and GitHub providers. Added 15 unit tests achieving 95% coverage. Ready for staging deployment.
- **PR/Commits**: https://github.com/myorg/myapp/pull/456
- **Rollout**: phased
- **Key artifacts**:
  - `src/auth/oauth2.ts` - OAuth2 client implementation
  - `src/auth/providers/google.ts` - Google OAuth provider
  - `src/auth/providers/github.ts` - GitHub OAuth provider
  - `tests/auth/oauth2.test.ts` - 15 unit tests
  - `config/oauth.yaml` - OAuth configuration schema
- **Follow-ups**:
  - Add rate limiting to OAuth endpoints (security review needed)
  - Update documentation with OAuth setup guide (documentation needed)
```

`.claude/README.md`:
```markdown
# Claude Code Sessions

This directory tracks all Claude Code sessions for this project.

## Sessions

- [auth-oauth2-integration](./auth-oauth2-integration/README.md) — 2026-01-15: OAuth2 Integration [DONE]
- [payment-api-v2](./payment-api-v2/README.md) — 2026-01-12: Payment API v2 Migration [PAUSED]
- [database-migration](./database-migration/README.md) — 2026-01-08: Database Schema Migration [DONE]

## Session Structure

Each session directory contains:
- `README.md` - Session overview, goals, outcomes, and artifacts
- Session-specific files and notes as needed

## Status Tags

- **[DONE]** - Session completed successfully
- **[PAUSED]** - Session paused, to be resumed later
- **[ABANDONED]** - Session abandoned or cancelled
```

---

## EXAMPLE OUTPUT 2: Paused Session

**Input**:
```
/close-session
SESSION_SLUG: payment-api-v2
STATUS: Paused
OUTCOME: Completed payment processing migration to Stripe v2 API. Blocked on legal review of PCI compliance documentation before staging deployment.
PR_OR_COMMIT: https://github.com/myorg/myapp/pull/789
ROLL_OUT: none
FOLLOW_UPS:
  - Legal review of PCI compliance docs (ETA: next deployment phase) (legal review needed)
  - Security penetration test after legal approval (security review needed)
  - Load testing with 10k req/s target (infrastructure work)
ARTIFACTS_COMPLETED:
  - src/payment/stripe-v2.ts - Stripe v2 API client
  - src/payment/webhooks.ts - Stripe webhook handlers
  - tests/payment/stripe-v2.test.ts - Integration tests
  - docs/pci-compliance.md - PCI DSS compliance documentation
```

**Closure summary output**:
```markdown
---

## Closure Summary

**Session**: Payment API v2 Migration
**Status**: Paused
**Date**: 2026-01-15

### Key Accomplishments

1. **Migrated payment processing to Stripe v2 API** with support for payment intents, saved cards, and 3D Secure authentication

2. **Implemented webhook handlers** for payment.succeeded, payment.failed, and subscription events with idempotency

3. **Completed PCI compliance documentation** covering data flow, encryption, access controls, and audit logging

4. **Blocked on legal review** - awaiting sign-off on PCI compliance docs before staging deployment

### Deliverables

- `src/payment/stripe-v2.ts` (620 lines) - Stripe v2 API client with payment intents
- `src/payment/webhooks.ts` (340 lines) - Webhook handlers with idempotency
- `tests/payment/stripe-v2.test.ts` (480 lines) - Integration tests with Stripe test mode
- `docs/pci-compliance.md` (85 pages) - PCI DSS compliance documentation

### Follow-ups

- Legal review of PCI compliance docs (ETA: next deployment phase) (legal review needed)
- Security penetration test after legal approval (security review needed)
- Load testing with 10k req/s target (infrastructure work)

---

**Session artifacts updated**:
- ✅ `.claude/payment-api-v2/README.md` updated
- ✅ `.claude/README.md` index updated
```

---

## EXAMPLE OUTPUT 3: Abandoned Session

**Input**:
```
/close-session
SESSION_SLUG: graphql-migration
STATUS: Abandoned
OUTCOME: GraphQL migration abandoned due to decision to stick with REST API. Completed research and prototype, but approach doesn't align with your expertise and timeline constraints.
PR_OR_COMMIT: N/A
ROLL_OUT: none
FOLLOW_UPS:
  - Document learnings in architecture decision record (@tech-leads)
  - Archive prototype code to internal-tools repo (infrastructure work)
ARTIFACTS_COMPLETED:
  - research/graphql-evaluation.md - GraphQL vs REST comparison
  - prototypes/graphql-server/ - Apollo Server prototype
  - docs/migration-plan.md - Migration plan (not executed)
```

**Closure summary output**:
```markdown
---

## Closure Summary

**Session**: GraphQL Migration (Abandoned)
**Status**: Abandoned
**Date**: 2026-01-15

### Key Accomplishments

1. **Completed comprehensive evaluation** of GraphQL vs REST for our use case, documenting tradeoffs in schema complexity, caching, and your expertise

2. **Built functional prototype** with Apollo Server demonstrating federated schema across 3 services

3. **Documented migration plan** with 4-phase rollout strategy (deprecated but preserved for future reference)

4. **Decision to abandon** - GraphQL benefits don't outweigh migration costs given timeline and your expertise constraints

### Deliverables

- `research/graphql-evaluation.md` (40 pages) - Comprehensive GraphQL vs REST analysis
- `prototypes/graphql-server/` (2,800 lines) - Apollo Server prototype with schema federation
- `docs/migration-plan.md` (25 pages) - Migration plan (not executed, archived for reference)

### Follow-ups

- Document learnings in architecture decision record (@tech-leads)
- Archive prototype code to internal-tools repo (infrastructure work)

---

**Session artifacts updated**:
- ✅ `.claude/graphql-migration/README.md` updated
- ✅ `.claude/README.md` index updated
```

---

## TIPS FOR EFFECTIVE SESSION CLOSURE

### 1. Be Specific and Concrete
- ❌ "Made progress on feature"
- ✅ "Completed OAuth2 integration with Google and GitHub providers (450 lines, 95% test coverage)"

### 2. Include Quantitative Metrics
- Lines of code written
- Test coverage percentage
- Number of tests added
- Performance improvements (latency, throughput)
- Cost reductions

### 3. Document Blockers for Paused Sessions
- Who is blocking (person (if delegated))
- What they need to do
- Expected timeline (ETA)

### 4. Preserve Learnings for Abandoned Sessions
- Why it was abandoned (architecture decision, timeline, priority shift)
- What was learned (document in ADR)
- What can be reused (archive, don't delete)

### 5. Link to Related Artifacts
- PR URLs (not just PR numbers)
- Commit hashes (full or short)
- Wiki pages, ADRs, Confluence docs
- JIRA tickets, Linear issues

### 6. Make Follow-ups Actionable
- ❌ "Need to do more testing"
- ✅ "Load test with 10k req/s target (infrastructure work, ETA: next deployment phase)"

### 7. Use Consistent Status Tags
- Always use `[DONE]`, `[PAUSED]`, `[ABANDONED]` in brackets
- Never use variants like `(done)`, `COMPLETED`, `finished`

### 8. Keep Global Index Clean
- Newest sessions at top
- Consistent date format (YYYY-MM-DD)
- Don't change slug links
- Only append status tags

---

## VALIDATION CHECKLIST

Before finishing, verify:

**Session README** (`.claude/<SESSION_SLUG>/README.md`):
- [ ] Status line updated to match STATUS input
- [ ] Key artifacts section present and complete
- [ ] Closure section added at bottom
- [ ] All input parameters included
- [ ] Existing content preserved (not deleted)
- [ ] Markdown formatting valid

**Global Index** (`.claude/README.md`):
- [ ] Index file exists
- [ ] Session entry present
- [ ] Status tag appended correctly
- [ ] No duplicate entries
- [ ] Entries sorted (newest first)
- [ ] Markdown formatting valid

**Closure Summary**:
- [ ] 5-10 specific accomplishment bullets
- [ ] Quantitative metrics included
- [ ] Deliverables listed with descriptions
- [ ] Follow-ups actionable with owners
- [ ] Suitable for PR description or project update

---

**End of /close-session command**
