# Firebase API Migration Guide

## Overview

The legacy Firebase endpoints (`/firebase/...`) are deprecated and will be removed in v2.0.0.
Migrate to the new microservices endpoints (`/api/v1/firebase/...`) for:
- ✅ Proper custom item_id support
- ✅ Better validation and error handling
- ✅ Production-ready horizontal scaling
- ✅ Consolidated endpoints (less duplication)

## Deprecation Timeline

- **Now:** Legacy endpoints marked deprecated, warnings logged
- **v1.5.0** (3 months): Increase warning log levels
- **v2.0.0** (6 months): Remove legacy endpoints entirely

## Endpoint Mapping

### 1. Add Pocket Article

**Legacy:**
```bash
POST /firebase/add-pocket-article
{
  "user_id": "user123",
  "url": "https://example.com/article",
  "pocket_data": {"title": "Article", "item_id": "custom_id"},
  "archiver": "all"
}
```

**New:**
```bash
POST /api/v1/firebase/add-article
{
  "user_id": "user123",
  "url": "https://example.com/article",
  "item_id": "custom_id",                    # ✅ Now first-class field
  "pocket_data": {"title": "Article"},
  "archiver": "all"
}
```

**Changes:**
- `item_id` is now a top-level optional field (no longer in dict)
- Smart prefix selection (pocket vs article based on pocket_data presence)
- Validation: alphanumeric + underscore/hyphen only, max 255 chars

### 2. Save Article

**Legacy:**
```bash
POST /firebase/save
{
  "url": "https://example.com/article",
  "archiver": "all",
  "metadata": {"title": "Article"}
}
```

**New:**
```bash
POST /api/v1/firebase/add-article
{
  "url": "https://example.com/article",
  "item_id": "optional_custom_id",           # ✅ Optional custom ID
  "archiver": "all",
  "metadata": {"title": "Article"}
}
```

**Changes:**
- Consolidates with add-pocket-article into single endpoint
- Supports optional custom item_id
- Auto-generates article_{hash} if no item_id provided

### 3. Archive Article

**Legacy:**
```bash
POST /firebase/archive
{
  "item_id": "article123",
  "url": "https://example.com/article",
  "archiver": "all"
}
```

**New:**
```bash
POST /api/v1/firebase/archive
{
  "item_id": "article123",
  "url": "https://example.com/article",
  "archiver": "all"
}
```

**Changes:**
- Minimal (structure is same)
- Better validation on item_id format
- Uses Celery workers instead of in-process tasks

### 4. Download

**Legacy:**
```bash
GET /firebase/download/{item_id}/{archiver}
```

**New:**
```bash
GET /api/v1/firebase/download/{item_id}/{archiver}
```

**Changes:**
- Path structure unchanged
- Same response format
- Uses api-gateway rate limiting

## Migration Checklist

- [ ] Update client code to use new endpoint paths
- [ ] Move `item_id` from dict to top-level field (if applicable)
- [ ] Add error handling for 400 validation errors
- [ ] Test with custom item_ids
- [ ] Monitor deprecation warning logs
- [ ] Deploy updated clients before v2.0.0 release

## Backward Compatibility

During deprecation period (until v2.0.0):
- ✅ Both old and new endpoints work
- ✅ Old endpoints log deprecation warnings
- ✅ Both write to same PostgreSQL database
- ⚠️ Do not mix endpoints for same article (may cause conflicts)

## Need Help?

- API docs: `/docs` (FastAPI interactive docs)
- Issues: [GitHub repo issues](https://github.com)
- Migration support: Check application logs for deprecation warnings
