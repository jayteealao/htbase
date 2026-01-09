# Firebase API Migration Guide

**Effective Date:** 2026-01-09
**Breaking Changes:** Yes - Old endpoints removed

---

## Summary

HTBase has consolidated redundant Firebase API endpoints to simplify the API surface and add custom `item_id` support. The old `/add-pocket-article` and `/save` endpoints have been **removed** and replaced with a single unified `/add-article` endpoint.

### What Changed

| Old Endpoint | Status | Replacement |
|--------------|--------|-------------|
| `POST /firebase/add-pocket-article` | ❌ **Removed** | `POST /firebase/add-article` |
| `POST /firebase/save` | ❌ **Removed** | `POST /firebase/add-article` |
| `GET /firebase/download/{item_id}/{archiver}` | ✅ **Unchanged** | No changes |
| `POST /firebase/archive` | ✅ **Enhanced** | Now validates custom item_id |

### New Features

- ✅ **Custom item_id Support**: Provide your own article identifiers
- ✅ **Unified API**: Single endpoint for all article types (Pocket + generic)
- ✅ **Firestore Control**: Opt-in/opt-out of Firestore sync
- ✅ **Better Validation**: item_id format validation (alphanumeric + underscore/hyphen)

---

## Migration Quick Reference

### From `/add-pocket-article` to `/add-article`

**Old Request:**
```json
POST /api/v1/firebase/add-pocket-article
{
  "user_id": "user_123",
  "url": "https://example.com/article",
  "pocket_data": {
    "title": "Article Title",
    "excerpt": "Article excerpt",
    "author": "John Doe",
    "word_count": 1500
  },
  "archiver": "all"
}
```

**New Request (equivalent):**
```json
POST /api/v1/firebase/add-article
{
  "url": "https://example.com/article",
  "user_id": "user_123",
  "pocket_data": {
    "title": "Article Title",
    "excerpt": "Article excerpt",
    "author": "John Doe",
    "word_count": 1500
  },
  "archiver": "all",
  "enable_firestore_sync": true
}
```

**Changes:**
- ✅ Endpoint path changed: `/add-pocket-article` → `/add-article`
- ✅ Added `enable_firestore_sync: true` (default, can omit)
- ✅ All other fields unchanged
- ✅ Response format unchanged

---

### From `/save` to `/add-article`

**Old Request:**
```json
POST /api/v1/firebase/save
{
  "url": "https://example.com/article",
  "archiver": "readability",
  "metadata": {
    "title": "Article Title",
    "author": "Jane Smith",
    "excerpt": "Article excerpt"
  }
}
```

**New Request (equivalent):**
```json
POST /api/v1/firebase/add-article
{
  "url": "https://example.com/article",
  "archiver": "readability",
  "metadata": {
    "title": "Article Title",
    "author": "Jane Smith",
    "excerpt": "Article excerpt"
  },
  "enable_firestore_sync": false
}
```

**Changes:**
- ✅ Endpoint path changed: `/save` → `/add-article`
- ✅ Added `enable_firestore_sync: false` (since old `/save` didn't sync to Firestore)
- ✅ All other fields unchanged
- ✅ Response format unchanged

---

## Custom item_id Usage

### New Feature: Provide Your Own item_id

You can now provide custom article identifiers instead of relying on auto-generated hash-based IDs.

**Example with Custom item_id:**
```json
POST /api/v1/firebase/add-article
{
  "url": "https://example.com/article",
  "item_id": "pocket_1234567890",
  "pocket_data": {
    "title": "Article Title"
  }
}
```

**Rules:**
- Alphanumeric characters only + underscore (`_`) and hyphen (`-`)
- Maximum 255 characters
- Cannot be changed once created (URL is unique constraint)

**Conflict Resolution:**
- If URL already exists with different item_id, returns existing item_id
- Warning logged but request succeeds with existing item_id

---

## Migration Examples

### Example 1: Basic Pocket Article

**Before:**
```bash
curl -X POST http://localhost:8000/api/v1/firebase/add-pocket-article \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "url": "https://example.com/article",
    "pocket_data": {"title": "Test"},
    "archiver": "all"
  }'
```

**After:**
```bash
curl -X POST http://localhost:8000/api/v1/firebase/add-article \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "user_id": "user_123",
    "pocket_data": {"title": "Test"},
    "archiver": "all"
  }'
```

---

### Example 2: Generic Article (No Pocket Data)

**Before:**
```bash
curl -X POST http://localhost:8000/api/v1/firebase/save \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "archiver": "readability",
    "metadata": {"title": "Test"}
  }'
```

**After:**
```bash
curl -X POST http://localhost:8000/api/v1/firebase/add-article \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "archiver": "readability",
    "metadata": {"title": "Test"},
    "enable_firestore_sync": false
  }'
```

---

### Example 3: Custom item_id (New Feature)

**New:**
```bash
curl -X POST http://localhost:8000/api/v1/firebase/add-article \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "item_id": "custom_12345",
    "pocket_data": {"title": "Test"},
    "archiver": "all"
  }'
```

---

## Response Format Changes

### Response Fields

**Old Response (add-pocket-article):**
```json
{
  "article_id": "pocket_a1b2c3d4e5f6",
  "status": "queued",
  "message": "Article queued for archiving...",
  "task_id": "task_uuid_12345"
}
```

**New Response (add-article):**
```json
{
  "item_id": "pocket_a1b2c3d4e5f6",
  "status": "queued",
  "message": "Article queued for archiving with 5 archiver(s)",
  "task_id": "task_uuid_12345"
}
```

**Change:** `article_id` → `item_id` (consistent naming across all endpoints)

---

## Code Migration Examples

### Python Client

**Before:**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/firebase/add-pocket-article",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "user_id": "user_123",
        "url": url,
        "pocket_data": pocket_data,
        "archiver": "all"
    }
)

article_id = response.json()["article_id"]
```

**After:**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/firebase/add-article",  # Changed endpoint
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "url": url,
        "user_id": "user_123",
        "pocket_data": pocket_data,
        "archiver": "all",
        # enable_firestore_sync defaults to True
    }
)

item_id = response.json()["item_id"]  # Changed field name
```

---

### JavaScript/TypeScript Client

**Before:**
```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/firebase/add-pocket-article",
  {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      user_id: "user_123",
      url: url,
      pocket_data: pocketData,
      archiver: "all"
    })
  }
);

const { article_id } = await response.json();
```

**After:**
```typescript
const response = await fetch(
  "http://localhost:8000/api/v1/firebase/add-article",  // Changed endpoint
  {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      url: url,
      user_id: "user_123",
      pocket_data: pocketData,
      archiver: "all",
      // enable_firestore_sync defaults to true
    })
  }
);

const { item_id } = await response.json();  // Changed field name
```

---

## FAQ

### Q: Do I need to change my existing articles?

**A:** No. Existing articles in your database are unchanged. Only API client code needs updating.

---

### Q: What happens to my auto-generated item_ids?

**A:** They remain unchanged. The new endpoint auto-generates IDs the same way:
- Pocket articles: `pocket_{hash}`
- Generic articles: `article_{hash}`

---

### Q: Can I use the old endpoints temporarily?

**A:** No. The old endpoints have been **removed**. You must migrate to `/add-article` immediately.

---

### Q: What if I provide an item_id for a URL that already exists?

**A:** The API returns the existing item_id and logs a warning. Your custom item_id is ignored to maintain URL uniqueness.

**Example:**
```json
// First request
POST /add-article {"url": "https://example.com", "item_id": "id_1"}
Response: {"item_id": "id_1", "status": "queued"}

// Second request (same URL, different item_id)
POST /add-article {"url": "https://example.com", "item_id": "id_2"}
Response: {"item_id": "id_1", "status": "exists"}  // Returns existing item_id
```

---

### Q: Can I disable Firestore sync for Pocket articles?

**A:** Yes! Set `enable_firestore_sync: false` in your request:

```json
{
  "url": "https://example.com/article",
  "pocket_data": {...},
  "enable_firestore_sync": false
}
```

---

### Q: What characters are allowed in custom item_id?

**A:** Alphanumeric (a-z, A-Z, 0-9), underscore (`_`), and hyphen (`-`) only. Max 255 characters.

**Valid:**
- `pocket_12345`
- `article-abc-def`
- `my_custom_id_123`

**Invalid:**
- `article with spaces` (spaces not allowed)
- `article@123` (special characters not allowed)
- `article/123` (slashes not allowed)

---

### Q: How do I migrate Firebase Cloud Functions?

**A:** If you have Cloud Functions calling `/add-pocket-article` or `/save`, update the endpoint URL:

```javascript
// Before
const response = await fetch(
  `${API_BASE_URL}/firebase/add-pocket-article`,
  // ...
);

// After
const response = await fetch(
  `${API_BASE_URL}/firebase/add-article`,
  // ...
);
```

---

### Q: Does the `/archive` endpoint work with custom item_ids?

**A:** Yes! The `/archive` endpoint now validates custom item_ids and accepts any format matching the rules.

---

### Q: Will there be more breaking changes?

**A:** No immediate plans. This consolidation eliminates technical debt and provides a stable foundation. Future enhancements will be backward-compatible where possible.

---

## Rollback (If Issues Occur)

If you encounter critical issues after migration:

1. **Check Error Logs**: Look for validation errors or 400 responses
2. **Verify Request Format**: Ensure you're using the new endpoint and field names
3. **Test with curl**: Verify the endpoint works with simple curl requests
4. **Contact Support**: File an issue at https://github.com/anthropics/htbase/issues

---

## Migration Checklist

- [ ] Update API endpoint URLs: `/add-pocket-article` → `/add-article`, `/save` → `/add-article`
- [ ] Update response field references: `article_id` → `item_id`
- [ ] Add `enable_firestore_sync` field if needed (optional, defaults to `true`)
- [ ] Test with sample requests (see examples above)
- [ ] Update API documentation in your client code
- [ ] Deploy updated clients to production
- [ ] Monitor error logs for validation failures
- [ ] Consider using custom item_ids for easier tracking (optional)

---

## Support

**Documentation:** [FIREBASE_API_FLOW.md](./FIREBASE_API_FLOW.md)
**Issues:** https://github.com/anthropics/htbase/issues
**Plan Reference:** [C:\Users\jayte\.claude\plans\noble-dreaming-sedgewick.md](../.claude/plans/noble-dreaming-sedgewick.md)

---

## Timeline

| Date | Event |
|------|-------|
| 2026-01-09 | Breaking changes implemented |
| 2026-01-09 | Old endpoints removed |
| 2026-01-09 | Documentation updated |
| 2026-01-09 | Migration guide published |

**Migration is required immediately.** Old endpoints are no longer available.
