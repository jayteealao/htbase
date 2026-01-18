# Comprehensive Codebase Health Check

**Status:** Active
**Session:** codebase-review
**Date:** 2026-01-17
**Work Type:** refactor
**Scope:** repo
**Target:** .
**Risk Tolerance:** medium

## Context

- General health check across architecture, maintainability, security, and performance
- Following Wave 1-5 refactoring work (app directory removal, Firestore migration, PostgreSQL removal)
- Assess current state and identify next improvement opportunities

## Constraints

None specified

## Non-Goals

None specified

## Success Criteria

- Complete architecture review of codebase structure
- Identify maintainability issues and technical debt
- Document security concerns if any
- Assess performance patterns and potential optimizations
- Prioritized list of improvement opportunities
- Actionable recommendations for next steps

## Default Review Chain

- /review:architecture
- /review:maintainability
- /review:security
- /review:overengineering
- /review:performance

## Next Commands to Run

1. `/research-plan` - Create research plan to systematically explore the codebase
2. `/review:architecture` - Review overall architecture and structure
3. `/review:maintainability` - Assess code quality and maintainability
4. `/review:security` - Identify security concerns
5. `/review:overengineering` - Find unnecessary complexity
6. `/review:performance` - Assess performance patterns

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

*Session created: 2026-01-17*
