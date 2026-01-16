# Decision Note: Plan Inconsistency - Production Context

**Date:** 2026-01-16
**Status:** BLOCKING - Requires Resolution
**Created By:** /work command pre-flight check

---

## Problem

The research plan contains conflicting information about production status and approach:

**Section 0 (Task Classification) states:**
- "Must maintain backward compatibility for existing clients"
- "No breaking changes without proper deprecation timeline"
- "Must follow industry best practices for API deprecation"
- Success criteria includes "12-18 month deprecation timeline established"
- Success criteria: 30% reduction (28 → ~18-20 endpoints)

**Section 5 (Implementation Plan) states:**
- "**Timeline**: 2-3 weeks"
- "**Approach**: Direct replacement (no gradual migration)"
- "**Context:** NOT in production, can make breaking changes"
- Target: 43% reduction (28 → 16 endpoints)

**Conversation Summary indicates:**
- User confirmed: "we are not in production so we can make changes to the api"
- User wants: "remove the entire monolith api part and centralize on shared microservices api gateway"
- Only 2 clients to update: Firebase Cloud Function + Frontend React app

---

## Context

During the `/research-plan` execution:
1. Initial plan assumed production environment → 12-18 month timeline
2. User provided critical feedback: NOT in production
3. Sections 3-9 of plan were updated to reflect direct replacement approach
4. **Section 0 was NOT fully updated** to match the new approach

This inconsistency creates confusion about:
- What constraints actually apply
- What the success criteria should be
- Whether backward compatibility is required
- What timeline we're working with

---

## Options

### Option 1: Update Section 0 to Match Sections 3-9 (RECOMMENDED)

Update Section 0 (Task Classification) to reflect non-production context:

**Changes:**
- **Inputs**: Add "NOT in production" context
- **Constraints**: Remove backward compatibility requirements, clarify only 2 clients
- **Success Criteria**: Change to 43% reduction (28 → 16), 2-3 week timeline, remove deprecation timeline requirement

**Pros:**
- Aligns entire plan with user's actual context
- Clear, consistent guidance for implementation
- Matches user's explicit statement "we are not in production"

**Cons:**
- Requires plan modification before implementation
- Adds small delay to starting implementation

**Risk:** Low

---

### Option 2: Follow Section 0 (Production Approach)

Implement gradual migration with backward compatibility as stated in Section 0.

**Pros:**
- Follows written plan in Section 0
- Safer if production status was misunderstood

**Cons:**
- **Directly contradicts user's explicit statement**
- Much longer timeline (12-18 months vs 2-3 weeks)
- Unnecessary complexity (strangler pattern, feature flags)
- Less endpoint reduction (30% vs 43%)

**Risk:** High - user explicitly said "not in production"

---

### Option 3: Ask User to Clarify

Stop and ask user which approach they want.

**Pros:**
- Gets explicit confirmation
- No assumptions

**Cons:**
- User already provided explicit confirmation in conversation
- Creates unnecessary friction
- User said "we are not in production" clearly

**Risk:** Low, but inefficient

---

## Recommendation

**Option 1: Update Section 0 to Match Sections 3-9**

**Rationale:**
1. User explicitly confirmed: "we are not in production so we can make changes to the api"
2. User wants: "remove the entire monolith api part" - direct replacement approach
3. Sections 3-9 were already updated based on this feedback
4. Section 0 just wasn't fully updated during the edit session
5. This is clearly a documentation inconsistency, not a change in requirements

**Changes Needed:**
- Update Section 0 "Inputs Summarized" to add "NOT in production" context
- Update Section 0 "Constraints" to remove backward compatibility requirements
- Update Section 0 "Success Criteria" to match 43% reduction, 2-3 weeks, direct replacement

---

## Next Steps

Before proceeding with implementation:

1. **Update Section 0 of research-plan.md** to align with Sections 3-9
2. Verify plan is now consistent throughout
3. Proceed with PHASE 0 (Pre-Flight) using consistent plan
4. Begin implementation of Step 1 (Design API Structure)

---

## Impact

**If we proceed with inconsistent plan:**
- Risk of implementing wrong approach (12-18 month vs 2-3 week)
- Wasted effort on backward compatibility that's not needed
- Confusion during implementation

**If we fix inconsistency first:**
- 10-15 minutes to update Section 0
- Clear, consistent guidance for all implementation phases
- No ambiguity about constraints or success criteria

**Decision:** Fix inconsistency first (Option 1)

---

*Decision created during /work pre-flight check*
*Requires: Plan update before implementation*
