# Codebase Mapper Research Report

**Date**: 2026-01-16
**Feature**: API Endpoint Simplification
**Component Type**: API endpoints
**Search Scope**: Repository-wide

## Executive Summary

Analysis of 28 HTBase API endpoints reveals 4 client types and 3 deprecated endpoints marked for v2.0.0 removal.

**Key Findings**:
- 3 deprecated Firebase endpoints (/firebase/add-pocket-article, /firebase/save, /firebase/archive)
- 4 client types: Frontend React, Cloud Functions, Examples, Tests
- Migration path documented and partially implemented
- Microservices architecture (api-gateway) is production-ready
- Low breaking change risk except for Cloud Function

**Risk Hotspots**:
- HIGH: Firebase Cloud Function uses deprecated /firebase/archive endpoint
- LOW: Frontend uses non-deprecated /api/save/ endpoints

## 1. Client Code Found

### Client 1: React Frontend (TypeScript)

**Location**: C:\Users\jayte\Documents\dev\hbase\frontend\src\api\

**Files**:
- client.ts:3-9 - Axios HTTP client with base URL config
- saves.ts:8-43 - Archive operations (getSaves, getArchivers, runArchiver)

**Base URL Config**:
```typescript
const envBaseURL = import.meta.env.VITE_API_BASE_URL
const baseURL = envBaseURL ?? '/api'
```

**Endpoints Used**:
| Endpoint | Method | File:Line | Breaking? |
|----------|--------|-----------|-----------|
| /saves | GET | saves.ts:8 | No |
| /archivers | GET | saves.ts:18 | No |
| /save | POST | saves.ts:35 | No |
| /archive/{archiver} | POST | saves.ts:38 | No |

**Risk**: LOW - Uses core endpoints, not deprecated

### Client 2: Firebase Cloud Function (Node.js)

**Location**: C:\Users\jayte\Documents\dev\hbase\functions\index.js

**Endpoint Used**:
| Endpoint | Method | Line | Breaking? |
|----------|--------|------|-----------|
| /firebase/archive | POST | 97 | YES |

**Code**:
```javascript
const htbaseUrl = process.env.HTBASE_URL || 'http://localhost:8080';
const response = await axios.post(`${htbaseUrl}/firebase/archive`, {
  item_id: itemId,
  url: userArticle.url,
  archiver: userArticle.archiver || 'all'
});
```

**Risk**: HIGH - Production service using deprecated endpoint

**Migration Required**:
```javascript
// Change from:
`${htbaseUrl}/firebase/archive`
// To:
`${htbaseUrl}/api/v1/firebase/archive`
```

### Client 3: Example Code

**Files**:
- examples/python/simple_archive.py:36
- examples/javascript/simple_archive.js:28
- examples/curl/basic_examples.sh:20

**Endpoints**: /api/save/{archiver}, /api/batch/{archiver}, /api/retrieve

**Risk**: LOW - Uses core endpoints

### Client 4: Integration Tests

**Files**:
- tests/integration/test_api.py - Core functionality
- tests/integration/test_api_deprecation.py - Deprecation markers
- tests/e2e/test_end_to_end.py - Full workflow

**Risk**: LOW - Deprecation tests will be removed with endpoints

## 2. Deprecated Endpoints

### Three Endpoints Marked for Removal

| Endpoint | File:Line | Status | Replacement |
|----------|-----------|--------|-------------|
| /firebase/add-pocket-article | firebase.py:69 | Deprecated | /api/v1/firebase/add-article |
| /firebase/save | firebase.py:331 | Deprecated | /api/v1/firebase/add-article |
| /firebase/archive | firebase.py:415 | Deprecated | /api/v1/firebase/archive |

**Deprecation Pattern**:
```python
@router.post("/add-pocket-article", deprecated=True)
async def add_pocket_article(...):
    """
    **DEPRECATED:** Use /api/v1/firebase/add-article instead.
    This endpoint will be removed in v2.0.0.
    """
    logger.warning("DEPRECATED: /firebase/add-pocket-article called")
```

## 3. Integration Points

### Database Access

**Monolith**: SQLite via repository pattern (app/db/repository.py)
**Microservices**: PostgreSQL via SQLAlchemy (shared/db/)

**Tables**:
- archived_urls - Main records with item_id
- archive_artifacts - Archiver outputs
- url_metadata - Extracted metadata

### Cloud Storage

**GCS Integration** (services/api-gateway/app/routes/firebase.py:240-251):
```python
from shared.storage.gcs_file_storage import GCSFileStorage
signed_url = gcs.generate_access_url(storage_path, expiration)
```

### Firestore Sync

**Best-effort sync** from PostgreSQL to Firestore when enabled

## 4. Configuration

### Environment Variables

**Frontend**: VITE_API_BASE_URL
**Cloud Function**: HTBASE_URL, SYNC_TO_POSTGRES
**Backend**: SKIP_EXISTING_SAVES, DATABASE_URL, GCS_BUCKET, FIRESTORE_PROJECT_ID

## 5. Risk Assessment

### HIGH: Cloud Function Migration

**Risk**: Production Cloud Function uses deprecated /firebase/archive

**Mitigation**:
1. Update functions/index.js:97 before v2.0.0
2. Deploy updated function
3. Test in staging
4. Monitor for errors

### MEDIUM: External API Consumers

**Risk**: Unknown external services may call deprecated endpoints

**Mitigation**:
1. Monitor deprecation logs
2. Track calling IPs
3. Maintain 6-month deprecation period

### LOW: Frontend and Examples

**Risk**: Minimal - use non-deprecated endpoints

## 6. Migration Path

### Phase 1: Preparation (Complete)
- Mark endpoints deprecated
- Create migration guide
- Build replacement endpoints

### Phase 2: Client Migration (In Progress)
- Update Firebase Cloud Function
- Monitor deprecation warnings
- Contact external consumers

### Phase 3: Removal (v2.0.0)
- Remove deprecated endpoints
- Remove deprecation tests
- Update documentation

## 7. Test Coverage

**Existing**: tests/integration/test_api_deprecation.py
- 4 tests verify deprecation markers
- All passing (4/4)

**Needed**:
- Test /api/v1/firebase/add-article with custom item_id
- Test item_id validation
- Test URL uniqueness

## 8. Documentation

**Existing**:
- README.md:10-24 - Deprecation notice
- docs/FIREBASE_API_MIGRATION.md - Migration guide
- DEPRECATION_VERIFICATION.md - Verification report

**Needed**:
- v2.0.0 release notes
- Updated examples
- Architecture diagram updates

## 9. Recommendations

### Immediate (Week 1)
1. Update Firebase Cloud Function endpoint URL
2. Set up deprecation monitoring
3. Email known API consumers

### Short-term (Month 1-3)
4. Add missing tests
5. Update documentation
6. Track migration progress

### Long-term (Month 4-6)
7. Prepare v2.0.0 release
8. Remove deprecated code

## 10. Comparison: Legacy vs New

**Legacy** (DEPRECATED):
```bash
POST /firebase/add-pocket-article
{
  "pocket_data": {"item_id": "123abc"}  # item_id IGNORED
}
# Result: item_id = "pocket_<hash>"
```

**New** (CORRECT):
```bash
POST /api/v1/firebase/add-article
{
  "item_id": "123abc"  # Top-level field
}
# Result: item_id = "123abc"
```

## Conclusion

**Status**: Well-executed deprecation in progress

**Critical Action**: Update Firebase Cloud Function before v2.0.0

**Overall Risk**: MEDIUM (Cloud Function migration required)

---

**Files Analyzed**: 25
**Search Duration**: 15 minutes
**Report Generated**: 2026-01-16
