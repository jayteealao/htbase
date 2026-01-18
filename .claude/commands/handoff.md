---
name: handoff
description: Create crisp handoff documentation for reviewers, oncall, or deployment teams
usage: /handoff [SCOPE] [TARGET] [AUDIENCE] [CONTEXT]
arguments:
  - name: SCOPE
    description: 'Review scope: pr (default) | worktree | diff | repo'
    required: false
    default: pr
  - name: TARGET
    description: 'Target specifier: PR number, branch name, commit hash, or repo root'
    required: false
  - name: AUDIENCE
    description: 'Target audience: reviewers | oncall | cross-functional | leadership'
    required: false
    default: reviewers
  - name: CONTEXT
    description: 'What is changing and why, related artifacts (plans, reviews, runbooks), rollout strategy'
    required: false
examples:
  - command: /handoff pr 123 reviewers
    description: Create handoff note for code reviewers
  - command: /handoff pr 456 oncall "CONTEXT: Payment processor migration, canary rollout, runbook at docs/runbooks/payment-failover.md"
    description: Create handoff note for oncall team with deployment context
  - command: /handoff worktree cross-functional "CONTEXT: New checkout flow, LaunchDarkly flag checkout_v2, dashboard at grafana.com/dashboards/checkout"
    description: Create handoff for cross-functional team with monitoring links
---

# Handoff Documentation

You produce crisp handoff documentation that lets someone else review, deploy, or support the change without reading your mind.

## Core Principles

### Be Concise, Not Vague
**❌ BAD**: "Made some changes to the API"
**✅ GOOD**: "Added rate limiting (100 req/min per user) to `/api/checkout` endpoint"

### Prefer Concrete Pointers
**❌ BAD**: "Check the logs for errors"
**✅ GOOD**: "Check CloudWatch Logs group `/aws/lambda/checkout-api` filtered by `error.code=payment_declined`"

### Surface Operational Implications
**❌ BAD**: "Database schema changed"
**✅ GOOD**: "Database migration adds index (5min, backward compatible). Deploy order: DB migration → app deployment → backfill (optional)"

### If Unknown, Say So
**❌ BAD**: "Should work fine"
**✅ GOOD**: "Rollback difficulty: UNKNOWN. Recommendation: Deploy to staging first and test rollback procedure before production."

## Step 0: Infer SESSION_SLUG if Needed

If `SESSION_SLUG` is not provided:
1. Read `.claude/README.md`
2. Extract the **last session** from the table (most recent entry)
3. Use that session's slug as `SESSION_SLUG`

## Step 1: Determine Scope and Audience

Based on `SCOPE` and `AUDIENCE` parameters:

**Scope:**
- **`pr`** (default): Handoff for specific pull request
- **`worktree`**: Handoff for uncommitted changes
- **`diff`**: Handoff for diff between branches
- **`repo`**: Handoff for entire repository state

**Audience:**
- **`reviewers`**: Focus on code review guidance (where to start, what to be strict about)
- **`oncall`**: Focus on operational concerns (runbooks, rollback, monitoring)
- **`cross-functional`**: Focus on business context (what/why, user impact, timelines)
- **`leadership`**: Focus on high-level summary (objectives, risks, timelines)

## Step 2: Gather Context

Extract from `CONTEXT` parameter or analyze codebase:

1. **Change summary**: What is changing and why
2. **Related artifacts**:
   - Research plan (`/research-plan` output)
   - Review findings (`/review:*` outputs)
   - Runbooks (paths or links)
   - Dashboards (Grafana/Datadog links)
   - Feature flags (LaunchDarkly/Split/custom)
3. **Rollout strategy**: None, canary, phased, manual
4. **Rollback plan**: Easy, moderate, hard, unknown
5. **Known risks**: List of concerns
6. **Verification steps**: Commands/checks to validate

## Step 3: Create Handoff Note

Structure the handoff note based on audience:

### For Reviewers

Focus on:
- Where to start reading (entry points, key files)
- Highest-risk areas (security, performance, data integrity)
- Suggested review order
- Things to be strict about (error handling, edge cases, tests)
- How to test locally

### For Oncall

Focus on:
- Deployment steps and timing
- Monitoring and alerting
- Runbook updates
- Rollback procedures
- Known failure modes
- Support escalation

### For Cross-Functional

Focus on:
- Business objectives
- User impact (features, behavior changes)
- Timeline and milestones
- Dependencies on other teams
- Success metrics

### For Leadership

Focus on:
- Strategic objectives
- Business impact (revenue, users, market)
- Resource requirements
- Timeline and key dates
- Risk summary with mitigation

## Step 4: Handoff Note Template

```markdown
# Handoff Note

## 0) What This Is

**Change summary:**
- [Bullet 1: Main change]
- [Bullet 2: Secondary change]
- [Bullet 3: Related changes]

**Why now:**
[Business context, timeline driver, incident response]

**Non-goals:**
- [What this does NOT change]
- [Deferred work]

## 1) What Changed (High-Signal)

**Key behavior changes:**
- [User-visible changes]
- [API changes]
- [Performance changes]

**Key non-behavior changes:**
- [Refactorings]
- [Code cleanup]
- [Dependency updates]

**Public surfaces touched:**
- APIs: [List endpoints]
- UI: [List components/pages]
- Events: [List event types]
- Config: [List config fields]

## 2) How to Review (for reviewers)

**Where to start:**
1. [Entry point file/module]
2. [Core logic file/module]
3. [Tests]

**Highest-risk areas:**
- [File/module with risk description]
- [File/module with risk description]

**Suggested review order:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Things to be strict about:**
- [Error handling in X]
- [Edge cases in Y]
- [Performance in Z]

## 3) How to Test/Verify (for anyone)

**Local commands:**
```bash
# Setup
[Commands to set up local environment]

# Run tests
[Commands to run tests]

# Manual testing
[Commands for manual verification]
```

**CI checks:**
- [List required CI checks]

**Manual QA script:**
1. [Step 1]
2. [Step 2]
3. [Expected result]

**Expected outputs:**
```
[Example output or screenshot description]
```

## 4) How to Deploy/Rollout

**Rollout approach:**
[All-at-once | Canary | Phased | Manual]

**Feature flags:**
| Flag Name | Default | How to Toggle |
|-----------|---------|---------------|
| [name] | [on/off] | [LaunchDarkly UI / config file / API call] |

**Migrations/backfills:**
```bash
# Migration command
[Command]

# Expected duration
[Time estimate]

# Rollback
[Rollback command]
```

**Monitoring plan:**
- **Dashboard**: [Link to Grafana/Datadog dashboard]
- **Key metrics**: [List metrics to watch]
- **Alerts**: [List alert conditions]
- **Log queries**: [CloudWatch/Datadog queries]

## 5) Rollback Plan

**Rollback steps:**
```bash
# Step 1: Disable feature flag (if applicable)
[Command]

# Step 2: Revert deployment
[Command]

# Step 3: Verify rollback
[Command]
```

**Rollback difficulty:** [EASY | MODERATE | HARD | UNKNOWN]

**Data considerations:**
- [One-way data migrations?]
- [State that can't be rolled back?]

**Stop conditions:**
- [Error rate > 1%]
- [Latency p95 > 2s]
- [Customer complaints spike]

## 6) Known Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk description] | [L/M/H] | [L/M/H] | [Mitigation strategy] |

## 7) Links / References

- **PR**: [GitHub/GitLab link]
- **Plan**: [Research plan link or summary]
- **Runbooks**: [List of runbook links]
- **Dashboards**: [List of dashboard links]
- **Tickets**: [JIRA/Linear links]
- **Related PRs**: [Links to dependent PRs]
```

## Step 5: Tailor by Audience

### Reviewers Template

```markdown
# Code Review Handoff: [Feature/Fix Name]

## Quick Context
**What**: [1-sentence summary]
**Why**: [1-sentence business context]
**Risk level**: [LOW | MEDIUM | HIGH]

## Where to Start
1. **Entry point**: `[file.ts:line]` - [What this does]
2. **Core logic**: `[file.ts:line]` - [What this does]
3. **Tests**: `[test-file.ts]` - [Coverage notes]

## Review Checklist

### Critical Areas (Be Strict)
- [ ] **Error handling** in `[file.ts]` - Ensure all edge cases covered
- [ ] **Input validation** in `[file.ts]` - Check for injection vulnerabilities
- [ ] **Performance** in `[file.ts]` - Look for N+1 queries, unbounded loops
- [ ] **Tests** - Verify coverage for new code paths

### Medium Priority
- [ ] **Code style** - Consistent with existing patterns
- [ ] **Naming** - Clear, self-documenting
- [ ] **Comments** - Complex logic explained

### Nice to Have
- [ ] **Performance optimizations** - Opportunities for improvement
- [ ] **Refactoring** - Code cleanup suggestions

## How to Test Locally

```bash
# 1. Setup
npm install
docker-compose up -d

# 2. Run tests
npm test

# 3. Manual verification
curl http://localhost:3000/api/[endpoint] \
  -H "Authorization: Bearer test-token" \
  -d '{"key": "value"}'

# Expected output:
# {"status": "success", "data": {...}}
```

## Risk Areas

### Security
- [Specific concerns]

### Performance
- [Specific concerns]

### Data Integrity
- [Specific concerns]

## Questions for Author
- [ ] [Question 1]
- [ ] [Question 2]
```

### Oncall Template

```markdown
# Oncall Handoff: [Feature/Fix Name]

## What's Deploying
- **Feature**: [Name]
- **Impact**: [Who/what is affected]
- **Timeline**: Deploying [date/time]
- **Duration**: [Expected deployment window]

## Deployment Plan

### Phase 1: Canary (10%)
**Time**: [Start time]
**Duration**: 30 minutes
**Success criteria**:
- Error rate < 0.1%
- P95 latency < 200ms
- No customer complaints

**Commands**:
```bash
# Deploy canary
kubectl apply -f k8s/deployment-canary.yaml

# Monitor
watch kubectl get pods -l app=checkout,track=canary
```

### Phase 2: 50%
**Time**: [+30 min]
**Duration**: 1 hour
**Success criteria**: Same as Phase 1

### Phase 3: 100%
**Time**: [+90 min]
**Success criteria**: Same as Phase 1 + 24h stability

## Monitoring

**Primary dashboard**: https://grafana.company.com/d/checkout

**Key metrics to watch**:
```
# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# Latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Payment success rate
sum(rate(payment_success_total[5m])) / sum(rate(payment_attempts_total[5m]))
```

**Alerts**:
- `checkout-error-rate-high` - Page oncall
- `checkout-latency-high` - Slack #alerts
- `payment-failure-spike` - Page oncall

**Log queries** (CloudWatch):
```
fields @timestamp, request_id, error.code, user.subscription
| filter path = "/api/checkout" and outcome = "error"
| sort @timestamp desc
| limit 100
```

## Rollback Procedure

**Trigger conditions**:
- Error rate > 1% for 5 minutes
- P95 latency > 2s for 10 minutes
- Payment success rate < 95%
- 5+ customer complaints in #support

**Rollback steps** (< 5 minutes):
```bash
# 1. Disable feature flag
curl -X POST https://api.launchdarkly.com/flags/checkout_v2 \
  -H "Authorization: api-key-xxx" \
  -d '{"on": false}'

# 2. Verify flag disabled
curl https://api.launchdarkly.com/flags/checkout_v2

# 3. Revert deployment (if flag doesn't work)
kubectl rollout undo deployment/checkout-api

# 4. Verify rollback
kubectl rollout status deployment/checkout-api

# 5. Check metrics (should return to baseline in 2-3 minutes)
```

**Data considerations**:
- No database migrations (rollback is clean)
- In-flight requests will complete with old code after rollback

## Runbook Updates

**New runbook**: `docs/runbooks/checkout-v2-issues.md`

**Common issues**:

### Issue 1: Payment provider timeout
**Symptoms**: Error code `payment_timeout`, P95 latency > 5s
**Diagnosis**: Check Stripe API status at https://status.stripe.com
**Fix**: If Stripe is down, wait for recovery. If our side, increase timeout:
```bash
kubectl set env deployment/checkout-api PAYMENT_TIMEOUT_MS=10000
```

### Issue 2: Rate limit exceeded
**Symptoms**: Error code `rate_limit_exceeded`, 429 responses
**Diagnosis**: Check rate limit metrics in Datadog
**Fix**: Increase rate limit or scale horizontally:
```bash
kubectl scale deployment/checkout-api --replicas=10
```

## Escalation

**Primary oncall**: @oncall-engineer (Slack, PagerDuty)
**Backup oncall**: @backup-oncall
**Subject matter expert**: @feature-author
**Manager**: @engineering-manager

**Escalation path**:
1. Primary oncall (immediate)
2. Backup oncall (if primary doesn't respond in 10 min)
3. SME + manager (if issue persists > 30 min)

## Support Talking Points

**If customers ask about checkout issues**:
- "We're deploying an improved checkout experience. Some users may see brief errors during rollout."
- **ETA for fix**: Within 5 minutes (rollback time)
- **Customer impact**: Payment processing may fail temporarily
- **Workaround**: Retry in 5 minutes

**If payment failures spike**:
- "We're investigating payment processing issues. Rolling back now."
- **ETA for resolution**: 5 minutes
- **Customer action**: No action needed, issue will auto-resolve
```

### Cross-Functional Template

```markdown
# Cross-Functional Handoff: [Feature Name]

## Executive Summary

**What we're shipping**: [1-sentence description]
**Why it matters**: [Business impact]
**Who it affects**: [User segments]
**When**: [Timeline]

## Business Objectives

### Primary Goal
[Increase conversion by X% | Reduce churn by Y% | Launch in new market]

### Success Metrics
| Metric | Baseline | Target | Timeline |
|--------|----------|--------|----------|
| [Metric 1] | [Current] | [Goal] | [Date] |
| [Metric 2] | [Current] | [Goal] | [Date] |

### Key Results
- **Week 1**: [KR1]
- **Week 4**: [KR2]
- **Week 12**: [KR3]

## User Impact

### What Users Will See
**Before**:
[Description or screenshot]

**After**:
[Description or screenshot]

### Affected User Segments
- **Premium users** (10,000 users): [Impact description]
- **Free users** (100,000 users): [Impact description]
- **Enterprise customers** (50 companies): [Impact description]

### Behavior Changes
1. [Change 1: Old behavior → New behavior]
2. [Change 2: Old behavior → New behavior]

## Timeline & Milestones

| Date | Milestone | Owner | Status |
|------|-----------|-------|--------|
| [Date] | Engineering complete | @eng-lead | ✅ |
| [Date] | Design review | @design-lead | ✅ |
| [Date] | Deploy to staging | @oncall | 🔄 |
| [Date] | QA sign-off | @qa-lead | ⏳ |
| [Date] | Deploy to production | @oncall | ⏳ |
| [Date] | Full rollout | @product-lead | ⏳ |

## Dependencies

### Upstream (Blocking Us)
- [ ] **Marketing**: Landing page updates by [date]
- [ ] **Support**: Training completed by [date]
- [ ] **Legal**: Terms updated by [date]

### Downstream (We're Blocking)
- [ ] **Analytics**: New events need integration ([owner])
- [ ] **Mobile**: API changes need mobile SDK update ([owner])

## Rollout Strategy

**Phase 1: Internal (Week 1)**
- 100% of @company.com emails
- Goal: Validate functionality

**Phase 2: Beta (Week 2)**
- 10% of premium users (opted in)
- Goal: Gather feedback

**Phase 3: General Availability (Week 3-4)**
- 10% → 25% → 50% → 100% over 2 weeks
- Goal: Safe, monitored rollout

**Feature flag**: `checkout_v2` (LaunchDarkly)

## Risk Summary

| Risk | Likelihood | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| Payment provider downtime | Low | High | Circuit breaker, fallback | @eng |
| User confusion | Medium | Medium | In-app guide, support docs | @product |
| Mobile SDK compatibility | Low | High | Versioning, deprecation notice | @mobile |

## Communication Plan

### Internal
- **Announcement**: #general channel [date]
- **Demo**: All-hands [date]
- **Training**: Support team [date]

### External
- **Blog post**: [date] by @marketing
- **Email campaign**: [date] to premium users
- **In-app notification**: [date] all users

### Support Prep
- **FAQ**: docs/support/checkout-v2-faq.md
- **Common issues**: docs/support/checkout-v2-troubleshooting.md
- **Escalation**: Tag @engineering-oncall in #support

## Open Questions
- [ ] [Question 1] - Owner: [name] - Due: [date]
- [ ] [Question 2] - Owner: [name] - Due: [date]
```

### Leadership Template

```markdown
# Leadership Handoff: [Initiative Name]

## Strategic Context

**Objective**: [High-level business goal]
**Rationale**: [Why this matters now]
**Alignment**: [How this supports company OKRs]

## Business Impact

### Revenue Impact
- **Projected increase**: [X% or $Y]
- **Timeline to realization**: [Timeframe]
- **Confidence level**: [High/Medium/Low]

### User Impact
- **Affected users**: [Number and segments]
- **Expected experience improvement**: [Qualitative + quantitative]
- **Adoption timeline**: [Rollout schedule]

### Market Impact
- **Competitive positioning**: [How this affects market position]
- **Market opportunity**: [TAM/SAM/SOM]

## Resource Requirements

### Engineering
- **Team**: [Team name]
- **Effort**: [Person-weeks]
- **Timeline**: [Start - End dates]
- **Key personnel**: [Critical resources]

### Cross-Functional
- **Design**: [Effort and timeline]
- **Product**: [Effort and timeline]
- **Marketing**: [Effort and timeline]
- **Sales**: [Effort and timeline]

### Budget
- **Infrastructure**: [$X/month]
- **Third-party services**: [$Y/month]
- **One-time costs**: [$Z]

## Timeline

| Phase | Milestone | Date | Status |
|-------|-----------|------|--------|
| Planning | Requirements finalized | [Date] | ✅ |
| Development | Engineering complete | [Date] | 🔄 |
| Testing | QA sign-off | [Date] | ⏳ |
| Launch | Beta release | [Date] | ⏳ |
| Launch | General availability | [Date] | ⏳ |
| Post-launch | Success metrics validated | [Date] | ⏳ |

## Risk Summary

### Technical Risks
- [Risk 1]: [Mitigation]
- [Risk 2]: [Mitigation]

### Business Risks
- [Risk 1]: [Mitigation]
- [Risk 2]: [Mitigation]

### Mitigation Strategy
[Overall risk management approach]

## Success Criteria

### Short-term (1 month)
- [ ] [Metric 1] reaches [target]
- [ ] [Metric 2] reaches [target]
- [ ] [Qualitative goal]

### Long-term (6 months)
- [ ] [Strategic goal 1]
- [ ] [Strategic goal 2]

## Decision Points

**Go/No-Go**: [Date]
**Criteria**:
- [ ] [Criterion 1]
- [ ] [Criterion 2]

**If No-Go**:
[Alternative plan]

## Communication

- **Board update**: [Date]
- **All-hands**: [Date]
- **Customer communication**: [Date and channel]
```

## Example Handoff Notes

### Example 1: Payment Processor Migration (Reviewers)

```markdown
# Code Review Handoff: Stripe → Braintree Migration

## Quick Context
**What**: Migrate from Stripe to Braintree for payment processing
**Why**: Reduce transaction fees from 2.9% to 2.4% (saves $200k/year)
**Risk level**: HIGH (touches money)

## Where to Start
1. **Entry point**: `src/services/PaymentService.ts:45` - Main payment orchestration
2. **Core logic**: `src/adapters/BraintreeAdapter.ts:1` - Braintree integration
3. **Tests**: `src/services/PaymentService.test.ts` - 95% coverage

## Review Checklist

### Critical Areas (Be Strict)
- [ ] **Error handling** in `BraintreeAdapter.ts` - Ensure retry logic matches Stripe behavior
- [ ] **Idempotency** in `PaymentService.ts` - Check idempotency key implementation
- [ ] **Webhook handling** in `src/webhooks/braintree.ts` - Verify signature validation
- [ ] **Amount handling** - Braintree uses cents, ensure no currency conversion bugs
- [ ] **Tests** - Verify all Stripe error scenarios covered for Braintree

### Medium Priority
- [ ] **Code style** - Consistent with existing payment adapters
- [ ] **Logging** - Ensure wide events capture provider-specific fields
- [ ] **Monitoring** - Metrics tagged with provider=braintree

### Nice to Have
- [ ] **Performance** - Braintree client reuse (connection pooling)
- [ ] **Refactoring** - Extract common adapter interface

## How to Test Locally

```bash
# 1. Setup
npm install
docker-compose up -d postgres redis

# 2. Configure Braintree sandbox
cp .env.example .env
# Add BRAINTREE_MERCHANT_ID, BRAINTREE_PUBLIC_KEY, BRAINTREE_PRIVATE_KEY from sandbox

# 3. Run tests
npm test

# 4. Manual verification
curl http://localhost:3000/api/payments \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 1000,
    "currency": "USD",
    "payment_method": "nonce-from-braintree-drop-in"
  }'

# Expected output:
# {
#   "id": "payment_abc123",
#   "status": "succeeded",
#   "provider": "braintree",
#   "amount": 1000,
#   "currency": "USD"
# }

# 5. Test error scenarios
curl http://localhost:3000/api/payments \
  -H "Authorization: Bearer test-token" \
  -d '{"amount": 1000, "payment_method": "fake-nonce-declined"}'

# Expected: 402 Payment Required with error.code=payment_declined
```

## Risk Areas

### Security
- **PCI compliance**: Braintree handles card data (same as Stripe)
- **Webhook signatures**: CRITICAL - Verify signature before processing
- **API keys**: Stored in AWS Secrets Manager (not in code)

### Performance
- **Latency**: Braintree p95 is 250ms vs Stripe 150ms (acceptable)
- **Timeouts**: Set to 10s (Braintree recommends 10-15s)

### Data Integrity
- **Idempotency**: Braintree uses different key format (max 36 chars)
- **Charge reconciliation**: Need to match Braintree transaction IDs to our payment IDs

## Questions for Author
- [ ] What happens to in-flight Stripe charges during migration?
- [ ] Is there a rollback window before we lose Stripe data?
- [ ] How do we handle webhooks from both providers during migration?
```

### Example 2: Feature Flag Rollout (Oncall)

```markdown
# Oncall Handoff: New Checkout Flow (checkout_v2)

## What's Deploying
- **Feature**: Redesigned checkout with one-click payment
- **Impact**: All users (mobile + web)
- **Timeline**: Rolling out over 5 days starting [date]
- **Duration**: Continuous deployment, rollout controlled by feature flag

## Deployment Plan

### Day 1: Internal Testing
**Flag**: `checkout_v2` = ON for @company.com emails
**Success criteria**:
- 0 errors from internal users
- Feedback collected in #checkout-beta

**Commands**:
```bash
# Enable for internal users
curl -X PATCH https://api.launchdarkly.com/api/v2/flags/checkout_v2 \
  -H "Authorization: api-key-xxx" \
  -d '{
    "rules": [{
      "clauses": [{
        "attribute": "email",
        "op": "endsWith",
        "values": ["@company.com"]
      }],
      "variation": 0
    }]
  }'
```

### Day 2-3: Beta Users (10%)
**Flag**: `checkout_v2` = ON for 10% of users
**Success criteria**:
- Error rate < 0.5%
- Conversion rate >= baseline (2.3%)
- P95 latency < 1.5s

### Day 4: Ramp to 50%
**Success criteria**: Same as Day 2-3

### Day 5: Full Rollout (100%)
**Success criteria**: Same + 24h stability

## Monitoring

**Primary dashboard**: https://grafana.company.com/d/checkout-v2

**Key metrics**:
```
# Conversion rate by variant
sum(rate(checkout_completed_total{variant="v2"}[1h])) / sum(rate(checkout_started_total{variant="v2"}[1h]))

# Error rate by variant
sum(rate(checkout_errors_total{variant="v2"}[5m])) / sum(rate(checkout_attempts_total{variant="v2"}[5m]))

# Latency by variant
histogram_quantile(0.95, rate(checkout_duration_seconds_bucket{variant="v2"}[5m]))
```

**Alerts**:
- `checkout-v2-error-rate-high` - Page oncall if > 1%
- `checkout-v2-conversion-drop` - Slack #alerts if < 2.0%
- `checkout-v2-latency-high` - Slack #alerts if p95 > 2s

**Log queries** (Datadog):
```
path:/api/checkout feature_flags.checkout_v2:true outcome:error
| group by error.code
| count
```

## Rollback Procedure

**Trigger conditions**:
- Error rate > 1% for 10 minutes
- Conversion rate < 2.0% for 30 minutes
- P95 latency > 2s for 15 minutes

**Rollback steps** (< 2 minutes):
```bash
# 1. Disable feature flag (instant)
curl -X PATCH https://api.launchdarkly.com/api/v2/flags/checkout_v2 \
  -H "Authorization: api-key-xxx" \
  -d '{"on": false}'

# 2. Verify all users see old checkout
curl https://api.launchdarkly.com/api/v2/flags/checkout_v2/evaluation \
  -H "Authorization: api-key-xxx"

# 3. Monitor rollback (metrics should recover in 1-2 minutes)
# Check dashboard: https://grafana.company.com/d/checkout-v2
```

**Data considerations**:
- No database changes (pure frontend)
- In-progress checkouts will complete with version they started with
- No data loss on rollback

## Runbook

### Common Issue 1: One-click payment fails with "payment_method_invalid"

**Symptoms**: Error code `payment_method_invalid`, user reports "payment failed"

**Diagnosis**:
```bash
# Check user's payment methods
curl https://api.company.com/internal/users/{user_id}/payment-methods \
  -H "Authorization: internal-api-key"

# Check Stripe status
curl https://status.stripe.com/api/v2/status.json
```

**Fix**:
1. If payment method expired, ask user to re-add
2. If Stripe issue, wait or rollback
3. If our bug, disable one-click (fallback to regular flow)

### Common Issue 2: Checkout stuck on loading

**Symptoms**: User reports "checkout won't load"

**Diagnosis**:
```bash
# Check frontend errors
# Datadog: path:/checkout status:error
```

**Fix**:
1. Check if CDN issue (Cloudflare status)
2. Check if API overloaded (high latency)
3. If persistent, rollback feature flag

## Escalation

**Primary oncall**: @oncall-engineer
**Feature owner**: @product-engineer
**Product manager**: @pm
**Engineering manager**: @eng-manager

**Escalation path**:
1. Try rollback first (you have authority)
2. If rollback doesn't work, page @product-engineer
3. If user-facing issue, notify @pm in #product-alerts
4. If incident > 30min, notify @eng-manager

## Support Talking Points

**If users report checkout issues**:
- "We're testing a new checkout experience. If you encounter issues, please refresh and try again."
- **Workaround**: Clear browser cache and retry
- **ETA**: Issues resolve immediately on rollback (2 minutes)

**If conversion drops significantly**:
- Internal action: Rollback immediately
- External: No customer communication needed (silent rollback)
```

## Step 6: Output Handoff Note

Create handoff note at `.claude/<SESSION_SLUG>/handoffs/handoff_<timestamp>.md`

## Example Output Structure

```markdown
# Handoff Note: [Feature/Change Name]

**Generated**: 2024-01-15 14:30 UTC
**Author**: @engineer-name
**Audience**: [Reviewers | Oncall | Cross-functional | Leadership]
**Session**: <SESSION_SLUG>

[Include appropriate template based on audience]

---

**Verification**:
- [ ] All links work
- [ ] All commands tested
- [ ] Metrics queries validated
- [ ] Runbook updated
- [ ] Team notified in [#channel]
```

## Handoff Quality Checklist

Before finalizing handoff:

- [ ] **Concise but complete**: No unnecessary details, but all critical info present
- [ ] **Concrete pointers**: File paths, endpoints, dashboard links (not vague references)
- [ ] **Operational clarity**: Deployment steps, monitoring, rollback explicit
- [ ] **Risk transparency**: Known risks stated with mitigations
- [ ] **Verification steps**: Clear commands to validate success
- [ ] **Links work**: All referenced dashboards, runbooks, tickets accessible
- [ ] **Audience-appropriate**: Level of detail matches audience needs
- [ ] **Unknown items flagged**: If something is uncertain, explicitly say so with "UNKNOWN" tag

## Common Handoff Anti-Patterns

### ❌ Anti-Pattern 1: Vague Descriptions

**Bad**:
> Made some improvements to the API

**Good**:
> Added rate limiting (100 req/min per user) to `/api/checkout` using Redis. Exceeding limit returns 429 with `Retry-After` header.

### ❌ Anti-Pattern 2: Missing Verification

**Bad**:
> Deploy and it should work

**Good**:
> Deploy and verify:
> ```bash
> curl https://api.prod.company.com/health
> # Expected: {"status": "ok", "version": "2.1.0"}
> ```

### ❌ Anti-Pattern 3: Unclear Rollback

**Bad**:
> Can rollback if needed

**Good**:
> Rollback (< 5 min):
> ```bash
> kubectl rollout undo deployment/api
> kubectl rollout status deployment/api
> # Verify: curl https://api.prod.company.com/health | jq .version
> # Expected: "2.0.9" (previous version)
> ```

### ❌ Anti-Pattern 4: No Monitoring Plan

**Bad**:
> Check logs for errors

**Good**:
> Monitor these metrics for 24h:
> - Error rate: https://grafana.com/d/api-errors (should be < 0.1%)
> - Latency: https://grafana.com/d/api-latency (p95 should be < 200ms)
> - Alert if: error rate > 1% for 5 minutes

### ❌ Anti-Pattern 5: Assuming Context

**Bad**:
> Use the usual deployment process

**Good**:
> Deployment process:
> 1. Merge PR to `main`
> 2. Wait for CI (10 min)
> 3. Auto-deploys to staging
> 4. Run smoke tests: `npm run test:staging`
> 5. Promote to prod: `./scripts/deploy-prod.sh`
> 6. Monitor dashboard: [link]

## Summary

A good handoff note:
- **Saves time**: Reviewer/oncall/stakeholder can act immediately without asking questions
- **Reduces risk**: Explicit rollback procedures and monitoring prevent incidents
- **Builds trust**: Transparent about risks and unknowns shows maturity
- **Scales knowledge**: Documents process for future team members

Remember: **You won't be there to explain it. The note must stand alone.**
