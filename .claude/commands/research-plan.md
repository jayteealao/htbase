---
name: research-plan
description: Create evidence-based implementation plan with research-first approach
args:
  SESSION_SLUG:
    description: The session identifier. If not provided, uses the most recent session from .claude/README.md
    required: false
  INPUTS:
    description: Natural language description OR paste error logs/stack trace/bug report/product spec/user story/refactor goal
    required: true
  MILESTONE:
    description: Which milestone to plan (if scope-triage exists). Defaults to 'mvp' if triage exists, otherwise plans full scope
    required: false
    choices: [mvp, m1, m2, m3, full]
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
    description: Technical or business constraints (optional)
    required: false
  NON_GOALS:
    description: Explicit out-of-scope items (optional)
    required: false
  RISK_TOLERANCE:
    description: Risk tolerance level for this work
    required: false
    choices: [low, medium, high]
  SUCCESS_CRITERIA:
    description: Measurable acceptance criteria (optional)
    required: false
  ASSUMPTIONS_ALLOWED:
    description: Whether assumptions are allowed in the plan (default yes)
    required: false
    choices: [yes, no]
---

# ROLE
You are a senior staff engineer doing research-first planning. Your output must be an actionable engineering plan, not vague advice.

# GLOBAL RULES (apply to ALL work types)

1. **Evidence-only**: When referencing code, always cite file paths + line ranges (or exact identifiers) and quote minimal snippets.
2. **Research first, then plan**:
   - ALWAYS spawn ALL 5 research agents in parallel (codebase-mapper, web-research, design-options, risk-analyzer, edge-case-generator)
   - Synthesize findings from all agents into cohesive understanding
   - Locate existing patterns in the codebase
   - Find nearest similar feature/bug/module and summarize what to reuse
   - Identify constraints implied by architecture, tests, CI, deployments
3. **Separate FACTS vs ASSUMPTIONS vs QUESTIONS**:
   - FACTS: Directly supported by inputs/code/research
   - ASSUMPTIONS: Educated guesses (label clearly)
   - QUESTIONS: Only those that change the plan
4. **Keep the plan executable**:
   - Each step should be small, verifiable, and revertible
   - Specify tests/checks to run per step
5. **Prefer minimal-change solutions** unless WORK_TYPE demands redesign
6. **Always include**: Testing strategy, observability impact, rollout/rollback
7. **Web research is mandatory**: Always research security (OWASP, CVE) and compare dependencies
8. **Justify every dependency**: Use 2-3 alternative comparison with sources
9. **Research iteratively**: Follow up on gaps with additional searches (limit: 2 rounds)
10. **Self-review is mandatory**: Review generated plan for errors, edge cases, and overengineering BEFORE finalizing

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

## Step 1: Validate session and load context

Check that `.claude/<SESSION_SLUG>/` exists:
- If it doesn't exist, stop and tell the user to run `/start-session` first
- Read `.claude/<SESSION_SLUG>/README.md` to understand session context
- Check for existing spec at `.claude/<SESSION_SLUG>/spec/spec-crystallize.md` (if it exists, read it)
- Check for existing scope triage at `.claude/<SESSION_SLUG>/plan/scope-triage.md` (if it exists, read it)
- Check for existing repro harness at `.claude/<SESSION_SLUG>/incidents/repro-harness.md` (if it exists, read it)

## Step 2: Determine milestone scope

If scope triage exists:
1. **MILESTONE** (if not provided)
   - Default to `mvp` if triage exists
   - User can override with explicit MILESTONE parameter

2. **Extract milestone scope from triage**
   - Read the appropriate milestone section (MVP / M1 / M2 / M3)
   - Extract:
     - Features included in this milestone
     - Features explicitly excluded (deferred to later)
     - Dependencies required for this milestone
     - Acceptance criteria for this milestone
     - Complexity level

3. **Focus plan on this milestone only**
   - Plan implements ONLY what's in this milestone
   - Reference what was built in previous milestones (if M1+)
   - Note dependencies on future milestones (if any)

If no triage exists:
- MILESTONE = `full` (plan entire scope)
- Use spec or INPUTS for full scope

## Step 3: Parse and infer metadata

From INPUTS, session context, milestone scope (if applicable), and any existing artifacts, infer:

1. **WORK_TYPE** (if not provided)
   - Use value from session README if available
   - Otherwise infer from INPUTS:
     - `error_report`: Bug fix, error logs, stack traces
     - `incident`: Production issue with urgency
     - `new_feature`: Adding new functionality
     - `refactor`: Restructuring without behavior change
     - `greenfield_app`: Building something entirely new
   - If unclear, use AskUserQuestion

2. **SCOPE/TARGET** (if not provided)
   - Default to values from session README
   - If not in session, default to `repo` and `.`

3. **CONSTRAINTS** (if not provided)
   - Extract from INPUTS or session README or spec
   - Look for: performance, security, compliance, compatibility, time constraints

4. **NON_GOALS** (if not provided)
   - Extract from INPUTS or session README or spec

5. **RISK_TOLERANCE** (if not provided)
   - Use value from session README
   - If not available, default to `medium`

6. **SUCCESS_CRITERIA** (if not provided)
   - Extract from INPUTS or session README or spec
   - If spec exists, use acceptance criteria from spec

7. **ASSUMPTIONS_ALLOWED** (if not provided)
   - Default to `yes`
   - If `no`, the plan must be fully concrete with no unknowns

## Step 3.5: Pre-Research Interview (Multi-Round)

**CRITICAL**: Ask clarifying questions to understand planning context before research begins.

This is a **multi-round interview (3-5 rounds)** to uncover non-obvious details and clarify planning ambiguities.

### Create interview directory

Create `.claude/<SESSION_SLUG>/interview/` directory if it doesn't exist.

### Round 1: Planning Context Clarification

Use **AskUserQuestion** to ask 2-3 targeted questions based on INPUTS, WORK_TYPE, and session context:

**Question categories to consider:**
1. **Work Type Validation**: "I inferred this is a {WORK_TYPE}. Is that correct, or should I approach this differently?"
2. **Success Criteria**: "What does 'done' look like for this work? What are the key metrics or outcomes?"
3. **Constraints Clarification**: "Are there critical constraints I should know about (performance, backward compatibility, timeline)?"
4. **Risk Tolerance**: "For risky decisions, should I prefer {conservative/safe} or {aggressive/fast}?"
5. **Scope Boundaries**: "Is {aspect X} in scope, or should I defer that?"

**Example questions:**
- "You mentioned [goal]. Does this need to work for [edge case Y], or can we start simpler?"
- "Should this implementation prioritize [speed] or [robustness]?"
- "Are there specific patterns or approaches you want me to follow or avoid?"
- "What's the most important thing to get right vs. what can we iterate on later?"

Store Round 1 answers.

### Round 2: Non-Obvious Planning Details (Conditional)

Based on Round 1 answers and WORK_TYPE, ask **2-3 deeper questions** about:

**Question categories:**
1. **Implementation Approach**: "Should I use {approach A} or {approach B} for {aspect}?"
2. **Testing Strategy**: "What level of test coverage is expected (basic/comprehensive)?"
3. **Rollout Expectations**: "Should this use feature flags, or can we ship directly?"
4. **Data Handling**: "How should we handle existing data during this change?"
5. **Backward Compatibility**: "Do we need to maintain compatibility with {old version/API}?"

**When to ask Round 2:**
- If Round 1 revealed multiple valid approaches
- If INPUTS is vague on implementation strategy
- If WORK_TYPE has significant design choices (refactor, new feature, greenfield)

**When to skip Round 2:**
- If Round 1 answers were comprehensive
- If INPUTS or spec already provides clear direction
- If WORK_TYPE is straightforward (bug fix with clear reproduction)

Store Round 2 answers.

### Round 3: Implementation Strategy

Ask **1-3 questions** about implementation preferences:

**Question categories:**
1. **Incremental vs. Big Bang**: "Should we break this into smaller shippable increments, or build it all at once?"
2. **Technology Choices**: "Are there specific libraries, frameworks, or tools you want to use or avoid?"
3. **Code Quality**: "What's more important: shipping fast or comprehensive test coverage and documentation?"
4. **Refactoring Scope**: "Should we clean up existing code while implementing this, or keep changes minimal?"

Store Round 3 answers.

### Round 4: Operational Considerations

Ask **1-2 questions** about operations and deployment:

**Question categories:**
1. **Monitoring**: "What metrics or logs are most important to track for this work?"
2. **Rollout Plan**: "Should this roll out gradually (feature flags, canary) or all at once?"
3. **Rollback Requirements**: "If we need to rollback, what's the acceptable downtime or data loss?"
4. **Dependencies**: "Are there any external services or external dependencies?"

Store Round 4 answers.

### Round 5: Final Planning Validation

Ask **1-2 final questions** to:
- Resolve critical trade-offs that impact the plan structure
- Validate assumptions about complexity or risk
- Confirm approach for high-risk decisions
- Ensure alignment on priorities and scope

Store Round 5 answers.

### Store Interview Results

Create `.claude/<SESSION_SLUG>/interview/research-plan-interview.md`:

```markdown
---
command: /research-plan
session_slug: {SESSION_SLUG}
date: {YYYY-MM-DD}
interview_stage: pre-research
work_type: {WORK_TYPE}
---

# Pre-Research Interview

## Round 1: Planning Context

**Q1: {Question}**
A: {User's answer}

**Q2: {Question}**
A: {User's answer}

{...}

## Round 2: Non-Obvious Planning Details

**Q1: {Question}**
A: {User's answer}

{...}

## Round 3: Implementation Strategy

**Q1: {Question}**
A: {User's answer}

{...}

## Round 4: Operational Considerations

**Q1: {Question}**
A: {User's answer}

{...}

## Round 5: Final Planning Validation

**Q1: {Question}**
A: {User's answer}

{...}

## Key Planning Insights

- {Insight 1 from interview}
- {Insight 2 from interview}
- {Insight 3 from interview}
```

**Use these answers** when:
- Choosing WORK_TYPE playbook (Step 5)
- Generating implementation approaches (Step 6)
- Creating step-by-step plan (Step 8)
- Defining test strategy (Step 9)
- Defining rollout strategy (Step 11)

## Step 4: RESEARCH PHASE

**CRITICAL**: Comprehensive research before planning is not optional.

### Step 4a: Create research directory

Create `.claude/<SESSION_SLUG>/research/` directory if it doesn't exist.

### Step 4b: Execute comprehensive research (ALL 5 agents in parallel)

**CRITICAL**: ALWAYS spawn ALL 5 research agents for comprehensive analysis.

Spawn all agents in parallel:

1. **codebase-mapper agent** (research scope: codebase exploration):
```
Input parameters:
- feature_description: {Extracted from INPUTS or spec}
- component_type: {Inferred from WORK_TYPE and INPUTS}
- scope: {SCOPE value}
- target: {TARGET value}
- constraints: {CONSTRAINTS if provided}
- frameworks: {Inferred from codebase or session context}
- session_slug: {SESSION_SLUG}

Expected output: `.claude/<SESSION_SLUG>/research/codebase-mapper.md`
```

2. **web-research agent** (research scope: codebase exploration):
```
Input parameters:
- research_topics: {Derived from spec + dependencies}
  * ALWAYS: Security best practices for {feature_type}
  * ALWAYS: OWASP guidelines, CVE checks for {tech_stack}
  * ALWAYS: Dependency comparison for top 2-3 libraries
  * CONDITIONAL: Performance patterns, case studies, cost analysis
- context: {Feature description from spec}
- focus_areas: [security, dependencies, performance, scalability]
- tech_stack: {From spec or inferred from codebase}
- depth: medium
- session_slug: {SESSION_SLUG}

Expected output: `.claude/<SESSION_SLUG>/research/web-research.md`
```

3. **design-options agent** (research scope: codebase exploration):
```
Input parameters:
- spec: {Feature requirements from spec.md}
- codebase_patterns: {Summary from codebase-mapper}
- industry_patterns: {Summary from web-research}
- constraints: {CONSTRAINTS from Step 3}
- session_slug: {SESSION_SLUG}

Expected output: `.claude/<SESSION_SLUG>/research/design-options.md`
```

4. **risk-analyzer agent** (research scope: codebase exploration):
```
Input parameters:
- feature_description: {From spec.md}
- design_approaches: {High-level options to consider}
- constraints: {CONSTRAINTS}
- risk_tolerance: {RISK_TOLERANCE}
- session_slug: {SESSION_SLUG}

Expected output: `.claude/<SESSION_SLUG>/research/risk-analysis.md`
```

5. **edge-case-generator agent** (research scope: codebase exploration):
```
Input parameters:
- feature_description: {From spec.md}
- context: {Session and implementation context}
- session_slug: {SESSION_SLUG}

Expected output: `.claude/<SESSION_SLUG>/research/edge-cases.md`
```

Wait for ALL 5 agents to complete (comprehensive codebase and web research) before proceeding to Step 4c.

### Step 4c: Read and synthesize all research findings

**CRITICAL**: Synthesize findings from ALL 5 agents into a cohesive understanding.

1. **Read codebase-mapper.md** and extract:
   - Similar features (2-3 examples with patterns)
   - Naming conventions and architectural patterns
   - Integration points and dependencies
   - Error handling patterns
   - Risk hotspots

2. **Read web-research.md** and extract:
   - Security findings: OWASP guidelines, CVEs, security advisories
   - Dependency comparisons: Library alternatives with pros/cons
   - Performance benchmarks (if applicable)
   - Case studies: Real-world implementations
   - Best practices: Industry standards and recommendations

3. **Read design-options.md** and extract:
   - 2-3 design approaches with trade-off analysis
   - Recommended approach with justification
   - Decision matrix
   - Alignment with codebase patterns

4. **Read risk-analysis.md** and extract:
   - Top 5-7 risks with likelihood × impact scores
   - Mitigations for each risk
   - Detection methods
   - Risk prioritization

5. **Read edge-cases.md** and extract:
   - Comprehensive edge case catalog (10 categories)
   - Security edge cases (OWASP patterns)
   - Error scenarios and handling strategies
   - Boundary conditions

6. **Synthesize findings**:
   - Cross-reference codebase patterns with industry best practices
   - Validate design options against risk analysis
   - Ensure dependencies address edge cases
   - Create unified view of: patterns + risks + options + edge cases

### Step 4d: Follow-up research (if gaps identified)

If initial research reveals gaps or ambiguities:
1. Identify missing information:
   - Incomplete dependency comparison
   - Unclear security considerations
   - Missing implementation examples
2. Generate targeted follow-up queries
3. Execute 1-2 additional web searches (limit: 2 rounds total)
4. Consolidate findings into research documents

Skip if initial research is comprehensive.

## Step 4.5: Post-Research Interview (Multi-Round)

**CRITICAL**: Validate research findings and clarify planning gaps discovered during research.

This is a **multi-round interview (3-5 rounds)** to ensure research insights align with user expectations and planning needs.

### Round 1: Research Findings Validation

Present **key research findings** and ask **2-3 validation questions**:

**Present findings:**
- "I found {count} similar features/patterns: {list with file paths}"
- "The codebase uses {pattern X} for {purpose}"
- "Integration points identified: {list}"
- "Risk hotspots: {list}"
- "Existing {similar feature} follows {approach}"

**Ask validation questions:**
1. **Pattern Alignment**: "I found that {similar work} uses {pattern/approach}. Should we follow the same pattern?"
2. **Gap Identification**: "I couldn't find examples of {specific aspect}. Should we create something new or adapt {existing approach}?"
3. **Approach Validation**: "Based on research, I'm leaning toward {approach X}. Does this align with your expectations?"
4. **Complexity Confirmation**: "Research suggests this will touch {count} components. Is that the right scope?"

**Example questions:**
- "I found two different patterns for {aspect}: {A} and {B}. Which should we follow?"
- "The research shows that similar features use {technology/pattern}. Should we stick with that?"
- "I discovered {finding} which suggests {implication}. Does this change your priorities?"
- "Research indicates {risk X}. Are you comfortable with that, or should we take a different approach?"

Store Round 1 answers.

### Round 2: Planning Direction Clarification (Conditional)

If research revealed **multiple valid approaches, gaps, or conflicts**, ask **1-3 targeted questions**:

**Question categories:**
1. **Approach Selection**: "I identified {count} options: {A}, {B}, {C}. Which direction should I plan for?"
2. **Risk Trade-offs**: "Option {A} is safer but slower. Option {B} is faster but riskier. Which do you prefer?"
3. **Missing Patterns**: "There's no existing pattern for {aspect}. Should I design a new one or adapt {similar pattern}?"
4. **Scope Refinement**: "Research shows {finding} which could expand scope. Should I include that or defer it?"
5. **Compatibility Decisions**: "Existing code uses {old pattern}. Should the plan migrate everything or maintain compatibility?"

**When to ask Round 2:**
- If research found multiple valid implementation approaches
- If risks or trade-offs need user input
- If scope boundaries are unclear after research
- If backward compatibility decisions are needed

**When to skip Round 2:**
- If research clearly points to one approach
- If pre-research interview already covered these decisions
- If spec or requirements already define the direction

Store Round 2 answers.

### Round 3: Pattern Alignment

Ask **1-3 questions** about following existing patterns:

**Question categories:**
1. **Consistency vs. Innovation**: "I found pattern {X} is used elsewhere. Should we follow it strictly, or is this a good time to improve it?"
2. **Legacy Code**: "The existing code uses {old approach}. Should we maintain consistency or modernize?"
3. **Architectural Decisions**: "I see both {approach A} and {approach B} in the codebase. Which should be the standard going forward?"

Store Round 3 answers.

### Round 4: Risk and Complexity

Ask **1-2 questions** about risk tolerance and complexity:

**Question categories:**
1. **Complexity Budget**: "This could be done simply in {X steps} or more robustly in {Y steps}. What's your preference?"
2. **Risk Assessment**: "Research revealed risk: {X}. Are you comfortable with mitigation: {Y}, or should we take a safer approach?"
3. **Technical Debt**: "We could ship faster with {acceptable debt} or slower with {clean implementation}. Which matters more?"

Store Round 4 answers.

### Round 5: Final Planning Confirmation

Ask **1-2 final questions** to:
- Confirm high-impact architectural decisions based on research
- Validate complexity estimates if significantly different than expected
- Resolve final ambiguities before generating the plan
- Ensure chosen approach aligns with user's vision

Store Round 5 answers.

### Update Interview Document

Append to `.claude/<SESSION_SLUG>/interview/research-plan-interview.md`:

```markdown
---

## Post-Research Interview

### Research Summary Presented
- Similar patterns/features: {list}
- Approaches identified: {list}
- Integration points: {list}
- Risk hotspots: {list}
- Gaps found: {list}

### Round 1: Research Validation

**Q1: {Question}**
A: {User's answer}

**Q2: {Question}**
A: {User's answer}

{...}

### Round 2: Planning Direction Clarification

**Q1: {Question}**
A: {User's answer}

{...}

### Round 3: Pattern Alignment

**Q1: {Question}**
A: {User's answer}

{...}

### Round 4: Risk and Complexity

**Q1: {Question}**
A: {User's answer}

{...}

### Round 5: Final Planning Confirmation

**Q1: {Question}**
A: {User's answer}

{...}

### Key Planning Decisions

- {Decision 1 based on post-research interview}
- {Decision 2 based on post-research interview}
- {Decision 3 based on post-research interview}

### Confirmed Approach

{1-2 sentence summary of the validated approach based on interview answers}
```

**Use these answers** when:
- Applying WORK_TYPE playbook (Step 5)
- Generating implementation approach (Step 6)
- Recommending approach (Step 7)
- Creating implementation steps (Step 8)
- Defining risks and mitigations (Step 12)

## Step 5: Choose and apply WORK_TYPE playbook

Based on WORK_TYPE, follow the appropriate playbook analysis:

### A) ERROR_REPORT playbook
Goal: reproduce → isolate → fix → prevent recurrence

Required analysis:
- **Symptoms**: What fails, where, how often, who impacted
- **Reproduction**: Exact steps OR best-approx reproduction harness
- **Hypotheses**: List 3–7 plausible causes with evidence
- **Root cause**: Pick most likely cause and explain causal chain
- **Fix strategy**:
  - Minimal fix
  - Hardening fix (optional)
  - Prevention (tests, alerts, guardrails)

### B) GREENFIELD_APP playbook
Goal: Ship an MVP safely without overengineering

Required analysis:
- **Product shape**:
  - Primary user journeys (top 3)
  - Core entities/data model
- **Architecture "just enough"**:
  - Choose simplest stack consistent with repo norms
  - Define module boundaries (3–7 modules)
- **Delivery plan**:
  - Milestone 0: Scaffolding + CI + local dev
  - Milestone 1: End-to-end happy path
  - Milestone 2: Harden (auth, validation, error handling, logging)
  - Milestone 3: Polish + docs + load testing (if needed)
- **Operational plan**:
  - Config, secrets, deploy strategy
  - Basic observability from day 1

### C) REFACTOR playbook
Goal: Improve structure without changing behavior (unless explicitly allowed)

Required analysis:
- **Refactor intent**: What pain is being removed (duplication, coupling, complexity)
- **Safety requirements**:
  - Define "behavior lock" tests (golden tests)
  - Define invariants that must not change
- **Sequencing**:
  - Propose stepwise plan that keeps main branch green
  - Identify intermediate states that must compile & pass tests
- **Risk controls**:
  - Feature flags if behavior might drift
  - Strict diff checks (API contracts, query counts, response schema)

### D) NEW_FEATURE playbook
Goal: Implement feature with clear contract, tests, rollout plan

Required analysis:
- **Spec crystallization**:
  - If spec exists from `/spec-crystallize`, USE IT as the authoritative source
  - Reference spec sections 3 (requirements), 4 (contracts), 5 (edge cases), 6 (acceptance criteria)
  - Plan should implement what the spec defines, not redefine it
  - If no spec exists, define behavior, edge cases, error cases in this plan
- **Design options**: Present 2–3 options (simple → robust), pick one with justification
- **Integration plan**: Where it plugs in, what it reuses, what it must not break
- **Rollout**: Feature flag / canary / migration plan, backward compatibility

### E) INCIDENT playbook
Goal: Stop the bleeding, restore service, understand root cause

Required analysis (similar to ERROR_REPORT but with urgency focus):
- **Immediate mitigation**: Fastest path to restore service
- **Temporary fix**: If full fix takes time, what's the short-term solution
- **Root cause**: Quick but thorough analysis
- **Permanent fix**: What needs to change long-term
- **Prevention**: What failed in detection/prevention

## Step 6: Generate options

### Step 6a: Generate implementation approach

Manually generate 1 straightforward implementation approach based on codebase patterns:
- Review findings from codebase-mapper.md
- Identify the simplest approach that aligns with existing patterns
- Document approach: Summary, pros/cons, key dependencies
- Use this for Section 2 "Implementation Approach" of the plan

## Step 7: Recommend one approach

Pick the best option based on:
- RISK_TOLERANCE
- CONSTRAINTS
- Codebase patterns
- Simplicity

Provide clear rationale and explicitly state what you're NOT doing (to avoid overengineering).

## Step 7.5: Analyze dependencies and justify choices

For each major dependency in the chosen approach:
1. **Identify 2-3 alternative libraries/approaches** using web-research.md and codebase-mapper.md findings
2. **Compare alternatives** with decision matrix (pros/cons, performance, security, community)
3. **Justify your choice** with sources from web research
4. **Document security status** (CVEs, advisories) from web-research.md
5. **Check if dependency exists in codebase** (reuse) or is new (justify addition)
6. **Note if "build vs buy"** - could we implement this ourselves simply vs adding a dependency?

For EACH dependency, prepare:
- Comparison table with 2-3 alternatives
- Justification with web sources (articles, benchmarks, docs)
- Security analysis (CVE findings, OWASP guidelines)
- Performance benchmarks (if applicable)
- Case studies (if found in web research)

This analysis will populate the **Technology Choices section** (Section 3) in Step 13.

**Example dependency analysis**:
- Dependency: `express-validator` for input validation
- Alternatives: joi, yup, express-validator
- Chosen: express-validator (already in codebase, integrates with Express middleware, good CVE record)
- Security: No active CVEs, follows OWASP input validation guidelines
- Sources: [npm comparison](URL), [OWASP guide](URL)

## Step 8: Create step-by-step implementation plan

Break down into small, verifiable checkpoints. For each step:
- **Goal**: What this step achieves
- **Files/components to change**: Specific paths
- **Exact edits**: High-level description of changes
- **Tests/checks to run**: How to verify this step
- **"Done when" criteria**: Clear completion criteria

Steps should be:
- Small (~50-200 LOC per step ideally)
- Independently testable
- Revertible if needed

## Step 9: Define comprehensive test plan

Specify tests across all layers:
- **Unit tests**: Which functions/classes need unit tests
- **Integration tests**: Which integrations need testing
- **E2E tests**: Which user journeys need E2E coverage
- **Regression tests**: For bug fixes or refactors
- **Non-functional tests**: Performance, security, load tests if relevant

## Step 10: Define observability & operability

- **Logs**: What to add/change (include redaction notes for PII)
- **Metrics**: What to track (ensure bounded cardinality)
- **Tracing**: What spans to add for distributed tracing
- **Alerts**: Only if justified (avoid alert fatigue)
- **Health checks**: For new services/critical paths

## Step 11: Define rollout & rollback

- **Rollout strategy**: Feature flags, canary, gradual rollout
- **Backward compatibility**: What old clients/services need to keep working
- **Rollback steps**: How to revert if things go wrong
- **Data migration**: If schema/data changes, how to migrate safely

## Step 12: Create risk register

- Spawn the risk-analyzer agent to systematically identify and assess risks:
  ```
  Task: Spawn risk-analyzer agent

  Input parameters:
  - approach: {Chosen design approach from Step 7}
  - implementation_plan: {Step-by-step plan from Step 8}
  - constraints: {CONSTRAINTS from Step 3}
  - risk_tolerance: {RISK_TOLERANCE from Step 3}
  - session_slug: {SESSION_SLUG}
  - integration_points: {From codebase-mapper.md}
  - security_context: {From web-research.md}

  Expected output: `.claude/<SESSION_SLUG>/research/risk-analysis.md`
  ```
- Wait for agent and read results
- Extract top 3-5 highest priority risks with mitigations
- Use for optional "Risk Analysis" section in plan

- Skip risk-analyzer agent
- Manually identify top 3-5 risks based on research findings:
- **Risk description**
- **Likelihood**: low/medium/high
- **Impact**: low/medium/high
- **Mitigation**: How to reduce risk
- **Detection**: How to detect if risk materializes

## Step 13: Generate the research plan document

**IMPORTANT**: Incorporate insights from both interview stages:
- Use pre-research interview answers for planning context, constraints, and success criteria
- Use post-research interview answers for approach selection, risk tolerance, and design decisions
- Reference interview document for key decisions: `.claude/<SESSION_SLUG>/interview/research-plan-interview.md`

Create plan file at: `.claude/<SESSION_SLUG>/plan.md`

If milestone exists from scope-triage, note it in frontmatter:
```yaml
---
milestone: mvp  # or m1, m2, m3, full
---
```


## Step 13.5: Self-review and refine the generated plan

**CRITICAL**: Review the generated plan for errors, edge cases, and overengineering BEFORE finalizing.

### Review Checklist:

1. **Error Detection**:
   - Check for logical errors in implementation steps
   - Verify all file paths and references are correct
   - Validate code examples for syntax errors
   - Ensure step dependencies are in correct order
   - Confirm all acceptance criteria are testable

2. **Edge Case Coverage**:
   - Review edge-cases.md findings
   - Check if plan addresses all critical edge cases from research
   - Verify error handling for boundary conditions
   - Ensure concurrent access scenarios are handled
   - Validate input validation covers edge cases

3. **Overengineering Detection**:
   - Identify unnecessary abstractions or patterns
   - Flag premature optimizations
   - Check for over-complex solutions to simple problems
   - Verify dependencies are justified (not adding libraries for trivial tasks)
   - Ensure YAGNI principle is followed

4. **Missing Critical Elements**:
   - Security considerations from web-research.md and risk-analysis.md
   - Performance implications from research
   - Rollback and error recovery procedures
   - Testing strategy for edge cases
   - Observability for monitoring issues

### If Issues Found:

1. **Research gaps**: Execute targeted follow-up research
   - Re-query web-research if security/best practices unclear
   - Review codebase-mapper if patterns misunderstood
   - Check design-options for alternative approaches

2. **Fix identified issues**:
   - Correct logical errors in steps
   - Add missing edge case handling
   - Simplify overengineered solutions
   - Remove unnecessary dependencies
   - Strengthen security measures

3. **Regenerate affected sections** of plan.md:
   - Update Implementation Steps section
   - Revise Technology Choices if dependencies changed
   - Update Success Criteria & Risks
   - Modify Test Plan if edge cases expanded

4. **Verify improvements**:
   - Re-run review checklist on updated sections
   - Ensure fixes don't introduce new issues
   - Confirm plan is now error-free and comprehensive

**Output**: Refined plan.md with all issues addressed

## Step 14: Update session README

Update `.claude/<SESSION_SLUG>/README.md`:
1. Find the artifacts section
2. Check off `[ ]` → `[x]` for `plan.md`
3. Add to "Recent Activity" section:
   ```markdown
   - {YYYY-MM-DD}: Created research plan via `/research-plan`
   ```

## Step 15: Output summary

Print a summary with key findings and next steps.

# OUTPUT FORMAT


## Core Structure (ALL modes)

```markdown
---
command: /research-plan
session_slug: {SESSION_SLUG}
date: {YYYY-MM-DD}
milestone: {mvp | m1 | m2 | m3 | full}  # if scope-triage exists
research_depth: {none | quick | deep}
work_type: {WORK_TYPE}
scope: {SCOPE}
target: {TARGET}
risk_tolerance: {RISK_TOLERANCE}
related:
  session: ../README.md
  spec: ../spec.md (if exists)
  triage: ../plan/scope-triage.md (if exists)
---

# Research + Plan: {Title}

## 0) Task Overview

**Work Type:** {WORK_TYPE}
**Scope/Target:** {SCOPE} / {TARGET}

**What We're Building:**
- {3-5 bullet summary of what this plan implements}

**Constraints:**
{List or "None"}

**Success Criteria:**
1. {Measurable criterion 1}
2. {Measurable criterion 2}
3. {Measurable criterion 3}

---

## 1) Research Findings

**Manual Research:**
- {Pattern 1 found}: `{file_path}:{line}`
- {Pattern 2 found}: `{file_path}:{line}`

**Similar Features Found:**
- {Feature 1}: {Pattern summary} (`{file_path}:{line}`)
- {Feature 2}: {Pattern summary} (`{file_path}:{line}`)

**Key Patterns to Follow:**
- **Naming**: {Convention with example}
- **Architecture**: {Layer structure}
- **Error Handling**: {Pattern with error codes}

**Relevant Files:**
- `{file_path}` - {Description}
- `{file_path}` - {Description}

[Full codebase analysis: research/codebase-mapper.md](../research/codebase-mapper.md)

**Similar Features Found:**
- {Feature 1}: {Pattern summary} (`{file_path}:{line}`)
- {Feature 2}: {Pattern summary} (`{file_path}:{line}`)

**Key Patterns to Follow:**
- **Naming**: {Convention with example}
- **Architecture**: {Layer structure}
- **Error Handling**: {Pattern with error codes}
- **Integration**: {How features integrate with auth, DB, APIs}

**Industry Recommendations:**
- {Recommendation 1} - Source: [{source}]({URL})
- {Recommendation 2} - Source: [{source}]({URL})

**Security Considerations:**
- {Security finding 1} (OWASP)
- {Security finding 2}

[Full codebase analysis: research/codebase-mapper.md](../research/codebase-mapper.md)
[Full web research: research/web-research.md](../research/web-research.md)

---

## 2) Implementation Approach

**Summary:**
{1-2 paragraphs describing what we're building and how}

**What We're Building:**
- ✅ {Feature 1}
- ✅ {Feature 2}
- ✅ {Feature 3}

**What We're NOT Building:**
- ❌ {Feature A} - {Reason: defer to later / out of scope / unnecessary}
- ❌ {Feature B} - {Reason}

**Options Considered:**
- **Option 1: {Name}** ⭐ RECOMMENDED
  - Pros: {Benefit 1}, {Benefit 2}
  - Cons: {Downside 1}
  - Complexity: {Low/Med/High}, Risk: {Low/Med/High}
- **Option 2: {Name}** - Not chosen because {reason}

[Full design options analysis: research/design-options.md](../research/design-options.md)

---

## 3) Technology Choices & Dependency Justification

**CRITICAL**: Justify EVERY major dependency with research-backed comparison.

### Core Dependencies

#### Dependency 1: {Library Name} v{Version}

**Purpose**: {What problem it solves in 1-2 sentences}

**Alternatives Considered**:

| Library | Pros | Cons | Performance | Security | Community | Decision |
|---------|------|------|-------------|----------|-----------|----------|
| **{Option A}** ⭐ | ✅ {Pro 1}<br>✅ {Pro 2} | ❌ {Con 1} | {Benchmark or N/A} | {CVEs or status} | {GitHub stars, activity} | **CHOSEN** |
| {Option B} | ✅ {Pro 1} | ❌ {Con 1}<br>❌ {Con 2} | {Benchmark} | {CVEs} | {GitHub stars} | Rejected: {Reason} |
| {Option C} | ✅ {Pro 1} | ❌ {Con 1} | {Benchmark} | {CVEs} | {GitHub stars} | Rejected: {Reason} |

**Why {Option A}**:
{2-3 sentence justification backed by research}

**Sources**:
- [Comparison Article]({URL}) - {Date}
- [Benchmark]({URL}) - {Date}
- [Official Docs]({URL})

**Security Considerations**:
- CVEs: {None found / List with mitigations}
- OWASP: {Relevant guideline}
- Security advisories: {Status}

---

#### Dependency 2: {Library Name}
{Repeat structure for each major dependency}

---

### Security Research Summary

**OWASP Guidelines for {Feature Type}**:
1. {Guideline 1} - Source: [{OWASP Resource}]({URL})
2. {Guideline 2} - Source: [{OWASP Resource}]({URL})

**CVE Findings**:
- {Dependency A}: {No CVEs / CVE-XXXX-YYYY (mitigated by X)}
- {Dependency B}: {Status}

**Security Checklist** (from web research):
- [ ] Authentication: {Requirement}
- [ ] Authorization: {Requirement}
- [ ] Input validation: {Requirement}
- [ ] {OWASP-specific items}

---

### Performance Research (if applicable)

**Benchmarks Found**:
- {Library A}: {Throughput}, {Latency p99}
- {Library B}: {Throughput}, {Latency p99}

**Optimization Techniques**:
1. {Technique 1} - Source: [{Article}]({URL})
2. {Technique 2} - Source: [{Article}]({URL})

---

### Case Studies (if found)

**{Company}: {Feature}**
- Approach: {What they did}
- Results: {Metrics}
- Lessons: {Key takeaway}
- Source: [{Article}]({URL})

---

## 4) Implementation Steps

### Step 1: {Title}

**Goal:** {What this achieves}

**Files:**
- `{file_path}` - {Change description}
- `{file_path}` - {Change description}

**Done When:**
- [ ] {Criterion 1}
- [ ] {Criterion 2}
- [ ] Tests pass

### Step 2: {Title}

{Repeat structure for each step}

---

## 5) Success Criteria & Key Risks

**Success Criteria:**
1. ✅ {Measurable criterion 1}
2. ✅ {Measurable criterion 2}
3. ✅ {Measurable criterion 3}

**Top Risks:**
1. **{Risk 1 title}**: {Description}
   - Mitigation: {How to address}
   - Detection: {How to detect}

2. **{Risk 2 title}**: {Description}
   - Mitigation: {How to address}
   - Detection: {How to detect}

3. **{Risk 3 title}**: {Description}
   - Mitigation: {How to address}
   - Detection: {How to detect}

---

{OPTIONAL SECTIONS - Only include when relevant}

## 6) Detailed Test Plan (optional)


**Unit Tests:**
- `{test_file_path}` - {Test scenarios}

**Integration Tests:**
- `{test_file_path}` - {Test scenarios}

**E2E Tests:**
- {Scenario 1}
- {Scenario 2}

**Coverage Target:** {percentage}%

---

## 7) Observability & Rollout (optional)

{Include ONLY if production deployment OR high-risk changes}

**Logs to Add:**
- {Log statement 1} - {Purpose, with PII redaction notes}
- {Log statement 2}

**Metrics to Track:**
- {Metric 1} - {Purpose}
- {Metric 2} - {Purpose}

**Rollout Strategy:**
- Phase 1: {Strategy}
- Phase 2: {Strategy}

**Rollback Steps:**
1. {Step 1}
2. {Step 2}

---

## Next Steps

1. Review this plan
2. Run `/work SESSION_SLUG:{SESSION_SLUG}` to begin implementation
3. Run tests and validation after each step

---

*Session: [{SESSION_SLUG}](../README.md)*
```

## Notes on Simplified Structure

**What Changed:**
- Reduced from 11 sections to 5 core + 2 optional
- Target length: 200-400 lines (vs 800-1000 previously)
- Sections 5-6 are truly optional (only when needed)
- Facts/Assumptions/Unknowns merged into Task Overview and Implementation Approach
- Options Considered moved into Implementation Approach (only shown if deep research)
- Detailed risk register moved to optional section (or simplified in Section 4)
- Test plan simplified or made optional
- Observability/Rollout made optional

**Result:** Plans are focused on immediate task, not exhaustive documentation

# SUMMARY OUTPUT

After creating the plan, print:

```markdown
# Research Plan Complete

## Plan Location
Saved to: `.claude/{SESSION_SLUG}/plan.md`

## Interview Summary
- Pre-research rounds conducted: {3-5}
- Post-research rounds conducted: {3-5}
- Key decisions captured: {count}
- Interview document: `.claude/{SESSION_SLUG}/interview/research-plan-interview.md`

## Research Summary
- Files researched: {count}
- Similar patterns found: {count}
- Components impacted: {list}
- Risk hotspots identified: {count}

## Recommended Approach
{One-sentence summary of chosen option}

## Implementation Overview
- Total steps: {count}
- Estimated complexity: {low/medium/high}
- Key risks: {top 3}

## Next Command to Run

/work
SESSION_SLUG: {SESSION_SLUG}
CHECKPOINT: Starting implementation of {feature/fix title}
```

# IMPORTANT: Interview-Driven Research-First Planning

This command emphasizes **interview + research over guessing**:
1. **Conduct multi-round interviews** before and after research to clarify user intent:
   - Pre-research: Understand planning context, constraints, and success criteria
   - Post-research: Validate findings, select approaches, resolve conflicts
2. **Spend time exploring the codebase** before proposing solutions
3. **Find and reference existing patterns** - don't invent new ones (validate with post-research interview)
4. **Cite evidence** - always include file paths and line numbers
5. **Separate facts from assumptions** - be explicit about unknowns, clarify with interviews
6. **Keep plans executable** - small steps, clear criteria
7. **Think about operations** - observability, rollout, rollback
8. **Store interview results** in `.claude/<SESSION_SLUG>/interview/research-plan-interview.md` for future reference

The plan should feel grounded in the actual codebase AND validated against user expectations, not generic advice.

# EXAMPLE USAGE

**User input:**
```
/research-plan
INPUTS: Need to implement the CSV bulk import feature we spec'd. Users upload CSV, preview data, commit to database with duplicate detection.
```

**Agent:**
1. Infers SESSION_SLUG from last entry in `.claude/README.md`: `csv-bulk-import`
2. Reads session README for context
3. Reads spec from `.claude/csv-bulk-import/spec/spec-crystallize.md`
4. Researches codebase extensively:
   - Finds existing upload patterns
   - Finds CSV parsing utilities
   - Identifies customer model and constraints
   - Maps dependencies and risk hotspots
5. Applies NEW_FEATURE playbook
6. Generates 3 options (sync, async, streaming)
7. Recommends async approach based on risk tolerance
8. Creates detailed step-by-step plan with 8 steps
9. Defines comprehensive test plan
10. Adds observability and rollout strategy
11. Identifies 6 key risks with mitigations
12. Saves plan to `.claude/csv-bulk-import/plan/research-plan.md`
13. Updates session README
14. Outputs summary with next command
