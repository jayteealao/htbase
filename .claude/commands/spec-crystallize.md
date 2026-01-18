---
name: spec-crystallize
description: Convert ambiguous feature requests into implementable specifications
args:
  SESSION_SLUG:
    description: The session identifier (from /start-session). If not provided, uses the most recent session from .claude/README.md
    required: false
  INPUTS:
    description: Natural language description of the feature, or paste product request, ticket, user story, screenshots text, Slack notes, etc.
    required: true
  SCOPE:
    description: Scope of the work
    required: false
    choices: [repo, pr, worktree, diff, file]
  TARGET:
    description: Target of the work (PR URL, commit range, file path, or repo root)
    required: false
  STAKEHOLDERS:
    description: Roles or teams involved (optional)
    required: false
  CONSTRAINTS:
    description: Technical or business constraints (optional)
    required: false
  NON_GOALS:
    description: Explicit out-of-scope items (optional)
    required: false
  RISK_TOLERANCE:
    description: Risk tolerance level for this work
    required: false
    choices: [low, medium, high]
  OUTPUT_STYLE:
    description: Output style for the spec
    required: false
    choices: [engineering, product, mixed]
---

# ROLE
You are a spec author. Your job is to convert ambiguous inputs into an implementable specification that engineering can execute and QA can verify.

# SPEC RULES
- Separate: Requirements vs Design vs Open Questions
- Prefer testable language: "Given/When/Then", measurable thresholds, explicit error cases
- Default to least scope that still solves the user problem (avoid overengineering)
- If inputs conflict, propose a resolution and mark it as "Decision Needed"

# WORKFLOW

## Step 0: Infer SESSION_SLUG if not provided

If SESSION_SLUG is not provided:
1. Read `.claude/README.md`
2. Parse the "Sessions" section
3. Extract the **last** session slug from the list (format: `- [session-slug](./session-slug/README.md) — YYYY-MM-DD: Title`)
   - Sessions are in chronological order, so the last entry is the most recently created
4. Use that as SESSION_SLUG
5. If `.claude/README.md` doesn't exist or has no sessions, stop and tell user to run `/start-session` first

If SESSION_SLUG was provided, use it as-is.

## Step 1: Validate session exists

Check that `.claude/<SESSION_SLUG>/` exists:
- If it doesn't exist, stop and tell the user to run `/start-session` first
- If it exists, read `.claude/<SESSION_SLUG>/README.md` to understand the session context

## Step 2: Parse and infer metadata

From INPUTS and session context, infer:

1. **SCOPE/TARGET** (if not provided)
   - Default to values from session README
   - If not in session README, default to `repo` and `.`

2. **STAKEHOLDERS** (if not provided)
   - Infer from INPUTS (mentions of teams, roles, users)
   - Leave empty if not mentioned

3. **CONSTRAINTS** (if not provided)
   - Extract from INPUTS or session README
   - Look for: performance, security, compliance, compatibility, time constraints
   - Leave empty if not mentioned

4. **NON_GOALS** (if not provided)
   - Extract from INPUTS or session README
   - Look for phrases like "out of scope", "not including", "deferred"
   - Leave empty if not mentioned

5. **RISK_TOLERANCE** (if not provided)
   - Use value from session README
   - If not in session, default to `medium`

6. **OUTPUT_STYLE** (if not provided)
   - `engineering`: Technical, API-focused, data model emphasis
   - `product`: User journey focus, UX emphasis, less technical detail
   - `mixed`: Balanced (default)
   - Infer from STAKEHOLDERS or default to `mixed`

## Step 2.5: Pre-Research Interview (Multi-Round)

**CRITICAL**: Ask clarifying questions to understand user intent before research begins.

This is a **multi-round interview** to uncover non-obvious details and clarify ambiguities.

### Create interview directory

Create `.claude/<SESSION_SLUG>/interview/` directory if it doesn't exist.

### Round 1: Core Requirements Clarification

Use **AskUserQuestion** to ask 2-4 targeted questions based on INPUTS analysis:

**Question categories to consider:**
1. **Problem Scope**: "What specific user problem are we solving that existing features don't address?"
2. **Success Definition**: "How will we know this feature is successful? What metrics or user feedback matter most?"
3. **Critical Constraints**: "Are there non-negotiable technical, business, or timeline constraints I should know about?"
4. **User Context**: "Who are the primary users and what's their current workaround or pain point?"

**Example questions:**
- "You mentioned [feature X]. Should this work for [edge case Y], or is that explicitly out of scope?"
- "When you say [ambiguous term], do you mean [interpretation A] or [interpretation B]?"
- "I see we need [capability]. Does this need to support [advanced use case] or just [basic use case]?"

Store Round 1 answers.

### Round 2: Non-Obvious Details (Conditional)

Based on Round 1 answers, ask **2-3 deeper questions** about:

**Question categories:**
1. **Edge Cases**: "What should happen when [boundary condition]?"
2. **Integration Assumptions**: "Should this integrate with [existing system X] or work standalone?"
3. **Trade-offs**: "Would you prefer [fast + simple] or [slower + robust]?"
4. **Data Handling**: "What happens to existing data when [scenario]?"

**When to ask Round 2:**
- If Round 1 revealed significant ambiguities
- If INPUTS is vague on critical details
- If you need to choose between multiple valid approaches

**When to skip Round 2:**
- If Round 1 answers were comprehensive
- If INPUTS is already detailed and clear

Store Round 2 answers (if conducted).

### Round 3: Final Validation (Optional)

**Only if needed**, ask 1-2 final questions to:
- Resolve remaining critical ambiguities
- Confirm assumptions that would significantly impact the spec
- Validate understanding of complex requirements

**When to skip Round 3:**
- Most cases - only use if truly necessary

Store Round 3 answers (if conducted).

### Store Interview Results

Create `.claude/<SESSION_SLUG>/interview/spec-crystallize-interview.md`:

```markdown
---
command: /spec-crystallize
session_slug: {SESSION_SLUG}
date: {YYYY-MM-DD}
interview_stage: pre-research
---

# Pre-Research Interview

## Round 1: Core Requirements

**Q1: {Question}**
A: {User's answer}

**Q2: {Question}**
A: {User's answer}

{...}

## Round 2: Non-Obvious Details

{If conducted}

## Round 3: Final Validation

{If conducted}

## Key Insights

- {Insight 1 from interview}
- {Insight 2 from interview}
- {Insight 3 from interview}
```

**Use these answers** when generating the spec in Step 5.

## Step 3: Research Phase

### Step 3a: Create research directory

Create `.claude/<SESSION_SLUG>/research/` directory if it doesn't exist.

### Step 3b: Execute research

Spawn **codebase-mapper agent** (5-7 minutes):
```
Task: Spawn codebase-mapper agent

Input parameters:
- feature_description: {Extracted from INPUTS}
- component_type: {Inferred from INPUTS - API, UI, data model, worker, etc.}
- scope: {SCOPE value}
- target: {TARGET value}
- constraints: {CONSTRAINTS if provided}
- frameworks: {Inferred from codebase or session context}
- session_slug: {SESSION_SLUG}

Expected output: `.claude/<SESSION_SLUG>/research/codebase-mapper.md`
```

Wait for agent completion and read output, then proceed to Step 4.

### Step 3c: Read research results

Read `.claude/<SESSION_SLUG>/research/codebase-mapper.md` for key findings:
- Similar features and patterns
- Existing terminology and conventions
- Integration points and dependencies

**Fallback:** If agent fails or times out, do manual research with Glob/Grep/Read:
1. **Find similar flows/components**
   - Search for related features, similar user flows, or comparable UI components
   - Identify naming conventions and patterns to align with

2. **Identify impacted surfaces**
   - UI components, API endpoints, data models, background jobs, config, permissions

3. **Document findings**
   - Note relevant file paths and line numbers
   - Capture existing terminology and patterns

## Step 3.5: Post-Research Interview (Multi-Round)

**CRITICAL**: Validate research findings and clarify gaps discovered during research.

This is a **multi-round interview** to ensure research insights align with user expectations.

### Round 1: Research Findings Validation

Present **key research findings** and ask **2-3 validation questions**:

**Present findings:**
- "I found {count} similar features: {list with file paths}"
- "The codebase uses {pattern X} for {purpose}"
- "Integration points identified: {list}"

**Ask validation questions:**
1. **Pattern Alignment**: "I found we handle {similar feature} using {pattern}. Should we follow the same approach for your feature?"
2. **Gap Identification**: "I didn't find examples of {specific aspect}. Is this a new capability, or should I look elsewhere?"
3. **Priority Validation**: "Research suggests {approach X} aligns with our architecture. Does this match your vision?"

**Example questions:**
- "I found that similar features use {technology/pattern}. Should we stick with that, or is there a reason to diverge?"
- "The research shows {finding}, but you mentioned {requirement}. How should we reconcile this?"
- "I found {conflicting patterns A and B} in the codebase. Which aligns better with your goals?"

Store Round 1 answers.

### Round 2: Ambiguity Resolution (Conditional)

If research revealed **conflicting patterns, missing examples, or gaps**, ask **1-3 targeted questions**:

**Question categories:**
1. **Conflicting Patterns**: "I found two approaches: {A} and {B}. Which should we follow?"
2. **Missing Examples**: "I couldn't find {specific pattern}. Should we create a new pattern or adapt {existing approach}?"
3. **Design Direction**: "Based on research, I'm leaning toward {approach}. Does this align with your expectations?"
4. **Risk Trade-offs**: "Research shows {risk X}. Are you comfortable with {mitigation}, or should we take a different approach?"

**When to ask Round 2:**
- If research found conflicting patterns
- If critical examples are missing
- If user's requirements seem to conflict with codebase norms

**When to skip Round 2:**
- If research was conclusive and aligned with requirements
- If Round 1 validation covered all gaps

Store Round 2 answers (if conducted).

### Round 3: Final Confirmation (Optional)

**Only if needed**, ask 1-2 final questions to:
- Confirm high-risk architectural decisions
- Validate complex design choices
- Ensure critical assumptions are correct

Store Round 3 answers (if conducted).

### Update Interview Document

Append to `.claude/<SESSION_SLUG>/interview/spec-crystallize-interview.md`:

```markdown
---

## Post-Research Interview

### Research Summary Presented
- Similar features: {list}
- Patterns identified: {list}
- Integration points: {list}
- Gaps found: {list}

### Round 1: Research Validation

**Q1: {Question}**
A: {User's answer}

**Q2: {Question}**
A: {User's answer}

{...}

### Round 2: Ambiguity Resolution

{If conducted}

### Round 3: Final Confirmation

{If conducted}

### Key Decisions

- {Decision 1 based on post-research interview}
- {Decision 2 based on post-research interview}
- {Decision 3 based on post-research interview}
```

**Use these answers** when generating the spec in Step 5, particularly for:
- Implementation approach selection
- Pattern alignment decisions
- Edge case handling
- Integration strategy

## Step 4: Analyze inputs and extract requirements

Parse INPUTS to identify:
- Core problem statement
- User personas/roles affected
- User journeys (happy path + failure paths)
- Functional requirements
- Non-functional requirements
- Edge cases mentioned
- Acceptance criteria hints

## Step 4.5: Identify Edge Cases

Manually identify 5-10 edge cases based on:
- Common patterns (empty/null, invalid formats, boundaries)
- Security basics (if applicable)
- Error codes from codebase-mapper (if available)
- Failure modes mentioned in requirements

## Step 5: Generate the spec

**IMPORTANT**: Incorporate insights from both interview stages:
- Use pre-research interview answers for requirements, constraints, and user journeys
- Use post-research interview answers for implementation approach and pattern alignment
- Reference interview document for key decisions: `.claude/<SESSION_SLUG>/interview/spec-crystallize-interview.md`

Create or append to `.claude/<SESSION_SLUG>/plan.md` with the following structure:

**Note:** If `plan.md` already exists (from a previous planning step), append this spec to it with a clear separator:
```markdown
---

# Spec: {Title}
```

If creating new file, start with:

```markdown
---
command: /spec-crystallize
session_slug: {SESSION_SLUG}
date: {YYYY-MM-DD}
scope: {SCOPE}
target: {TARGET}
stakeholders: {STAKEHOLDERS}
risk_tolerance: {RISK_TOLERANCE}
output_style: {OUTPUT_STYLE}
related:
  session: ../README.md
---

# Spec: {Feature Title}

## 0) Summary

**Problem statement:**
{1-3 sentences describing the problem this feature solves}

**Who is impacted:**
{User roles, teams, or personas affected}

**Why now:**
{Context for timing - why this feature is being built now}

**Non-goals:**
{Explicit list of what's out of scope}

## 1) Glossary & Concepts

Define key terms to prevent naming drift and align with codebase conventions:

- **Term 1**: Definition (if exists in codebase, note file paths)
- **Term 2**: Definition
- **Term 3**: Definition

## 2) User Journeys

### Journey 1: {Primary use case}

**Primary path:**
1. User does X
2. System responds with Y
3. User sees Z
4. ...

**Failure paths:**
- If A fails, then B
- If validation error on C, show D
- ...

### Journey 2: {Secondary use case}

{Repeat structure}

### Journey 3: {Edge case journey}

{Repeat structure}

## 3) Requirements

### Functional Requirements

- **FR1**: {Requirement in testable language}
  - Rationale: {Why this is needed}
  - Impact: {What surfaces are affected}

- **FR2**: {Requirement}
  - Rationale: {Why}
  - Impact: {What}

{Continue for all functional requirements}

### Non-Functional Requirements

- **NFR1**: Performance - {Specific threshold, e.g., "API response < 200ms p95"}
- **NFR2**: Security - {Specific requirement, e.g., "All inputs sanitized against XSS"}
- **NFR3**: Privacy - {Data handling requirement}
- **NFR4**: Reliability - {Uptime/error rate requirement}
- **NFR5**: Scalability - {Expected load, growth projections}

### Permissions & Roles

| Role/Permission | Can Create | Can Read | Can Update | Can Delete | Notes |
|-----------------|------------|----------|------------|------------|-------|
| Admin           | ✓          | ✓        | ✓          | ✓          | Full access |
| User            | ✓          | Own only | Own only   | Own only   | |
| Guest           | ✗          | ✗        | ✗          | ✗          | |

## 4) Implementation Surface

### UI Changes (if applicable)

**New components:**
- Component 1: {Description, location}
- Component 2: {Description, location}

**Modified components:**
- {Path/Component}: {What changes}

**States & transitions:**
- State 1 → State 2 (on action X)
- Error states: {List error UI states}

### API Changes (if applicable)

#### New Endpoints

**POST /api/v1/resource**
- Purpose: {What it does}
- Request:
  ```json
  {
    "field1": "string",
    "field2": 123
  }
  ```
- Response (200):
  ```json
  {
    "id": "uuid",
    "status": "created"
  }
  ```
- Errors:
  - 400: Invalid input (validation errors)
  - 401: Unauthorized
  - 403: Forbidden
  - 409: Resource already exists
  - 500: Server error

#### Modified Endpoints

**PATCH /api/v1/resource/:id**
- Changes: {What's being added/modified}
- New fields: {List new request/response fields}

### Data Model Changes (if applicable)

**New tables/collections:**
- Table: `resources`
  - Columns: id (uuid), name (string), created_at (timestamp), ...
  - Indexes: idx_name, idx_created_at
  - Relationships: belongs_to user, has_many items

**Modified tables/collections:**
- Table: `users`
  - New columns: preference_x (boolean, default: false)
  - Migrations needed: Yes

### Background Jobs (if applicable)

- Job: `ProcessResourceJob`
  - Trigger: When resource created
  - Frequency: On-demand
  - Duration: ~5 seconds
  - Failure handling: Retry 3x with exponential backoff

### Configuration (if applicable)

New config values needed:
- `FEATURE_ENABLED`: boolean, default false
- `MAX_UPLOAD_SIZE`: integer, default 10485760 (10MB)

### Permissions/Authorization (if applicable)

New permission checks:
- `can_create_resource`: Check user role is admin or owner
- `can_view_resource`: Check user owns resource or is admin

## 5) Edge Cases & Error Handling

| Edge Case | Expected Behavior | Error Code/Message |
|-----------|-------------------|-------------------|
| Empty input | Reject with validation error | 400: "Field X is required" |
| Duplicate submission | Return existing resource (idempotent) | 200: Returns existing |
| Invalid format | Parse error with helpful message | 400: "Expected JSON" |
| Rate limit exceeded | Throttle with retry-after | 429: "Rate limit exceeded, retry after 60s" |
| Partial failure | Rollback and return error | 500: "Operation failed, no changes made" |
| Concurrent modification | Last-write-wins or optimistic locking | 409: "Resource modified, refresh and retry" |
| Missing dependencies | Graceful degradation or error | 503: "Service temporarily unavailable" |

## 6) Acceptance Criteria (Testable)

Write as Given/When/Then for easy conversion to tests:

**AC1: Happy path - Create resource**
- Given: Authenticated user with create permission
- When: POST /api/v1/resource with valid payload
- Then: Resource created with 201, ID returned, visible in list

**AC2: Validation - Required fields**
- Given: Authenticated user
- When: POST /api/v1/resource with missing required field
- Then: 400 error, helpful validation message, no resource created

**AC3: Authorization - Unauthorized user**
- Given: Unauthenticated user
- When: POST /api/v1/resource
- Then: 401 error, no resource created

**AC4: Idempotency - Duplicate submission**
- Given: Resource already exists with same unique key
- When: POST /api/v1/resource with duplicate data
- Then: 200 OK, returns existing resource, no duplicate created

**AC5: Edge case - {Specific edge case}**
- Given: {Precondition}
- When: {Action}
- Then: {Expected result}

{Continue for all critical acceptance criteria, including negative cases}

## 7) Out of Scope / Deferred Ideas

Keep this list to prevent scope creep during implementation:

- {Idea 1}: Deferred because {reason} - consider for future iteration
- {Idea 2}: Out of scope because {reason}
- {Idea 3}: Not needed for MVP, revisit in phase 2

**Note:** For open questions, use inline `TODO:` comments in relevant sections instead of a separate table.
Example: "TODO: Decide auth method (OAuth vs JWT) - recommend OAuth for third-party integration"

## 8) Implementation Notes

**Key Patterns to Follow:**
{If codebase-mapper ran, reference the patterns:}
- Follow naming conventions from `{similar_file_path}`
- Use error handling pattern from `{example_path}`
- See [full codebase analysis](../research/codebase-mapper.md) for details

**Key Risks:**
{Merge top 2-3 risks from research or analysis:}
- Risk 1: {Description} - Mitigation: {How to reduce}
- Risk 2: {Description} - Mitigation: {How to reduce}

**Dependencies:**
{Only if blocking:}
- {External API/service}: Required for {what}
- {Team/resource}: Blocked on {what}

{If research agents ran:}
**Research Links:**
- [Codebase Analysis](../research/codebase-mapper.md) - Similar patterns and conventions
{If web-research ran:}
- [Web Research](../research/web-research.md) - Industry best practices and security
{If edge-case-generator ran:}
- [Edge Cases](../research/edge-cases.md) - Comprehensive edge case analysis

---

## Next Steps

1. Review this spec with stakeholders: {STAKEHOLDERS or "team"}
2. Resolve any TODO items inline in the spec
3. Run `/research-plan` to create implementation plan
4. Consider running `/decision-record` for significant architectural decisions

---

*Spec generated: {YYYY-MM-DD}*
*Session: [{SESSION_SLUG}](../README.md)*
```

## Step 6: Update session README

Update `.claude/<SESSION_SLUG>/README.md`:
1. Find the artifacts section
2. Check off `[ ]` → `[x]` for `plan.md` (spec section)
3. Add a "Recent Activity" section at the top if it doesn't exist:
   ```markdown
   ## Recent Activity
   - {YYYY-MM-DD}: Created spec via `/spec-crystallize`
   ```

## Step 7: Output summary

Print a summary:

```markdown
# Spec Crystallized

## Spec Location
Saved to: `.claude/{SESSION_SLUG}/plan.md` (spec section)

## Interview Summary
- Pre-research rounds conducted: {1-3}
- Post-research rounds conducted: {1-3}
- Key insights captured: {count}
- Interview document: `.claude/{SESSION_SLUG}/interview/spec-crystallize-interview.md`

## Key Findings from Research
- Similar features found: {count}
- Impacted surfaces: {UI, API, Data, Jobs, Config, Permissions}
- Naming patterns identified: {list}

## What's Defined
- ✅ Problem statement and user journeys
- ✅ {count} Functional requirements
- ✅ {count} Non-functional requirements
- ✅ Permissions matrix
- ✅ API/UI/Data contracts
- ✅ {count} Edge cases documented
- ✅ {count} Acceptance criteria (testable)
- ✅ Dependencies and risks identified

## Open Questions
{List open questions that need resolution, or "None - ready to plan"}

## Next Command to Run

/research-plan
SESSION_SLUG: {SESSION_SLUG}
SCOPE: {SCOPE}
TARGET: {TARGET}
GOAL: Plan implementation of {feature title} based on crystallized spec
```

# IMPORTANT: Interview-Driven Spec Crystallization

This command should:
1. **Infer SESSION_SLUG** from most recent session if not provided (read last entry from `.claude/README.md` - sessions are in chronological order)
2. **Conduct multi-round interviews** before and after research to clarify user intent:
   - Pre-research: Understand requirements, constraints, and non-obvious details
   - Post-research: Validate findings, resolve conflicts, confirm design direction
3. **Infer defaults** from session README, INPUTS, and interview answers
4. **Do lightweight codebase research** to ground the spec in reality
5. **Align with existing patterns** rather than inventing new ones (validate with post-research interview)
6. **Flag conflicts** in INPUTS or research as questions in the interview
7. **Keep spec testable** - every requirement should be verifiable
8. **Avoid overengineering** - default to simplest solution
9. **Store interview results** in `.claude/<SESSION_SLUG>/interview/spec-crystallize-interview.md` for future reference

# OUTPUT STYLE VARIANTS

**Engineering style:**
- Heavy emphasis on API contracts, data models, technical constraints
- Detailed error handling and edge cases
- Performance metrics and scalability considerations

**Product style:**
- Heavy emphasis on user journeys and UX
- Less technical detail on implementation
- Focus on user value and business outcomes

**Mixed (default):**
- Balanced coverage of both user experience and technical implementation
- Enough detail for both product and engineering stakeholders

# EXAMPLE USAGE

## Simple Feature Spec (with explicit session)

**User input:**
```
/spec-crystallize
SESSION_SLUG: csv-bulk-import
INPUTS: Users need to upload CSV files with customer data. They should see a preview of what will be imported before committing. If they upload the same file twice, it should detect duplicates and not create duplicate records.
```

**Agent:**
1. Uses provided SESSION_SLUG: `csv-bulk-import`
2. Validates session exists
3. Reads session README (already has SCOPE: repo, TARGET: ., RISK_TOLERANCE: medium)
4. Does lightweight research:
   - Finds existing file upload component in `src/components/FileUpload.tsx`
   - Finds CSV parsing in `src/lib/csv-parser.ts`
   - Identifies API endpoint pattern: `/api/v1/resources`
5. Generates comprehensive spec with all sections
6. Updates session README
7. Outputs summary with next command

## Simple Feature Spec (session inferred)

**User input:**
```
/spec-crystallize
INPUTS: Users need to upload CSV files with customer data. They should see a preview of what will be imported before committing. If they upload the same file twice, it should detect duplicates and not create duplicate records.
```

**Agent:**
1. Reads `.claude/README.md` and finds most recent session: `csv-bulk-import`
2. Uses inferred SESSION_SLUG: `csv-bulk-import`
3. Validates session exists
4. Reads session README (already has SCOPE: repo, TARGET: ., RISK_TOLERANCE: medium)
5. Does lightweight research:
   - Finds existing file upload component in `src/components/FileUpload.tsx`
   - Finds CSV parsing in `src/lib/csv-parser.ts`
   - Identifies API endpoint pattern: `/api/v1/resources`
6. Generates comprehensive spec with all sections
7. Updates session README
8. Outputs summary with next command

**Result:**
Spec saved to `.claude/csv-bulk-import/plan.md` ready for `/research-plan`.

**Note:** This is the recommended workflow - after running `/start-session`, you can run subsequent commands without specifying SESSION_SLUG.
