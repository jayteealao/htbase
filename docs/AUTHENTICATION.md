# HTBase Authentication Guide

> **Current Status:** Authentication is **not yet implemented**. This document describes the planned implementation based on [Issue #002](../.claude/todos/002-pending-p0-authentication-system-missing.md).

---

## Overview

HTBase will support API key-based authentication for production deployments. Currently, the API is **open and unauthenticated**, which is suitable for local development but **not production-ready**.

**Timeline:** P0 priority - must be implemented before general availability.

---

## Current State (Development)

### No Authentication Required

All API endpoints are currently accessible without authentication:

```bash
# Works without any credentials
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"id": "test", "url": "https://example.com"}'
```

**Security Risk:** Anyone with network access can use your instance.

**Recommendation:** Only run HTBase on localhost or private networks until authentication is implemented.

---

## Planned Implementation

### API Key Authentication

HTBase will implement Bearer token authentication following industry standards.

### Planned Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Request                          │
│  Authorization: Bearer sk_live_abc123...                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 FastAPI Middleware                          │
│  - Extract Bearer token                                     │
│  - Validate token format                                    │
│  - Check against API keys database                          │
│  - Verify active status and permissions                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼ Valid                       ▼ Invalid
┌──────────────────┐          ┌─────────────────┐
│  Process Request │          │  401 Unauthorized│
└──────────────────┘          └─────────────────┘
```

---

## API Key Management

### Key Format

API keys will follow this format:

```
htbase_{environment}_{random_string}

Examples:
- htbase_live_abc123def456ghi789jkl012mno345pqr (replace X with random chars)
- htbase_test_xyz987wvu654tsr321qpo098nml765kji (replace Y with random chars)
```

**Components:**
- `htbase_` - Prefix indicating HTBase API key
- `live`/`test` - Environment identifier
- 32-character random string (alphanumeric)

---

### Key Generation (Planned)

#### Option 1: Admin API Endpoint

```bash
# Generate new API key
curl -X POST http://localhost:8000/api/admin/keys \
  -H 'Authorization: Bearer {admin_token}' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Production Agent",
    "environment": "live",
    "permissions": ["archive", "retrieve", "summarize"]
  }'
```

**Response:**
```json
{
  "key_id": "key_abc123",
  "api_key": "htbase_live_abc123def456ghi789jkl012mno345pqr",
  "name": "Production Agent",
  "environment": "live",
  "created_at": "2026-01-09T12:00:00Z",
  "permissions": ["archive", "retrieve", "summarize"],
  "active": true
}
```

**Warning:** The `api_key` value is only shown once. Store it securely.

---

#### Option 2: CLI Tool

```bash
# Generate key via CLI
python -m app.cli.generate_key \
  --name "Production Agent" \
  --environment live \
  --permissions archive,retrieve,summarize
```

**Output:**
```
Generated API Key:
  Key ID: key_abc123
  API Key: htbase_live_abc123def456ghi789jkl012mno345pqr
  Name: Production Agent
  Environment: live

Store this key securely - it will not be shown again.
```

---

### Key Storage

API keys will be stored in the PostgreSQL database:

**Schema:**
```sql
CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    key_id VARCHAR(64) UNIQUE NOT NULL,
    key_hash VARCHAR(128) NOT NULL,  -- bcrypt hash of sk_...
    name VARCHAR(255) NOT NULL,
    environment VARCHAR(10) NOT NULL,  -- 'live' or 'test'
    permissions JSONB DEFAULT '[]',
    active BOOLEAN DEFAULT true,
    rate_limit_per_minute INTEGER DEFAULT 60,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_by VARCHAR(255),
    notes TEXT
);

CREATE INDEX idx_api_keys_key_id ON api_keys(key_id);
CREATE INDEX idx_api_keys_active ON api_keys(active);
```

**Security:**
- Only bcrypt hashes stored (never plaintext)
- Keys shown only once at creation time
- Automatic expiration support

---

## Using API Keys

### Making Authenticated Requests

Once implemented, all API requests will require authentication:

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Authorization: Bearer htbase_live_abc123def456ghi789jkl012mno345pqr' \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "article-123",
    "url": "https://example.com"
  }'
```

### Python Example

```python
import requests

API_KEY = "htbase_live_abc123def456ghi789jkl012mno345pqr"
BASE_URL = "http://localhost:8000"

def archive_url(url: str, item_id: str, archiver: str = "readability"):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        f"{BASE_URL}/api/save/{archiver}",
        headers=headers,
        json={"url": url, "id": item_id}
    )
    response.raise_for_status()
    return response.json()
```

### JavaScript Example

```javascript
const API_KEY = 'htbase_live_abc123def456ghi789jkl012mno345pqr';
const BASE_URL = 'http://localhost:8000';

async function archiveUrl(url, itemId, archiver = 'readability') {
  const response = await fetch(`${BASE_URL}/api/save/${archiver}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ url, id: itemId })
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }

  return response.json();
}
```

---

## Error Responses

### 401 Unauthorized - Missing Token

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"id": "test", "url": "https://example.com"}'
```

**Response:**
```json
{
  "detail": "Missing authorization header",
  "error_code": "AUTH_MISSING",
  "documentation_url": "https://docs.htbase.com/auth"
}
```

**Status:** 401

---

### 401 Unauthorized - Invalid Token

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Authorization: Bearer sk_live_invalid' \
  -H 'Content-Type: application/json' \
  -d '{"id": "test", "url": "https://example.com"}'
```

**Response:**
```json
{
  "detail": "Invalid API key",
  "error_code": "INVALID_API_KEY",
  "documentation_url": "https://docs.htbase.com/auth"
}
```

**Status:** 401

---

### 401 Unauthorized - Expired Token

**Response:**
```json
{
  "detail": "API key has expired",
  "error_code": "API_KEY_EXPIRED",
  "expired_at": "2026-01-01T00:00:00Z",
  "documentation_url": "https://docs.htbase.com/auth"
}
```

**Status:** 401

---

### 403 Forbidden - Insufficient Permissions

```bash
# Attempting to summarize with a key that lacks summarize permission
curl -X POST http://localhost:8000/api/admin/summarize \
  -H 'Authorization: Bearer sk_live_read_only_key' \
  -H 'Content-Type: application/json' \
  -d '{"item_id": "test"}'
```

**Response:**
```json
{
  "detail": "Insufficient permissions for this operation",
  "error_code": "FORBIDDEN",
  "required_permission": "summarize",
  "your_permissions": ["archive", "retrieve"]
}
```

**Status:** 403

---

## Permissions System

### Available Permissions

| Permission | Allows | Endpoints |
|------------|--------|-----------|
| `archive` | Create archives | `POST /api/save/*`, `POST /api/batch/*` |
| `retrieve` | Download archives | `GET /api/retrieve` |
| `summarize` | Generate summaries | `POST /api/admin/summarize` |
| `delete` | Delete archives | `DELETE /api/admin/delete` |
| `admin` | All operations | All endpoints |

### Permission Checking (Planned Implementation)

```python
from functools import wraps
from fastapi import HTTPException, Depends

def require_permission(permission: str):
    """Decorator to require specific permission."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, api_key: APIKey = Depends(get_api_key), **kwargs):
            if not api_key.has_permission(permission):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "detail": "Insufficient permissions",
                        "error_code": "FORBIDDEN",
                        "required_permission": permission,
                        "your_permissions": api_key.permissions
                    }
                )
            return await func(*args, api_key=api_key, **kwargs)
        return wrapper
    return decorator

# Usage
@router.post("/save/{archiver}")
@require_permission("archive")
async def save_endpoint(archiver: str, request: SaveRequest, api_key: APIKey):
    # Implementation
    pass
```

---

## Rate Limiting

### Per-Key Rate Limits

Each API key will have a configurable rate limit:

```json
{
  "key_id": "key_abc123",
  "rate_limit_per_minute": 60,
  "rate_limit_per_hour": 1000,
  "rate_limit_per_day": 10000
}
```

### Rate Limit Headers

Responses will include rate limit information:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704811200
```

### 429 Rate Limit Exceeded

```json
{
  "detail": "Rate limit exceeded",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "limit": "60/minute",
  "reset_at": "2026-01-09T12:35:00Z",
  "retry_after": 45
}
```

**Status:** 429

**Headers:**
```
Retry-After: 45
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704811200
```

---

## Best Practices

### Security

1. **Never commit API keys to version control**
   ```bash
   # .gitignore
   .env
   secrets/
   *.key
   ```

2. **Store keys in environment variables**
   ```bash
   export HTBASE_API_KEY="sk_live_..."
   ```

3. **Use different keys for different environments**
   - `sk_test_...` for development
   - `sk_live_...` for production

4. **Rotate keys regularly**
   - Generate new key
   - Update applications
   - Deactivate old key

5. **Use least-privilege permissions**
   ```json
   {
     "name": "Read-only agent",
     "permissions": ["retrieve"]  // Only retrieve, no archive/delete
   }
   ```

---

### Key Management

#### Environment Variables

```bash
# .env file
HTBASE_API_KEY=htbase_live_abc123def456ghi789jkl012mno345pqr
HTBASE_BASE_URL=https://htbase.example.com
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("HTBASE_API_KEY")
BASE_URL = os.getenv("HTBASE_BASE_URL")
```

#### Secrets Management

**For production deployments:**

1. **Docker Secrets**
   ```yaml
   # docker-compose.yml
   services:
     htbase:
       secrets:
         - htbase_api_key

   secrets:
     htbase_api_key:
       file: ./secrets/api_key.txt
   ```

2. **Cloud Secrets Manager**
   ```python
   # Google Cloud Secret Manager
   from google.cloud import secretmanager

   client = secretmanager.SecretManagerServiceClient()
   name = f"projects/{project_id}/secrets/htbase-api-key/versions/latest"
   response = client.access_secret_version(request={"name": name})
   API_KEY = response.payload.data.decode("UTF-8")
   ```

3. **Kubernetes Secrets**
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: htbase-api-key
   type: Opaque
   data:
     api-key: c2tfbGl2ZV8uLi4=  # base64 encoded
   ```

---

## Migration Guide

### Before Authentication (Current)

```python
# Works without auth
requests.post(
    "http://localhost:8000/api/save/readability",
    json={"url": url, "id": item_id}
)
```

### After Authentication (Planned)

```python
# Requires API key
requests.post(
    "http://localhost:8000/api/save/readability",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={"url": url, "id": item_id}
)
```

### Backward Compatibility

To ease migration, HTBase will support an optional authentication mode:

```bash
# Enable optional auth (default: required)
export AUTH_REQUIRED=false
```

This allows gradual migration:
1. Deploy authentication system
2. Generate API keys
3. Update clients with keys
4. Enable required auth

---

## Development Setup

### Local Development Without Auth

For local development, you can disable authentication:

```bash
export AUTH_REQUIRED=false
docker compose up
```

### Testing Authentication Locally

To test authentication in development:

1. **Enable authentication**
   ```bash
   export AUTH_REQUIRED=true
   ```

2. **Generate a test key**
   ```bash
   python -m app.cli.generate_key --name "Dev Key" --environment test
   ```

3. **Use the key in requests**
   ```bash
   curl -X POST http://localhost:8000/api/save/readability \
     -H "Authorization: Bearer sk_test_..." \
     -H "Content-Type: application/json" \
     -d '{"id": "test", "url": "https://example.com"}'
   ```

---

## Implementation Checklist

Based on [Issue #002](../.claude/todos/002-pending-p0-authentication-system-missing.md), the following must be implemented:

- [ ] Database schema for API keys
- [ ] Key generation CLI tool
- [ ] Admin API endpoints for key management
- [ ] FastAPI authentication middleware
- [ ] Permission system
- [ ] Rate limiting per key
- [ ] Error responses (401, 403, 429)
- [ ] Key rotation mechanism
- [ ] Audit logging for key usage
- [ ] Documentation updates
- [ ] Client library updates
- [ ] Migration guide for existing users

**Priority:** P0 (blocks production deployment)

**Estimated Effort:** 2-3 days

---

## FAQ

### Q: When will authentication be available?
**A:** Authentication is a P0 priority and must be implemented before general availability. Track progress in [Issue #002](../.claude/todos/002-pending-p0-authentication-system-missing.md).

### Q: Can I use HTBase in production without auth?
**A:** Not recommended. Only deploy on private networks or localhost until authentication is implemented.

### Q: Will existing clients break when auth is added?
**A:** A migration period with optional auth will be provided to allow gradual client updates.

### Q: How are API keys stored?
**A:** Keys are hashed using bcrypt and stored in PostgreSQL. Plaintext keys are never stored.

### Q: Can I use OAuth2 or JWT tokens?
**A:** Initial implementation will support API keys only. OAuth2 support may be added in future versions.

### Q: How do I revoke a compromised key?
**A:** Use the admin API to deactivate the key: `PATCH /api/admin/keys/{key_id} {"active": false}`

---

## Resources

- [Issue #002 - Authentication System Missing](../.claude/todos/002-pending-p0-authentication-system-missing.md)
- [API Quickstart](API_QUICKSTART.md)
- [Error Codes Reference](ERROR_CODES.md)
- [Agent Best Practices](AGENT_GUIDE.md)

---

**Questions?** Open an issue on GitHub.
