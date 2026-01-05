# HTBase Deployment with Existing Traefik Stack

Deploy HTBase alongside your existing docker-compose.yml infrastructure.

## File Naming Convention

Since you already have `docker-compose.yml`, the HTBase service is in:
- **`docker-compose.htbase.yml`** - Service-specific compose file

## Deployment Methods

### Method 1: Run Separately (Recommended)

Deploy HTBase independently while sharing the same Docker network:

```bash
# Deploy main stack (if not already running)
docker compose up -d

# Deploy HTBase
docker compose -f docker-compose.htbase.yml up -d

# Check logs
docker compose -f docker-compose.htbase.yml logs -f htbase

# Stop HTBase
docker compose -f docker-compose.htbase.yml down
```

### Method 2: Run Together

Manage both stacks with a single command:

```bash
# Start everything
docker compose -f docker-compose.yml -f docker-compose.htbase.yml up -d

# View all logs
docker compose -f docker-compose.yml -f docker-compose.htbase.yml logs -f

# Stop everything
docker compose -f docker-compose.yml -f docker-compose.htbase.yml down
```

### Method 3: Add to Main File (Alternative)

You can also add the htbase service directly to your existing `docker-compose.yml`:

```yaml
# Add to your docker-compose.yml services section
services:
  # ... your existing services ...

  htbase:
    image: ghcr.io/jayteealao/htbase:sha-28df369
    container_name: htbase
    # ... rest of configuration from docker-compose.htbase.yml
```

## Pre-Deployment Setup

### 1. Place Firebase Credentials

```bash
# On your server (~/archivebox directory)
cd ~/archivebox

# Upload your Firebase credentials JSON
# Replace with your actual credentials file
scp firebase-credentials.json archivist@vmi2260613:~/archivebox/
```

### 2. Create Data Directory

```bash
cd ~/archivebox
mkdir -p data
chmod 755 data
```

### 3. Verify Network

HTBase connects to the same network as your existing services:

```bash
# Check network name (should be archivebox_default)
docker network ls | grep archivebox

# If network doesn't exist, create it:
docker network create archivebox_default
```

## Configuration

The HTBase compose file is already configured for your environment:

✅ **Database**: Uses your existing `postgres` service
✅ **Traefik**: Uses `myresolver` certresolver
✅ **Domain**: `htbase.archivist.lol`
✅ **CrowdSec**: Configured with your bouncer API key
✅ **Network**: Connects to `archivebox_default`

### Environment Variables

All environment variables are pre-configured in `docker-compose.htbase.yml`:

| Variable | Value | Notes |
|----------|-------|-------|
| DB_HOST | `postgres` | Your existing PostgreSQL container |
| DB_PASSWORD | `ed83e2f93719` | Matches your postgres password |
| STORAGE_BACKEND | `gcs` | Using Google Cloud Storage |
| GCS_BUCKET | `htbase-archives-standard` | Your GCS bucket |
| FIRESTORE_PROJECT_ID | `trails-414917` | Your Firestore project |

### Update Domain (if needed)

If you want a different subdomain, edit `docker-compose.htbase.yml`:

```yaml
labels:
  - "traefik.http.routers.htbase.rule=Host(`archive.archivist.lol`)"  # Change subdomain here
```

## Deployment

### Deploy on Server

```bash
# SSH to your server
ssh archivist@vmi2260613

# Navigate to directory
cd ~/archivebox

# Upload HTBase compose file
# (From your local machine)
scp docker-compose.htbase.yml archivist@vmi2260613:~/archivebox/

# Deploy HTBase
docker compose -f docker-compose.htbase.yml up -d

# Check startup logs
docker compose -f docker-compose.htbase.yml logs -f htbase
```

### Expected Startup Logs

```
=== Container Startup Diagnostics ===
[entrypoint] Current directory: /app
[entrypoint] Python version: Python 3.11.x
[entrypoint] Alembic version: 1.x.x

[entrypoint] Database Configuration:
  DB_HOST: postgres
  DB_PORT: 5432
  DB_NAME: postgres
  DB_USER: archivist
  DB_PASSWORD: <set (12 chars)>

[entrypoint] Testing database connectivity...
[entrypoint] Attempting connection to postgres:5432...
[entrypoint] ✓ TCP connection successful

[entrypoint] Applying DB migrations...
[entrypoint] Migration attempt 1 of 3...
[entrypoint] ✓ Migrations complete.

[entrypoint] Starting uvicorn...
[entrypoint] Listening on 0.0.0.0:8080
```

## Access HTBase

Once deployed, HTBase will be available at:

**https://htbase.archivist.lol**

Protected by:
- ✅ HTTPS via Let's Encrypt (Traefik `myresolver`)
- ✅ CrowdSec security bouncer
- ✅ Automatic HTTP → HTTPS redirect

### Test API

```bash
# Health check
curl https://htbase.archivist.lol/health

# Save a URL (example)
curl -X POST https://htbase.archivist.lol/save/monolith \
  -H 'Content-Type: application/json' \
  -d '{"id":"test123","url":"https://example.com"}'
```

## Monitoring

### View Logs

```bash
# Follow HTBase logs
docker compose -f docker-compose.htbase.yml logs -f htbase

# Last 100 lines
docker compose -f docker-compose.htbase.yml logs --tail=100 htbase

# Filter for errors
docker compose -f docker-compose.htbase.yml logs htbase | grep ERROR
```

### Check Health

```bash
# Container health
docker inspect htbase | grep -A 10 Health

# Service status
docker compose -f docker-compose.htbase.yml ps
```

### Traefik Dashboard

HTBase will appear in your Traefik dashboard:
- **Dashboard**: https://traefik.archivist.lol/dashboard/
- Check routers: Look for `htbase` router
- Check services: Look for `htbase-htbase@docker` service

### Resource Usage

```bash
# Monitor resources
docker stats htbase

# Check disk usage
du -sh ~/archivebox/data
```

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker compose -f docker-compose.htbase.yml logs htbase
```

**Common issues:**

1. **Database connection failed**
   ```
   [entrypoint] ✗ TCP connection failed - cannot reach postgres:5432
   ```
   - Ensure postgres container is running: `docker ps | grep postgres`
   - Check network: `docker network inspect archivebox_default`

2. **Missing credentials file**
   ```
   FileNotFoundError: /app/credentials/firebase-credentials.json
   ```
   - Verify file exists: `ls -la ~/archivebox/firebase-credentials.json`
   - Check mount in docker-compose.htbase.yml

3. **GCS permissions error**
   ```
   google.api_core.exceptions.Forbidden: 403
   ```
   - Verify service account has Storage Object Admin role
   - Check bucket exists: `gsutil ls gs://htbase-archives-standard`

### Can't Access via Traefik

**Check domain DNS:**
```bash
# Ensure htbase.archivist.lol points to your server
dig htbase.archivist.lol +short
# Should return: your-server-ip
```

**Check Traefik routing:**
```bash
# View Traefik logs
docker logs traefik | grep htbase

# Test internal access (bypassing Traefik)
docker exec htbase curl http://localhost:8080/health
```

**Verify network connection:**
```bash
# HTBase should be on archivebox_default network
docker inspect htbase | grep NetworkMode
```

## Updates

### Update to New Image

```bash
cd ~/archivebox

# Edit docker-compose.htbase.yml to change image tag:
# image: ghcr.io/jayteealao/htbase:sha-<new-commit>

# Pull new image
docker compose -f docker-compose.htbase.yml pull

# Recreate container
docker compose -f docker-compose.htbase.yml up -d
```

### View Available Tags

```bash
# List available tags from GHCR
# (requires authentication)
docker search ghcr.io/jayteealao/htbase
```

## Integration with Existing Services

HTBase integrates seamlessly with your stack:

| Service | Integration | Details |
|---------|-------------|---------|
| **Traefik** | Reverse proxy | Automatic routing, TLS, HTTP→HTTPS |
| **PostgreSQL** | Database | Shared postgres service |
| **CrowdSec** | Security | Bouncer protection enabled |
| **Prometheus** | Monitoring | Can add HTBase metrics endpoint |
| **Grafana** | Dashboards | Can visualize HTBase metrics |

### Optional: Add to Prometheus

Add HTBase metrics to your Prometheus config:

```yaml
# In dockprom/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'htbase'
    static_configs:
      - targets: ['htbase:8080']
```

## Backup

### Database Backup

HTBase uses your existing PostgreSQL, so normal backup applies:

```bash
# Backup entire postgres database
docker exec postgres pg_dump -U archivist postgres > htbase-backup.sql
```

### Data Directory

```bash
# Backup local data (if using local storage)
cd ~/archivebox
tar -czf htbase-data-backup-$(date +%Y%m%d).tar.gz ./data
```

### GCS Data

Data in GCS is automatically backed up by Google Cloud. Consider:
- **Lifecycle policies** for automatic archival
- **Versioning** for file recovery
- **Regional backup** for disaster recovery

## Security Notes

1. ✅ **Credentials mounted read-only** (`:ro`)
2. ✅ **CrowdSec protection** enabled
3. ✅ **HTTPS only** (HTTP redirects to HTTPS)
4. ✅ **Shared network** (not exposed to public internet)
5. ⚠️ **Consider adding auth** if needed:
   ```yaml
   - "traefik.http.routers.htbase.middlewares=auth,crowdsec-htbase@docker"
   # Uses your existing BasicAuth middleware
   ```

## Clean Up

### Stop HTBase

```bash
# Stop container
docker compose -f docker-compose.htbase.yml down

# Stop and remove volumes
docker compose -f docker-compose.htbase.yml down -v
```

### Complete Removal

```bash
# Remove container and data
docker compose -f docker-compose.htbase.yml down -v
rm -rf ~/archivebox/data
rm ~/archivebox/docker-compose.htbase.yml
rm ~/archivebox/firebase-credentials.json
```

## Support

- **Logs**: Check `docker-compose.htbase.yml logs`
- **Health**: Monitor via Traefik dashboard
- **Metrics**: View in Grafana (if configured)
- **Database**: Access via pgweb at https://pgweb.archivist.lol
