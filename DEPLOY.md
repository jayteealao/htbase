# HTBase Docker Compose Deployment Guide

Deploy HTBase using the pre-built GHCR image with Traefik reverse proxy.

## Prerequisites

- Docker and Docker Compose installed
- Traefik reverse proxy running with network `traefik-proxy`
- Firebase/GCP credentials JSON file
- PostgreSQL database accessible from Docker host

## Quick Start

### 1. Prepare Credentials

Place your Firebase/GCP credentials JSON file in the project directory:

```bash
# Download from Google Cloud Console
# IAM & Admin > Service Accounts > Keys
cp /path/to/your-credentials.json ./firebase-credentials.json
chmod 600 ./firebase-credentials.json
```

### 2. Create Data Directory

```bash
mkdir -p ./data
chmod 755 ./data
```

### 3. Configure Environment

Edit `compose.yml` and update:
- `DB_PASSWORD` - Your PostgreSQL password
- Traefik labels - Replace `htbase.yourdomain.com` with your actual domain
- Paths to credentials file if different

### 4. Deploy

```bash
# Start the service
docker compose -f compose.yml up -d

# Check logs
docker compose -f compose.yml logs -f htbase

# Check health
curl https://htbase.yourdomain.com/health
```

## Configuration Reference

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `postgres.archivist.lol` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `postgres` |
| `DB_USER` | Database user | `archivist` |
| `DB_PASSWORD` | Database password | `your_password` |

### Storage Configuration

#### Local Storage (Default)
```yaml
STORAGE_BACKEND: local
STORAGE_PROVIDERS: local
```

#### GCS Storage
```yaml
STORAGE_BACKEND: gcs
STORAGE_PROVIDERS: gcs
GCS_BUCKET: htbase-archives-standard
GCS_PROJECT_ID: trails-414917
```

#### Dual Persistence (GCS + Firestore)
```yaml
STORAGE_BACKEND: gcs
STORAGE_PROVIDERS: gcs
ENABLE_DUAL_PERSISTENCE: "true"
FIRESTORE_PROJECT_ID: trails-414917
```

### Traefik Labels

The compose file includes Traefik labels for automatic routing:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.htbase.rule=Host(`htbase.yourdomain.com`)"
  - "traefik.http.routers.htbase.entrypoints=websecure"
  - "traefik.http.routers.htbase.tls=true"
  - "traefik.http.routers.htbase.tls.certresolver=letsencrypt"
  - "traefik.http.services.htbase.loadbalancer.server.port=8080"
```

**Update:**
- Replace `htbase.yourdomain.com` with your domain
- Ensure `letsencrypt` certresolver is configured in your Traefik
- Adjust `entrypoints` if using different entry point name

## Volume Mounts

### Data Directory (`/data`)
```yaml
volumes:
  - ./data:/data
```

Local storage for archived files when using `STORAGE_BACKEND=local`.

### Firebase Credentials
```yaml
volumes:
  - ./firebase-credentials.json:/app/credentials/firebase-credentials.json:ro
```

**Important:** Mount as read-only (`:ro`) for security.

## Networking

The service connects to the external Traefik network:

```yaml
networks:
  traefik-proxy:
    external: true
```

**Ensure your Traefik network exists:**
```bash
docker network ls | grep traefik-proxy

# If not, create it:
docker network create traefik-proxy
```

## Health Check

Container includes a health check:
- **Endpoint:** `http://localhost:8080/health`
- **Interval:** 30 seconds
- **Timeout:** 10 seconds
- **Start period:** 40 seconds (for migrations)

Check health:
```bash
docker inspect htbase | grep -A 10 Health
```

## Database Migrations

Migrations run automatically on container startup via `entrypoint.sh`.

**Migration logs:**
```bash
docker compose logs htbase | grep migration
```

**Expected output:**
```
[entrypoint] Applying DB migrations...
[entrypoint] Migration attempt 1 of 3...
[entrypoint] ✓ Migrations complete.
[entrypoint] Starting uvicorn...
```

## Troubleshooting

### Container Fails to Start

**Check logs:**
```bash
docker compose logs htbase
```

**Common issues:**

1. **Database connection failure:**
   ```
   [entrypoint] ✗ TCP connection failed - cannot reach postgres.archivist.lol:5432
   ```
   - Verify DB_HOST, DB_PORT, DB_USER, DB_PASSWORD
   - Check database server allows connections from Docker host
   - Test connection: `telnet postgres.archivist.lol 5432`

2. **Missing credentials:**
   ```
   FileNotFoundError: /app/credentials/firebase-credentials.json
   ```
   - Ensure credentials file exists at specified path
   - Check volume mount in compose.yml

3. **GCS permission errors:**
   ```
   google.api_core.exceptions.Forbidden: 403 Access denied
   ```
   - Verify service account has Storage Object Admin role
   - Check GCS_BUCKET exists and is accessible

### Traefik Routing Issues

**Service not accessible:**
```bash
# Check Traefik dashboard for router/service
# Verify domain DNS points to Traefik host

# Test internal access (bypassing Traefik)
docker exec htbase curl http://localhost:8080/health
```

**Common fixes:**
- Ensure `traefik-proxy` network is connected
- Verify domain in Traefik router rule matches DNS
- Check Traefik logs for certificate errors

### Performance Issues

**Check resource usage:**
```bash
docker stats htbase
```

**Increase resources if needed:**
```yaml
services:
  htbase:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

## Updating

### Pull New Image

```bash
# Pull latest image for tag
docker pull ghcr.io/jayteealao/htbase:sha-28df369

# Recreate container
docker compose up -d --force-recreate
```

### Change Image Tag

Edit `compose.yml`:
```yaml
services:
  htbase:
    image: ghcr.io/jayteealao/htbase:sha-<new-commit>
```

Then:
```bash
docker compose up -d
```

## Security Considerations

1. **Credentials:** Mount credentials as read-only (`:ro`)
2. **Environment variables:** Consider using Docker secrets for sensitive data
3. **Network:** Use internal networks when possible
4. **Firewall:** Restrict database access to trusted IPs
5. **Updates:** Regularly update to latest image tags

## Backup

### Database
```bash
# Backup PostgreSQL
docker exec postgres pg_dump -U archivist postgres > backup.sql
```

### Data Directory (if using local storage)
```bash
# Backup /data
tar -czf data-backup-$(date +%Y%m%d).tar.gz ./data
```

### GCS (if using cloud storage)
Data is stored in GCS bucket - configure GCS lifecycle policies for backup/retention.

## Monitoring

### Logs
```bash
# Follow logs
docker compose logs -f htbase

# Last 100 lines
docker compose logs --tail=100 htbase
```

### Metrics
Consider integrating with:
- Prometheus (application metrics)
- Grafana (visualization)
- Loki (log aggregation)

## Support

- **Documentation:** See `CLAUDE.md` for architecture details
- **Issues:** Report at GitHub repository
- **Logs:** Include container logs when reporting issues
