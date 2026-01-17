# Migration Guide: PostgreSQL + Local Storage → Firestore + GCS

**Migration Date:** 2026-01-17
**Breaking Change:** Yes - Complete architecture change

---

## Overview

HTBase has migrated from a dual-database (PostgreSQL + Firestore) and dual-storage (Local + GCS) architecture to a simplified **Firestore-only + GCS-only** architecture.

### What Changed

**Removed:**
- PostgreSQL database (all tables, migrations, connection pooling)
- Local file storage (`/app/artifacts`, `ARTIFACTS_PATH`)
- `storage-worker` service (async upload worker)
- `sync-worker` service (PostgreSQL → Firestore backfill)
- Database abstraction layers (~4,000 lines of code)

**New Architecture:**
- Firestore as the sole database
- GCS as the sole storage backend
- Direct synchronous uploads (no worker queue)
- Temporary files during archiving (auto-cleanup)

**Benefits:**
- ~3,400 lines of code removed (40% reduction in shared/)
- Simpler deployment (no PostgreSQL to manage)
- Fewer services (2 services removed)
- No dual-write complexity
- No storage sync issues

---

## Environment Variable Changes

### Variables to REMOVE

Delete these from your `.env` files:

```bash
# PostgreSQL (no longer supported)
DATABASE_URL
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
DB_POOL_SIZE
DB_MAX_OVERFLOW
DB_SOCKET
DATABASE__HOST  # Nested format
DATABASE__PORT
DATABASE__NAME
DATABASE__USER
DATABASE__PASSWORD

# Local storage (removed)
STORAGE_BACKEND
STORAGE_PROVIDER
STORAGE_PROVIDERS
ARTIFACTS_PATH
LOCAL_STORAGE_PATH
COMPRESSION_ENABLED
CLEANUP_AFTER_UPLOAD
ENABLE_LOCAL_CLEANUP
LOCAL_WORKSPACE_RETENTION_HOURS
STORAGE_CONCURRENCY
ENABLE_STORAGE_INTEGRATION
DATABASE_BACKEND
```

### Variables to ADD/UPDATE

Add or update these variables:

```bash
# Database (Firestore - REQUIRED)
FIRESTORE_PROJECT_ID=your-gcp-project-id
FIRESTORE_COLLECTION=articles  # Optional, defaults to "articles"

# Storage (GCS - REQUIRED)
GCS_BUCKET=your-bucket-name
GCS_PROJECT_ID=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

---

## Docker Compose Changes

### Services Removed

Remove these services from `docker-compose.yml`:

```yaml
# DELETE THESE:
storage-worker:
  # ... entire service definition

sync-worker:
  # ... entire service definition
```

### Volume Changes

Remove the `artifacts` volume:

```yaml
# BEFORE:
volumes:
  redis-data:
    driver: local
  artifacts:      # DELETE THIS
    driver: local
  flower-data:
    driver: local

# AFTER:
volumes:
  redis-data:
    driver: local
  flower-data:
    driver: local
```

### Environment Variable Updates

Update the `x-common-env` anchor:

```yaml
# BEFORE:
x-common-env: &common-env
  DATABASE_URL: postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}
  GCS_BUCKET: ${GCS_BUCKET}
  # ...

# AFTER:
x-common-env: &common-env
  FIRESTORE_PROJECT_ID: ${GCS_PROJECT_ID}
  GCS_BUCKET: ${GCS_BUCKET}
  GCS_PROJECT_ID: ${GCS_PROJECT_ID}
  GOOGLE_APPLICATION_CREDENTIALS: /secrets/gcs-credentials.json
  # ...
```

---

## Migration Steps

### Step 1: Backup Existing Data

**If you have data in PostgreSQL that you want to keep:**

```bash
# Export PostgreSQL data
pg_dump -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} > htbase_backup_$(date +%Y%m%d).sql

# Or use the existing sync-worker to backfill Firestore
docker compose run sync-worker python -m app.tasks.backfill_firestore
```

**Note:** If you were already using Firestore for mobile sync, your data should already be in Firestore.

### Step 2: Update Code

Pull the latest code:

```bash
git pull origin main
# Or checkout the specific release tag
git checkout v2.0.0  # Replace with actual version
```

### Step 3: Update Environment Files

1. Update `.env`:
   ```bash
   # Remove PostgreSQL variables
   # Remove local storage variables
   # Add Firestore and GCS variables (see above)
   ```

2. Update `.env.microservices` or production env files:
   ```bash
   # Follow the same pattern
   ```

### Step 4: Update Dependencies

```bash
# Remove old packages
pip uninstall sqlalchemy psycopg alembic

# Install new packages (or rebuild Docker images)
pip install google-cloud-firestore
```

**For Docker deployments:**
```bash
# Rebuild images with new requirements.txt
docker compose build
```

### Step 5: Update Docker Compose

1. Remove `storage-worker` service
2. Remove `sync-worker` service
3. Remove `artifacts` volume
4. Update environment variables in `x-common-env`

### Step 6: Verify GCS Credentials

Ensure your service account has the correct permissions:

```bash
# Test GCS access
docker compose run api-gateway python -c "
from google.cloud import storage
client = storage.Client(project='your-project-id')
bucket = client.bucket('your-bucket-name')
print(f'Bucket exists: {bucket.exists()}')
"

# Test Firestore access
docker compose run api-gateway python -c "
from google.cloud import firestore
client = firestore.Client(project='your-project-id')
print(f'Collections: {list(client.collections())}')
"
```

### Step 7: Deploy

```bash
# Stop old services
docker compose down

# Start new services
docker compose up -d

# Check logs
docker compose logs -f api-gateway
docker compose logs -f archive-worker-singlefile
```

### Step 8: Verify Operations

1. **Test archive creation:**
   ```bash
   curl -X POST http://localhost:8080/archives \
     -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{
       "items": [{
         "id": "test123",
         "url": "https://example.com"
       }],
       "archivers": ["readability"]
     }'
   ```

2. **Check Firestore:**
   - Open Firebase Console
   - Navigate to Firestore Database
   - Verify `articles` collection has new documents

3. **Check GCS:**
   - Open GCS Console
   - Navigate to your bucket
   - Verify artifacts are being uploaded to `archives/{item_id}/{archiver}/output.{ext}`

---

## Rollback Procedure

If migration fails, you can rollback:

### Option 1: Git Revert

```bash
# Revert to previous version
git checkout previous-tag  # e.g., v1.9.0

# Restore old environment files
cp .env.backup .env

# Rebuild and redeploy
docker compose down
docker compose build
docker compose up -d
```

### Option 2: Restore PostgreSQL Backup

```bash
# Restore database from backup
psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} < htbase_backup_20260117.sql

# Redeploy old version
docker compose down
docker compose up -d
```

---

## Common Issues

### Issue: "Firestore client not configured"

**Cause:** Missing `FIRESTORE_PROJECT_ID` or `GOOGLE_APPLICATION_CREDENTIALS`

**Fix:**
```bash
# Check environment variables
docker compose exec api-gateway env | grep -E "FIRESTORE|GOOGLE"

# Ensure service account JSON is mounted
docker compose exec api-gateway ls -la /secrets/gcs-credentials.json
```

---

### Issue: "GCS upload failed"

**Cause:** Service account lacks permissions or bucket doesn't exist

**Fix:**
```bash
# Verify service account permissions
gcloud projects get-iam-policy your-project-id \
  --flatten="bindings[].members" \
  --format="table(bindings.role)" \
  --filter="bindings.members:serviceAccount:your-service-account@your-project-id.iam.gserviceaccount.com"

# Should have:
# - roles/storage.objectCreator (or roles/storage.admin)
# - roles/datastore.user (for Firestore)

# Create bucket if missing
gsutil mb gs://your-bucket-name
```

---

### Issue: "No data in Firestore"

**Cause:** Data is still in PostgreSQL, not migrated

**Fix:**
```bash
# Use the old sync-worker (before deleting it) to backfill
# This is only possible if you haven't deleted the sync-worker yet
docker compose -f docker-compose.old.yml run sync-worker \
  python -m app.tasks.backfill_firestore

# Or manually create test data
curl -X POST http://localhost:8080/archives \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{"id": "test1", "url": "https://example.com"}],
    "archivers": ["readability"]
  }'
```

---

### Issue: "Temp file permission denied"

**Cause:** Docker container can't write to `/tmp`

**Fix:**
```bash
# Check temp directory permissions
docker compose exec archive-worker-singlefile ls -la /tmp

# If needed, update Dockerfile to ensure /tmp is writable
# Usually this should work by default
```

---

## Performance Comparison

### Before (PostgreSQL + Local Storage)

- **Archive Write:** PostgreSQL INSERT + Local file write + Async GCS upload
- **Latency:** ~500ms (database) + ~2s (GCS upload, async)
- **Storage:** Local disk + GCS (dual storage)
- **Services:** 7 services (gateway, 5 workers, storage-worker)

### After (Firestore + GCS)

- **Archive Write:** Firestore write + Temp file + Sync GCS upload
- **Latency:** ~200ms (Firestore) + ~2s (GCS upload, sync)
- **Storage:** GCS only (temp files auto-deleted)
- **Services:** 6 services (gateway, 5 workers)

**Trade-offs:**
- ✅ Simpler architecture
- ✅ No sync lag between database and storage
- ✅ Fewer moving parts
- ⚠️ Slightly higher archiving latency (sync upload vs async)
- ⚠️ GCS required (no local-only option)

---

## Frequently Asked Questions

### Can I still use local storage?

**No.** Local storage has been completely removed. GCS is now required for all deployments.

**Workaround for development:** Use GCS Emulator:
```bash
# Run GCS emulator locally
docker run -p 4443:4443 fsouza/fake-gcs-server -scheme http

# Point to emulator
export GCS_ENDPOINT=http://localhost:4443
```

---

### Can I migrate back to PostgreSQL later?

**Technically yes, but not recommended.** The PostgreSQL code has been removed from the codebase. You would need to:

1. Checkout an old version
2. Export Firestore data
3. Import into PostgreSQL
4. Deal with schema differences

This is not officially supported.

---

### What happens to my existing GCS files?

**Nothing.** Existing GCS files remain unchanged. The new code uses the same GCS path structure:

```
gs://your-bucket/archives/{item_id}/{archiver}/output.{ext}
```

Files uploaded with the old system are fully compatible.

---

### Do I need to change my API clients?

**No.** The API endpoints remain the same. Only the backend storage has changed.

```bash
# This still works the same
POST /archives
GET /archives/{item_id}
GET /archives/{item_id}/download
```

---

## Support

**Issues:**
- GitHub: https://github.com/yourusername/htbase/issues

**Documentation:**
- [Environment Variables](./ENVIRONMENT_VARIABLES.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Architecture Overview](./ARCHITECTURE_OVERVIEW.md)

---

## Changelog

**2026-01-17 - v2.0.0**
- ❌ REMOVED: PostgreSQL database support
- ❌ REMOVED: Local file storage
- ❌ REMOVED: storage-worker service
- ❌ REMOVED: sync-worker service
- ✅ ADDED: Firestore as sole database
- ✅ ADDED: GCS-only storage with temp files
- 📦 CHANGED: ~3,400 lines of code removed
- 📦 CHANGED: Simplified deployment
