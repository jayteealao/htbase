---
name: start-session
description: Bootstrap a new work session with folder structure and README
args:
  EXPLANATION:
    description: Natural language explanation of what this session is about, what you want to accomplish, and any relevant context
    required: true
---

# ROLE
You are a session initializer. Your job is to bootstrap a self-contained work session under `.claude/<SESSION_SLUG>/` and update the global session index at `.claude/README.md`.

# HARD RULES
- SESSION_SLUG must be lowercase kebab-case and specific
- Infer all session metadata from the EXPLANATION provided
- Use AskUserQuestion tool when critical information is unclear or needs confirmation
- Never create duplicate entries in `.claude/README.md`; update if it exists
- Create all folders and files on disk automatically
- Parse and update existing `.claude/README.md` intelligently

# WORKFLOW

## Step 1: Analyze EXPLANATION and infer session metadata

Read the EXPLANATION carefully and extract/infer:

1. **SESSION_SLUG** (required)
   - Generate a descriptive lowercase kebab-case identifier from the explanation
   - Must match: `^[a-z0-9]+(-[a-z0-9]+)*$`
   - Examples: `csv-bulk-import`, `checkout-500`, `auth-timeout-fix`, `refactor-payment-state`
   - Keep it short (2-4 words) but specific enough to identify the work

2. **TITLE** (required)
   - Extract or generate a one-line human-readable title
   - Should be concise (5-10 words max)

3. **WORK_TYPE** (required)
   - Infer from the explanation which type applies:
     - `error_report`: Fixing a specific bug or error
     - `incident`: Production issue requiring immediate attention + postmortem
     - `new_feature`: Adding new functionality to existing system
     - `refactor`: Restructuring existing code without changing behavior
     - `greenfield_app`: Building something entirely new from scratch
   - If unclear, use AskUserQuestion to clarify

4. **SCOPE** (required)
   - Infer the scope of work:
     - `repo`: Entire repository
     - `pr`: Specific pull request
     - `worktree`: Current working tree
     - `diff`: Specific commit range
     - `file`: Single file or small set of files
   - If unclear or if TARGET needs to be specified (e.g., PR URL, file path), use AskUserQuestion

5. **TARGET** (required)
   - Based on SCOPE, determine the target:
     - For `repo`: Use `.` or repository root
     - For `pr`: Ask for PR URL or base..head range if not provided
     - For `worktree`: Use `HEAD`
     - For `diff`: Ask for commit range (e.g., `main..feature-branch`)
     - For `file`: Ask for file path(s)
   - If you need this info, use AskUserQuestion

6. **CONTEXT** (required)
   - Extract "why now" from the explanation
   - Look for mentions of tickets, issues, specs, incident channels, or deadlines
   - If minimal context provided, summarize what you extracted

7. **CONSTRAINTS** (optional)
   - Look for mentions of:
     - Performance requirements
     - Security requirements
     - Compliance needs
     - Compatibility requirements
     - Time constraints
   - Leave empty if none mentioned

8. **NON_GOALS** (optional)
   - Look for explicit mentions of what's out of scope
   - Leave empty if not mentioned

9. **SUCCESS_CRITERIA** (required)
   - Infer 3-10 measurable success criteria from the explanation
   - What would constitute "done"?
   - Make them specific and testable
   - If the explanation is vague, propose reasonable criteria and confirm with AskUserQuestion if needed

10. **RISK_TOLERANCE** (required)
    - Infer from the work type and explanation:
      - `low`: Critical systems, security-sensitive, requires extensive review
      - `medium`: Standard features, moderate impact
      - `high`: Experimental, rapid prototyping, isolated changes
    - If unclear, ask the user

11. **DEFAULT_REVIEW_CHAIN** (required)
    - Infer based on WORK_TYPE:
      - **error_report**: `review-correctness, review-testing`
      - **incident**: `review-correctness, review-security, review-reliability`
      - **new_feature**: `review-correctness, review-testing, review-overengineering, review-security`
      - **refactor**: `review-refactor-safety, review-maintainability, review-testing`
      - **greenfield_app**: `review-architecture, review-correctness, review-testing, review-overengineering`
    - Adjust based on mentions of security, performance, or other concerns in EXPLANATION

## Step 2: Confirm unclear items with user (if needed)

If any CRITICAL information is unclear or needs confirmation, use AskUserQuestion tool to ask:
- WORK_TYPE if ambiguous
- SCOPE/TARGET if not inferable
- RISK_TOLERANCE if unclear
- Any other critical detail that affects the session structure

**DO NOT ask about:**
- SESSION_SLUG (generate it yourself)
- TITLE (generate it yourself)
- SUCCESS_CRITERIA (propose reasonable ones based on the explanation)
- CONSTRAINTS/NON_GOALS (leave empty if not mentioned)

## Step 3: Validate SESSION_SLUG
- Ensure it matches: `^[a-z0-9]+(-[a-z0-9]+)*$`
- If invalid, correct it automatically

## Step 4: Choose session date
- Use today's date in YYYY-MM-DD format

## Step 5: Determine "entrypoint artifacts" by WORK_TYPE

Based on WORK_TYPE, determine which artifacts need to be created first.

**With simplified file structure, all content goes into the core files:**

**error_report:**
- `plan.md` (research plan section)
- `work.md` (work log)
- `reviews.md` (repro harness, correctness review)

**incident:**
- `plan.md` (research plan, RCA, postmortem actions)
- `work.md` (work log)
- `reviews.md` (repro harness, security review, reliability review)

**new_feature:**
- `plan.md` (spec + research plan sections)
- `work.md` (work log)
- `reviews.md` (review findings)

**refactor:**
- `plan.md` (research plan section)
- `work.md` (work log)
- `reviews.md` (refactor-safety review)

**greenfield_app:**
- `plan.md` (spec + scope triage + research plan sections)
- `work.md` (work log)
- `reviews.md` (architecture review, testing review)

## Step 6: Create session folder tree

Create the following **simplified** folder structure under `.claude/<SESSION_SLUG>/`:

```
.claude/<SESSION_SLUG>/
  README.md
  plan.md
  work.md
  reviews.md
  research/
```

**Files:**
- `README.md` - Session metadata and navigation
- `plan.md` - Combined file for specs, implementation plans, and decisions
- `work.md` - Work log with checkpoints
- `reviews.md` - All review findings consolidated
- `research/` - Directory for autonomous agent outputs (codebase-mapper, web-research, etc.)

This simplified structure (5 items vs 13+ directories) reduces overhead for hobby projects while maintaining organization.

**Initialize core files:**

Create `plan.md` with:
```markdown
# {TITLE}

*This file consolidates specs, implementation plans, scope triage, and architectural decisions for this session.*

---
```

Create `work.md` with:
```markdown
# Work Log: {TITLE}

**Started:** {YYYY-MM-DD}
**Status:** In Progress

---
```

Create `reviews.md` with:
```markdown
# Reviews: {TITLE}

*This file consolidates all review findings (security, performance, correctness, etc.) for this session.*

---
```

## Step 7: Generate session README.md

Create `.claude/<SESSION_SLUG>/README.md` with the following structure:

```markdown
# {TITLE}

**Status:** Active
**Session:** {SESSION_SLUG}
**Date:** {YYYY-MM-DD}
**Work Type:** {WORK_TYPE}
**Scope:** {SCOPE}
**Target:** {TARGET}
**Risk Tolerance:** {RISK_TOLERANCE}

## Context

{CONTEXT items as bulleted list}

## Constraints

{CONSTRAINTS items as bulleted list, or "None specified" if empty}

## Non-Goals

{NON_GOALS items as bulleted list, or "None specified" if empty}

## Success Criteria

{SUCCESS_CRITERIA items as bulleted list}

## Default Review Chain

{DEFAULT_REVIEW_CHAIN as bulleted list with `/` prefix}

## Next Commands to Run

{Ordered list of next commands based on WORK_TYPE - see Step 3 mapping}

## Artifacts

### Planning & Specs
- [ ] [plan.md](./plan.md) - Specs, implementation plans, scope triage, and decisions

### Work Log
- [ ] [work.md](./work.md) - Implementation checkpoints and progress

### Reviews & Quality
- [ ] [reviews.md](./reviews.md) - All review findings (security, performance, correctness, etc.)

### Research
- [ ] [research/](./research/) - Autonomous agent outputs (codebase analysis, web research)

## How to Navigate This Session

1. Start with the artifacts listed in "Next Commands to Run"
2. Check off completed artifacts in the checklist above
3. Follow the default review chain before shipping
4. Update this README as the session progresses
5. Run `/close-session` when all success criteria are met

---

*Session created: {YYYY-MM-DD}*
```

## Step 8: Update global session index

Read `.claude/README.md`:
- If it doesn't exist, create it with:

```markdown
# Claude Sessions Index

This folder contains session-scoped engineering artifacts generated by slash commands.
Each session is self-contained under `.claude/<session_slug>/`.

## Sessions

```

Parse the existing file:
- Find the "Sessions" section
- Check if SESSION_SLUG already exists
- If exists: update the date and title on that line
- If not exists: append new entry at the bottom of the sessions list (chronological order)

Entry format:
```
- [{SESSION_SLUG}](./{SESSION_SLUG}/README.md) — {YYYY-MM-DD}: {TITLE}
```

## Step 9: Output session bootstrap summary

Print a comprehensive summary with:

### 0) Session Metadata
- session_slug: {value}
- title: {value}
- date: {value}
- status: Active
- work_type: {value}
- scope/target: {value}
- risk_tolerance: {value}
- default_review_chain: {value}

### 1) File Tree Created
{Tree representation of created folders}

### 2) Session README.md Location
Path: `.claude/{SESSION_SLUG}/README.md`

### 3) Global Index Updated
Entry added/updated in `.claude/README.md` (appended to bottom - chronological order):
```
- [{SESSION_SLUG}](./{SESSION_SLUG}/README.md) — {YYYY-MM-DD}: {TITLE}
```

### 4) Entry Artifacts to Produce First (ordered)
{List from Step 5 with full paths}

### 5) Next Command to Run (pre-filled)

**Note:** Since this is now the most recent session (last entry in `.claude/README.md`), you can omit `SESSION_SLUG` from subsequent commands and they will automatically use this session.

Provide the EXACT next command invocation with all parameters filled:

**For error_report or incident:**
```
/repro-harness
SESSION_SLUG: {SESSION_SLUG}
SCOPE: {SCOPE}
TARGET: {TARGET}
BUG_REPORT: <paste issue description or error logs>
```

**For new_feature or greenfield_app:**
```
/spec-crystallize
SESSION_SLUG: {SESSION_SLUG}
SCOPE: {SCOPE}
TARGET: {TARGET}
FEATURE_DESC: <high-level feature description>
```

**For refactor:**
```
/research-plan
SESSION_SLUG: {SESSION_SLUG}
SCOPE: {SCOPE}
TARGET: {TARGET}
GOAL: <refactor objective>
```

# IMPLEMENTATION NOTES

The agent should:
1. Parse the EXPLANATION and extract all relevant information
2. Use intelligent defaults where possible
3. Use AskUserQuestion only for critical missing information
4. Generate a descriptive SESSION_SLUG automatically
5. Create all folder structures and files on disk
6. Update the global index intelligently (no duplicates)
7. Provide a comprehensive summary with the next command to run

# IMPORTANT: Conversational and inference-based

This command is designed to be conversational. The user provides a natural language EXPLANATION, and you infer everything else. Be intelligent about:
- Generating a good SESSION_SLUG from the explanation
- Inferring the work type (bug fix vs feature vs refactor)
- Proposing reasonable success criteria
- Defaulting SCOPE to `repo` and TARGET to `.` if not specified
- Only asking questions when absolutely necessary

# IMPORTANT: Session ordering

Sessions in `.claude/README.md` are stored in **chronological order** (oldest first, newest last):
- New sessions are **appended to the bottom** of the list
- The **last entry** is always the most recently created session
- This allows subsequent commands to infer the current session by reading the last entry

# EXAMPLE USAGE

## Example 1: Simple feature request

**User input:**
```
/start-session
EXPLANATION: We need to add CSV bulk import functionality to the app. Users should be able to upload a CSV file, preview the data, and then commit it to the database. This needs to be idempotent in case they upload the same file twice.
```

**Agent infers:**
- SESSION_SLUG: `csv-bulk-import`
- TITLE: `CSV bulk import with preview and idempotent commit`
- WORK_TYPE: `new_feature`
- SCOPE: `repo`
- TARGET: `.`
- SUCCESS_CRITERIA:
  - Users can upload CSV files via UI
  - Preview shows parsed CSV data before commit
  - Duplicate uploads are detected and handled idempotently
  - All CSV parsing errors are surfaced to users
  - Feature includes tests for edge cases (empty files, malformed CSV, duplicates)
- RISK_TOLERANCE: `medium`
- DEFAULT_REVIEW_CHAIN: `review-correctness, review-testing, review-overengineering, review-security`

**Output:**
```markdown
# Session Bootstrap Complete

## 0) Session Metadata
- session_slug: csv-bulk-import
- title: CSV bulk import with preview and idempotent commit
- date: 2026-01-15
- status: Active
- work_type: new_feature
- scope/target: repo / .
- risk_tolerance: medium
- default_review_chain: review-correctness, review-testing, review-overengineering, review-security

## 1) File Tree Created
.claude/csv-bulk-import/
├── README.md
├── plan.md
├── work.md
├── reviews.md
└── research/

## 2) Session README.md Location
Path: `.claude/csv-bulk-import/README.md`

## 3) Global Index Updated
Entry appended to `.claude/README.md` (chronological order):
- [csv-bulk-import](./csv-bulk-import/README.md) — 2026-01-15: CSV bulk import with preview and idempotent commit

## 4) Entry Artifacts to Produce First (ordered)
1. .claude/csv-bulk-import/plan.md (spec section)
2. .claude/csv-bulk-import/plan.md (research plan section)
3. .claude/csv-bulk-import/work.md (work log)

## 5) Next Command to Run (pre-filled)

**Note:** Since this is now the most recent session, you can omit `SESSION_SLUG` from subsequent commands.

You can run:
```
/spec-crystallize
INPUTS: CSV bulk import functionality with preview and idempotent commit - users upload CSV, preview data, commit to database, with duplicate detection
```

Or with explicit session:
```
/spec-crystallize
SESSION_SLUG: csv-bulk-import
SCOPE: repo
TARGET: .
INPUTS: CSV bulk import functionality with preview and idempotent commit - users upload CSV, preview data, commit to database, with duplicate detection
```

## Example 2: Bug fix with minimal context

**User input:**
```
/start-session
EXPLANATION: The checkout flow is returning 500 errors when users try to apply discount codes
```

**Agent infers:**
- SESSION_SLUG: `checkout-500-discount`
- TITLE: `Fix 500 error on discount code application`
- WORK_TYPE: `error_report`
- SCOPE: `repo`
- TARGET: `.`
- SUCCESS_CRITERIA:
  - Discount codes can be applied without 500 errors
  - Root cause is identified and fixed
  - Tests added to prevent regression
  - Edge cases (expired codes, invalid codes, stacked discounts) are handled
- RISK_TOLERANCE: `low` (checkout is critical)
- DEFAULT_REVIEW_CHAIN: `review-correctness, review-testing`

## Example 3: Agent asks clarifying question

**User input:**
```
/start-session
EXPLANATION: Refactor the payment processing module to use the new gateway
```

**Agent response:**
Agent uses AskUserQuestion to ask:
- "What scope should this refactor cover?" (options: entire payment module, specific PR, just the gateway integration files)
- "What's the risk tolerance?" (options: low - extensive testing required, medium - standard review, high - rapid migration)

Then proceeds with session creation after receiving answers.
