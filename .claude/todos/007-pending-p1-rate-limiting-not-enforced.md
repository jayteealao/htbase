---
status: pending
priority: p1
issue_id: "007"
tags: [code-review, security, rate-limiting, api-gateway, agent-native]
dependencies: [002]
---

# Rate Limiting Configured But Not Enforced

Rate limit configuration exists in environment variables but is not implemented in API Gateway, leaving system vulnerable to abuse.

## Problem Statement

The `.env.microservices.example` file defines `API_RATE_LIMIT=100/minute` and the REARCHITECTURE_PLAN.md documents Celery task rate limits, but the API Gateway has no rate limiting middleware. Without enforcement, the API is vulnerable to:
- Resource exhaustion attacks
- Cloud cost explosions (expensive Chromium workers)
- Service degradation for legitimate users
- LLM API quota exhaustion

**Impact:**
- Malicious actors can submit unlimited archive tasks
- Single client can monopolize all workers
- $10,000+ monthly cloud bills from abuse
- Service becomes unusable for real users

## Findings

- **Location:** `services/api-gateway/app/main.py` - No rate limiting middleware
- **Configuration exists but unused:**
  ```bash
  # .env.microservices.example:34
  API_RATE_LIMIT=100/minute
  ```
- **Celery task limits documented but don't protect API:**
  ```python
  # REARCHITECTURE_PLAN.md mentions task-level limits
  task_annotations={
      'archive_worker.tasks.archive_url': {'rate_limit': '10/m'},
  }
  ```
- **Agent-Native Review:** Rated 3/10 - "Configured but not enforced"
- **No rate limit headers** in API responses
- **No slowapi or similar library** imported

## Proposed Solutions

### Option 1: SlowAPI with Per-IP Rate Limiting (Quick Fix)

**Approach:** Add slowapi middleware with IP-based rate limiting.

**Pros:**
- Quick to implement (1-2 hours)
- Works immediately without database
- Standard rate limit headers
- Per-route configuration

**Cons:**
- IP-based limits can be bypassed with proxies
- No per-API-key limits
- Memory-based (doesn't scale across replicas)

**Effort:** 2-3 hours

**Risk:** Low

**Implementation:**
```python
# services/api-gateway/app/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to routes
from slowapi import Limiter
@router.post("/save")
@limiter.limit("10/minute")  # Per IP
async def save_url(...):
    pass

@router.get("/tasks/{task_id}")
@limiter.limit("1000/hour")  # Status checks less restrictive
async def get_task_status(...):
    pass
```

---

### Option 2: Redis-Based Per-API-Key Rate Limiting (Recommended)

**Approach:** Use Redis for distributed rate limiting per API key.

**Pros:**
- Scales across multiple API Gateway replicas
- Per-API-key limits (more accurate)
- Persistent across restarts
- Can implement different tiers

**Cons:**
- Requires Redis dependency (already have for Celery)
- More complex implementation
- Depends on Issue #002 (auth) being fixed first

**Effort:** 4-6 hours

**Risk:** Low

**Implementation:**
```python
# shared/rate_limit.py
import redis
from datetime import datetime, timedelta
from typing import Optional

class RateLimiter:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.prefix = "htbase:ratelimit:"

    def check_limit(
        self,
        key: str,  # API key or IP
        limit: int,
        window_seconds: int
    ) -> tuple[bool, dict]:
        """
        Check if request is within rate limit.

        Returns:
            (is_allowed, info_dict)
        """
        window_key = f"{self.prefix}{key}:{int(datetime.utcnow().timestamp() // window_seconds)}"

        # Increment counter
        current = self.redis.incr(window_key)

        # Set expiry on first request
        if current == 1:
            self.redis.expire(window_key, window_seconds)

        # Check limit
        is_allowed = current <= limit
        reset_at = ((int(datetime.utcnow().timestamp() // window_seconds) + 1) * window_seconds)

        return is_allowed, {
            "limit": limit,
            "remaining": max(0, limit - current),
            "reset_at": reset_at,
            "retry_after": reset_at - int(datetime.utcnow().timestamp())
        }

# services/api-gateway/app/main.py
from shared.rate_limit import RateLimiter
from shared.config import get_settings

settings = get_settings()
rate_limiter = RateLimiter(settings.redis_url)

# Dependency
async def check_rate_limit(
    request: Request,
    api_key: str = Depends(verify_api_key)  # From Issue #002
):
    """Check rate limit before processing request."""
    # Use API key as identifier
    is_allowed, info = rate_limiter.check_limit(
        key=api_key,
        limit=100,  # From settings
        window_seconds=60
    )

    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded",
                "details": info
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "X-RateLimit-Reset": str(info["reset_at"]),
                "Retry-After": str(info["retry_after"])
            }
        )

    # Add rate limit headers to successful responses
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(info["reset_at"])

# Apply to routes
@router.post("/save", dependencies=[Depends(check_rate_limit)])
async def save_url(...):
    pass
```

---

### Option 3: Tiered Rate Limiting by Subscription

**Approach:** Different rate limits based on API key tier (free, pro, enterprise).

**Pros:**
- Revenue opportunity
- Fair resource allocation
- Encourages upgrades

**Cons:**
- Requires subscription management
- More complex
- Overkill for MVP

**Effort:** 8-10 hours

**Risk:** Medium

## Recommended Action

**Implement Option 1 (SlowAPI) immediately as temporary fix, then Option 2 (Redis-based) after auth is implemented.**

1. Add slowapi for IP-based limiting (stopgap)
2. Implement Issue #002 (API key authentication)
3. Switch to Redis-based per-API-key limiting
4. Add rate limit headers to all responses
5. Document rate limits in API docs
6. Add monitoring for rate limit hits

**Timeline:** BLOCKS MERGE - Critical for production deployment

## Technical Details

**Affected files:**
- `services/api-gateway/app/main.py` - Add rate limiting middleware
- `shared/rate_limit.py` - Create rate limiter utility (new file)
- `.env.microservices.example` - Already has config

**Rate limit tiers (suggested):**
```python
RATE_LIMITS = {
    "archive": "10/minute",      # Expensive operations
    "batch": "5/minute",          # Very expensive
    "status": "1000/minute",      # Cheap queries
    "download": "100/minute",     # Medium cost
    "admin": "50/minute",         # Administrative
}
```

**Response headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704801300
Retry-After: 45  # Seconds until reset
```

**Error response:**
```json
{
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Rate limit exceeded",
  "details": {
    "limit": "10/minute",
    "reset_at": "2026-01-09T12:35:00Z",
    "retry_after": 45
  }
}
```

## Resources

- **PR:** #6
- **Agent-Native Review:** `AGENT_NATIVE_REVIEW.md` (lines 599-696)
- **SlowAPI:** https://github.com/laurents/slowapi
- **Redis Rate Limiting:** https://redis.io/commands/incr/#pattern-rate-limiter

## Acceptance Criteria

- [ ] Rate limiting middleware implemented
- [ ] Different limits for different endpoint types
- [ ] Rate limit headers in all responses
- [ ] 429 status code for exceeded limits
- [ ] Retry-After header included
- [ ] Tests for rate limit enforcement
- [ ] Documentation updated with rate limits
- [ ] Monitoring dashboard for rate limit metrics

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Agent-Native Reviewer)

**Actions:**
- Audited API Gateway for rate limiting implementation
- Found configuration but no enforcement
- Identified abuse vectors (expensive Chromium, LLM operations)
- Evaluated SlowAPI vs Redis-based solutions
- Drafted implementation options

**Learnings:**
- Rate limit config exists but completely unused
- No protection from resource exhaustion
- Critical for production deployment
- Must fix after authentication (dependency)
- Redis already available for distributed limiting

## Notes

- **BLOCKS MERGE** - Critical security/cost issue
- **Depends on Issue #002** - Auth must be implemented first for per-key limits
- Use Redis (already deployed for Celery) for distributed rate limiting
- Monitor rate limit hit rate to tune limits
- Consider different tiers for future monetization
- Document limits clearly in API documentation
