# Firebase API Endpoints Documentation

This document provides comprehensive documentation for all Firebase-related API endpoints in the HTBase system.

## ⚠️ Breaking Changes (2026-01-09)

**Endpoints Removed:**
- ❌ `POST /firebase/add-pocket-article` (replaced by `/add-article`)
- ❌ `POST /firebase/save` (replaced by `/add-article`)

**Migration Required:** Update your client applications to use the new consolidated `/add-article` endpoint. See [MIGRATION.md](./MIGRATION.md) for detailed migration guide.

**New Features:**
- ✅ Custom `item_id` support on all endpoints
- ✅ Unified API for adding articles (Pocket + generic metadata)
- ✅ Firestore sync control (opt-in/opt-out)

---

## Overview

The Firebase API provides mobile-optimized endpoints for article archiving with Pocket integration and Google Cloud Storage (GCS) support. These endpoints are designed for mobile applications that need efficient, filtered data access and signed download URLs.

**Location:** `services/api-gateway/app/routes/firebase.py`
**Router Prefix:** `/api/v1/firebase`

## Architecture Characteristics

- **Authentication:** HTTPBearer (API key required)
- **Rate Limiting:** Redis-based distributed rate limiting
- **Database:** Dual-write to PostgreSQL (primary) + Firestore (mobile replica)
- **Async Processing:** Returns immediately with task_id, processes in background
- **Storage:** Multi-provider (GCS, local backup)
- **Custom IDs:** Support for user-provided item_id (alphanumeric + underscore/hyphen)

## All Endpoints

### 1. POST /firebase/add-article

Add an article to the archive system with optional custom item_id, Pocket metadata, or generic metadata.

**Consolidated Endpoint:** This endpoint replaces `/add-pocket-article` and `/save`, providing all functionality from both endpoints plus custom item_id support.

**Full Path:** `POST /api/v1/firebase/add-article`

#### Request Model

```python
{
  # Core fields
  "url": "string",              # Article URL to archive (required)
  "archiver": "string",         # Optional: "all", "readability", "monolith", etc. (default: "all")

  # NEW: Custom item_id support
  "item_id": "string",          # Optional: Custom article identifier (alphanumeric + underscore/hyphen)

  # Pocket integration
  "user_id": "string",          # Optional: User identifier (for Pocket integration)
  "pocket_data": {              # Optional: Pocket metadata
    "title": "string",
    "excerpt": "string",
    "author": "string",
    "word_count": 0,
    "tags": ["tag1", "tag2"]
  },

  # Generic metadata (alternative to pocket_data)
  "metadata": {                 # Optional: Generic metadata
    "title": "string",
    "author": "string",
    "excerpt": "string"
  },

  # Firestore control
  "enable_firestore_sync": bool # Optional: Enable Firestore write (default: true)
}
```

#### Response Model

```python
{
  "item_id": "string",          # Article identifier (user-provided or auto-generated)
  "status": "string",           # "queued", "exists", "processing", "completed"
  "message": "string",          # Human-readable status message
  "task_id": "string"           # Background task ID (if queued)
}
```

#### What It Does

1. **Validate item_id:** If provided, validates format (alphanumeric + underscore/hyphen, max 255 chars)
2. **Determine ID:** Use custom item_id OR auto-generate with prefix ("pocket" for Pocket data, "article" for generic)
3. **Check Existing:** Queries database by URL (URL is unique constraint)
4. **Conflict Resolution:** If URL exists with different item_id, returns existing item_id
5. **Create Records:**
   - `ArchivedUrl` record with URL and metadata
   - `UrlMetadata` record with Pocket or generic data
6. **Write to Firestore:** If `enable_firestore_sync=true` and Firestore configured
7. **Queue Tasks:** Dispatches archive tasks to background workers
8. **Return Status:** Immediate response with task_id for polling

#### Example Request (with Custom item_id)

```bash
curl -X POST http://localhost:8000/api/v1/firebase/add-article \
  -H "Authorization: Bearer htbase_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/amazing-article",
    "item_id": "custom_12345",
    "pocket_data": {
      "title": "Amazing Article",
      "excerpt": "This article is amazing...",
      "author": "John Doe",
      "word_count": 1500
    },
    "archiver": "all",
    "enable_firestore_sync": true
  }'
```

#### Example Request (Auto-Generated ID, Generic Metadata)

```bash
curl -X POST http://localhost:8000/api/v1/firebase/add-article \
  -H "Authorization: Bearer htbase_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/another-article",
    "metadata": {
      "title": "Another Article",
      "author": "Jane Smith"
    },
    "archiver": "readability"
  }'
```

#### Example Response

```json
{
  "item_id": "custom_12345",
  "status": "queued",
  "message": "Article queued for archiving with 5 archiver(s)",
  "task_id": "task_uuid_12345"
}
```

#### item_id Behavior

| Scenario | Result |
|----------|--------|
| User provides `item_id`, URL is new | Uses custom item_id |
| User omits `item_id`, has `pocket_data` | Auto-generates `pocket_{hash}` |
| User omits `item_id`, has `metadata` only | Auto-generates `article_{hash}` |
| User provides `item_id`, URL exists with different item_id | Returns existing item_id (conflict resolved) |
| User provides invalid `item_id` format | Returns 400 error |

#### Rate Limiting

**Limit:** 10 requests/minute per API key
**Headers:**
- `X-RateLimit-Limit: 10`
- `X-RateLimit-Remaining: 7`
- `X-RateLimit-Reset: 1704801300`

#### Firestore Integration

**Collection:** `articles/{item_id}`
**Data Written (if `enable_firestore_sync=true`):**
- Filtered metadata (no `text_content`)
- Pocket data map (if provided)
- Archive status map (per archiver)

---

### 2. GET /firebase/download/{item_id}/{archiver}

Generate a signed download URL for archived article content.

**Full Path:** `GET /api/v1/firebase/download/{item_id}/{archiver}`

#### Path Parameters

- `item_id` (string, required): Article identifier
- `archiver` (string, required): Archiver name (`readability`, `monolith`, `pdf`, `screenshot`, `singlefile-cli`)

#### Query Parameters

- `expiration_hours` (integer, optional): URL expiration time (1-168 hours, default: 24)

#### Response Model

```python
{
  "download_url": "string",     # Signed GCS URL with token
  "expires_in": 0,              # Expiration in seconds
  "archiver": "string",         # Archiver type
  "gcs_path": "string"          # GCS storage path (gs://bucket/path)
}
```

#### What It Does

1. **Find Article:** Queries database for `item_id`
2. **Get Artifact:** Finds successful artifact for specified archiver
3. **Extract GCS Path:** Gets cloud storage path from artifact metadata
4. **Generate Signed URL:** Creates time-limited signed URL (default: 24 hours)
5. **Return URL:** Provides download URL with expiration info

#### Example Request

```bash
curl -X GET "http://localhost:8000/api/v1/firebase/download/pocket-a1b2c3/readability?expiration_hours=48" \
  -H "Authorization: Bearer htbase_live_abc123..."
```

#### Example Response

```json
{
  "download_url": "https://storage.googleapis.com/bucket/archives/pocket-a1b2c3/readability/output.html?X-Goog-Algorithm=...&X-Goog-Signature=...",
  "expires_in": 172800,
  "archiver": "readability",
  "gcs_path": "gs://htbase-archives/archives/pocket-a1b2c3/readability/output.html"
}
```

#### Rate Limiting

**Limit:** 100 requests/minute per API key

#### Error Responses

| Status Code | Condition | Response |
|-------------|-----------|----------|
| 404 | Article not found | `{"detail": "Article not found"}` |
| 404 | No successful artifact | `{"detail": "No successful archive found for archiver"}` |
| 404 | No cloud storage path | `{"detail": "No cloud storage path available"}` |
| 500 | GCS error | `{"detail": "Failed to generate signed URL"}` |

---

### 3. POST /firebase/archive

Trigger archival for existing article (called by Firebase Cloud Function).

**Supports Custom item_id:** This endpoint now validates custom item_ids and accepts any alphanumeric + underscore/hyphen identifier.

**Full Path:** `POST /api/v1/firebase/archive`

#### Request Model

```python
{
  "item_id": "string",          # Article item_id (can be custom or auto-generated)
  "url": "string",              # Article URL
  "archiver": "string"          # Archiver to use (default: "all")
}
```

#### Response Model

```python
{
  "item_id": "string",
  "status": "string",           # Overall status: "queued", "processing", "completed", "failed", "already_queued"
  "message": "string",
  "task_id": "string"
}
```

#### What It Does

1. **Validate item_id:** Validates format if provided (alphanumeric + underscore/hyphen, max 255 chars)
2. **Check Article:** Verifies article exists by `item_id`
3. **Create if Missing:** Creates `ArchivedUrl` if doesn't exist
4. **Check Pending:** Skips archivers already pending/in_progress
5. **Queue Tasks:** Dispatches only for missing/failed archivers
6. **Update Firestore:** Marks artifacts as PENDING in Firestore
7. **Return Status:** Status for each archiver

#### Example Request

```bash
curl -X POST http://localhost:8000/api/v1/firebase/archive \
  -H "Authorization: Bearer htbase_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "pocket-a1b2c3d4e5f6",
    "url": "https://example.com/article",
    "archiver": "monolith"
  }'
```

#### Example Response

```json
{
  "item_id": "pocket-a1b2c3d4e5f6",
  "status": "queued",
  "message": "Archival queued for monolith",
  "task_id": "task_uuid_67890"
}
```

#### Use Case

This endpoint is designed to be called by Firebase Cloud Functions when a user saves an article from the mobile app. The Cloud Function:

1. Receives save event from mobile
2. Checks if article exists in Firestore
3. Calls this endpoint to trigger archival
4. Returns immediately to mobile user

---

## Authentication & Security

### API Key Authentication

All Firebase endpoints require Bearer token authentication:

```http
Authorization: Bearer htbase_live_abc123def456ghi789jkl012mno345pqr
```

**Configuration:** Set via `API_KEYS` environment variable (comma-separated list)

**Key Format:** `htbase_{environment}_{random_string}`
- `htbase_live_...` - Production keys
- `htbase_test_...` - Development/testing keys

### Rate Limiting

**Implementation:** Redis-based distributed rate limiting with sliding window algorithm

**Limits by Endpoint Type:**
| Endpoint Type | Limit | Window |
|--------------|-------|--------|
| Archive operations (POST) | 10 requests | 1 minute |
| Download operations (GET) | 100 requests | 1 minute |

**Response Headers:**
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1704801300
```

**Rate Limit Exceeded (429):**
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

---

## Available Archivers

When specifying `archiver` in requests, you can use:

| Archiver | Description | Output Format | Size |
|----------|-------------|---------------|------|
| `all` | All archivers (default) | Multiple files | Largest |
| `readability` | Text extraction with cleaned HTML | HTML | ~50-500KB |
| `monolith` | Single-file HTML with embedded assets | HTML | ~1-10MB |
| `singlefile-cli` | Alternative single-file bundler | HTML | ~1-10MB |
| `pdf` | Chromium PDF export | PDF | ~500KB-5MB |
| `screenshot` | Full page screenshot | PNG | ~100KB-2MB |

**"all" expands to:** `["readability", "monolith", "singlefile-cli", "pdf", "screenshot"]`

---

## Error Handling

### HTTP Status Codes

| Status | Meaning | Common Causes |
|--------|---------|---------------|
| 200 OK | Success | Request completed successfully |
| 202 Accepted | Queued | Task queued for async processing |
| 400 Bad Request | Invalid input | Malformed JSON, missing required fields |
| 401 Unauthorized | Auth failed | Invalid or missing API key |
| 404 Not Found | Resource not found | Article/artifact doesn't exist |
| 429 Too Many Requests | Rate limited | Exceeded rate limit |
| 500 Internal Server Error | Server error | Database/storage/worker failure |

### Error Response Format

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE",
  "details": {
    "field": "value"
  }
}
```

---

## Comparison with Standard Endpoints

### Firebase Endpoints vs Standard `/save` Endpoint

| Feature | Firebase Endpoints | Standard `/save` |
|---------|-------------------|------------------|
| **Location** | `/api/v1/firebase/*` | `/api/v1/save` |
| **Firestore Write** | Optional (if dual persistence) | No |
| **Pocket Data** | Full support (`add-pocket-article`) | No |
| **User Tracking** | `user_id` supported | No user context |
| **ID Generation** | Hash-based (`pocket-`, `article-`) | User-provided |
| **Duplicate Check** | By `item_id` (hash) | By URL |
| **Mobile Optimized** | Yes (filtered Firestore data) | No |
| **Download URLs** | Signed GCS URLs with expiration | Stream from storage |
| **Cloud Function** | Designed for (`/archive`) | Direct API use |

### When to Use Which

**Use Firebase Endpoints When:**
- Building mobile apps with Firestore
- Need Pocket integration
- Want signed download URLs with expiration
- Need filtered, mobile-optimized data
- Integrating with Firebase Cloud Functions

**Use Standard Endpoints When:**
- Building web apps or server-to-server
- Don't need Firestore replication
- Want full control over IDs
- Need raw file downloads
- Direct API access without Firebase

---

## Configuration

### Environment Variables

```bash
# Authentication
API_KEYS=htbase_live_key1,htbase_live_key2,htbase_test_key3

# Rate Limiting
REDIS_URL=redis://localhost:6379/0

# Dual Persistence
ENABLE_DUAL_PERSISTENCE=true
DUAL_WRITE_FAILURE_MODE=log_and_continue  # fail_fast | log_and_continue | queue_retry

# Firestore
FIRESTORE_PROJECT_ID=your-firebase-project
FIRESTORE_CREDENTIALS_PATH=/path/to/credentials.json

# Storage
GCS_BUCKET=htbase-archives
STORAGE_PROVIDERS=gcs,local
```

### Dual Persistence Failure Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `fail_fast` | Fail entire operation if Firestore fails | Strict consistency required |
| `log_and_continue` | Log warning, continue with PostgreSQL only | Best-effort Firestore (recommended) |
| `queue_retry` | Queue for retry background sync | Not yet implemented |

---

## Code References

**Main Routes File:**
- `services/api-gateway/app/routes/firebase.py:1-250`

**Key Functions:**
- `add_pocket_article()` - Line 45-120
- `download_artifact()` - Line 125-180
- `save_article()` - Line 185-220
- `archive_article()` - Line 225-285

**Dependencies:**
- `shared/auth.py` - API key verification
- `shared/rate_limit.py` - Rate limiting middleware
- `shared/storage/dual_database_storage.py` - Database orchestration
- `shared/models/__init__.py` - Request/response models

---

## Next Steps

For detailed understanding of:
- **Complete request flow:** See [REQUEST_FLOW_COMPLETE.md](./REQUEST_FLOW_COMPLETE.md)
- **Database architecture:** See [DUAL_DATABASE_ARCHITECTURE.md](./DUAL_DATABASE_ARCHITECTURE.md)
- **Visual flows:** See [diagrams/SEQUENCE_DIAGRAMS.md](./diagrams/SEQUENCE_DIAGRAMS.md)
- **System architecture:** See [ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md)
