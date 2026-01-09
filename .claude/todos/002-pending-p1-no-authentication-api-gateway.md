---
status: resolved
priority: p1
issue_id: "002"
tags: [code-review, security, authentication, api-gateway]
dependencies: []
---

# No Authentication on API Gateway

API Gateway has no authentication mechanism, allowing anyone to submit archive tasks and access endpoints.

## Problem Statement

The API Gateway (`services/api-gateway/app/`) has zero authentication or authorization. All endpoints are publicly accessible, allowing:
- Unauthenticated users to submit expensive archive tasks
- Access to task status and results
- Potential abuse for cryptocurrency mining, DDoS amplification
- Unauthorized access to archived content and summaries

**Impact:**
- Resource exhaustion from malicious task submission
- Cloud cost explosion (Chromium workers are expensive)
- Data privacy violations
- Compliance failures (GDPR, SOC 2)

## Findings

- **Location:** All routes in `services/api-gateway/app/routes/*.py`
- **Missing auth on:**
  - `POST /save` - Submit archive tasks (no auth!)
  - `POST /save/batch` - Batch tasks (no auth!)
  - `GET /tasks/{task_id}` - View task status (no auth!)
  - `GET /archives/{id}` - Download archives (no auth!)
  - `POST /summarize/{id}` - Trigger LLM summarization (expensive!)
- **.env.microservices.example** has `CORS_ORIGINS` defined but not enforced
- No API rate limiting configured (despite `API_RATE_LIMIT` env var)
- No user/tenant isolation in database schema

## Proposed Solutions

### Option 1: API Key Authentication (Recommended for MVP)

**Approach:** Implement API key-based authentication using FastAPI dependencies.

**Pros:**
- Simple to implement (2-3 hours)
- Good for service-to-service auth
- Easy to rotate keys
- Works well for programmatic access

**Cons:**
- Not suitable for web apps (key exposure risk)
- No user-specific permissions
- Keys must be managed securely

**Effort:** 3-4 hours

**Risk:** Low

**Implementation:**
```python
# shared/auth.py
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    api_key = credentials.credentials
    valid_keys = os.getenv("API_KEYS", "").split(",")

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return api_key

# Apply to routes
@router.post("/save", dependencies=[Depends(verify_api_key)])
async def save_url(...):
    ...
```

---

### Option 2: JWT with Auth0/Firebase Auth

**Approach:** Use JWT tokens from external identity provider (Auth0, Firebase, Clerk).

**Pros:**
- Industry standard
- User-level authentication
- Supports web + mobile clients
- Granular permissions possible

**Cons:**
- More complex setup
- Requires frontend integration
- External dependency

**Effort:** 8-10 hours

**Risk:** Medium

---

### Option 3: mTLS (Mutual TLS)

**Approach:** Require client certificates for all API Gateway connections.

**Pros:**
- Very secure (certificate-based)
- No credentials in transit
- Good for B2B integrations

**Cons:**
- Complex certificate management
- Poor developer experience
- Not suitable for web/mobile apps

**Effort:** 12-15 hours

**Risk:** High (complexity)

## Recommended Action

**Implement Option 1 (API Keys) immediately for MVP, plan Option 2 for production.**

1. Create API key authentication middleware
2. Add `verify_api_key` dependency to all protected routes
3. Store API keys in Secret Manager (not .env files)
4. Implement rate limiting per API key
5. Add audit logging for all API calls

**Timeline:** BLOCKS MERGE - Critical security issue

## Technical Details

**Affected files:**
- `services/api-gateway/app/routes/saves.py` - Archive endpoints
- `services/api-gateway/app/routes/tasks.py` - Task status endpoints
- `services/api-gateway/app/routes/files.py` - File download (if exists)
- `services/api-gateway/app/routes/admin.py` - Admin endpoints
- `services/api-gateway/app/main.py` - FastAPI app setup

**Related components:**
- CORS middleware needs enforcement
- Rate limiting needs implementation
- Audit logging for security events

**Rate limiting config:**
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.post("/save")
@limiter.limit("10/minute")
async def save_url(...):
    ...
```

## Resources

- **PR:** #6
- **FastAPI Security:** https://fastapi.tiangolo.com/tutorial/security/
- **OWASP API Security:** https://owasp.org/www-project-api-security/
- **Rate Limiting:** https://github.com/laurents/slowapi

## Acceptance Criteria

- [ ] API key authentication implemented for all routes
- [ ] Environment variable for API keys (comma-separated list)
- [ ] 401 Unauthorized returned for missing/invalid keys
- [ ] Rate limiting enforced per API key
- [ ] CORS properly configured and enforced
- [ ] Audit logging for authentication failures
- [ ] Documentation updated with authentication requirements
- [ ] Tests for authentication (valid key, invalid key, missing key)

## Work Log

### 2026-01-09 - Initial Discovery (Code Review)

**By:** Claude Sonnet 4.5 (Code Review Agent)

**Actions:**
- Audited all API routes for authentication
- Found zero auth mechanisms in place
- Reviewed .env.microservices.example for existing config
- Identified expensive operations (Chromium, LLM) at risk

**Learnings:**
- All routes are currently public - critical security gap
- Expensive operations (Chrome workers, LLM API calls) can be abused
- Rate limiting config exists but not enforced
- Must implement auth before production deployment

## Notes

- **BLOCKS MERGE** - Critical security vulnerability
- Combine with Issue #001 (Command Injection) for comprehensive security fix
- Consider user/tenant isolation in database schema for multi-tenant future
- API keys stored in Secret Manager, not .env files
- Document authentication in API documentation
