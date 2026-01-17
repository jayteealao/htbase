# HTBase Environment Variables Reference

**Quick reference guide for all HTBase environment variables**

Last Updated: 2026-01-17

---

## Required Variables (Minimum Configuration)

These variables MUST be set for HTBase to run:

```bash
# Database (Firestore)
FIRESTORE_PROJECT_ID=your-gcp-project-id

# Storage (GCS - required, no local storage option)
GCS_BUCKET=your-bucket-name
GCS_PROJECT_ID=your-gcp-project-id
GOOGLE_APPLICATION_CREDENTIALS=./secrets/gcs-credentials.json

# Authentication
API_KEYS=htbase_live_key1,htbase_live_key2
```

**Note:** PostgreSQL is no longer supported. Firestore is the only database backend.

---

## All Variables by Category

### Core Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENVIRONMENT` | string | `production` | Environment name |
| `VERSION` | string | `latest` | Docker image version |
| `REGISTRY` | string | `` | Docker registry prefix |
| `LOG_LEVEL` | string | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | string | `json` | Log format (json/text) |

---

### Database Configuration (Firestore)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FIRESTORE_PROJECT_ID` | **REQUIRED** | - | Google Cloud project ID for Firestore |
| `FIRESTORE_COLLECTION` | string | `articles` | Firestore collection name |
| `GOOGLE_APPLICATION_CREDENTIALS` | **REQUIRED** | - | Path to GCP service account JSON |

**Notes:**
- PostgreSQL has been removed - Firestore is the only supported database
- Uses the same service account credentials as GCS
- No connection pooling needed - Firestore SDK handles this automatically

---

### Redis Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REDIS_HOST` | string | `redis` | Redis host |
| `REDIS_PORT` | int | `6379` | Redis port |
| `REDIS_DB` | int | `0` | Redis database number |
| `REDIS_PASSWORD` | string | - | Redis password (optional) |

**Derived (auto-set):**
- `REDIS_URL`: `redis://redis:6379/0`
- `CELERY_BROKER_URL`: `redis://redis:6379/0`
- `CELERY_RESULT_BACKEND`: `redis://redis:6379/1`

---

### API Gateway

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `API_PORT` | int | `8080` | API port |
| `API_WORKERS` | int | `4` | Uvicorn workers |
| `API_RATE_LIMIT` | string | `100/minute` | Rate limit |
| `CORS_ORIGINS` | string | `*` | CORS origins (comma-separated) |

---

### Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `API_KEYS` | **REQUIRED** | - | Comma-separated API keys |

**Format:** `htbase_live_{hex}` or `htbase_test_{hex}`

**Generate:**
```bash
openssl rand -hex 32
```

---

### Archiver Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEFAULT_ARCHIVERS` | string | `singlefile,monolith,readability,pdf,screenshot` | Default archivers |
| `SINGLEFILE_CONCURRENCY` | int | `2` | SingleFile workers |
| `MONOLITH_CONCURRENCY` | int | `3` | Monolith workers |
| `READABILITY_CONCURRENCY` | int | `5` | Readability workers |
| `PDF_CONCURRENCY` | int | `3` | PDF workers |
| `SCREENSHOT_CONCURRENCY` | int | `3` | Screenshot workers |

**Resource Usage:**
- SingleFile: ~1GB RAM per worker
- Monolith: ~1GB RAM per worker
- Readability: ~50MB RAM per worker
- PDF: ~500MB RAM per worker
- Screenshot: ~500MB RAM per worker

---

### Storage Configuration (GCS-Only)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GCS_BUCKET` | **REQUIRED** | - | GCS bucket name for artifacts |
| `GCS_PROJECT_ID` | **REQUIRED** | - | GCP project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | **REQUIRED** | - | Path to GCP service account JSON |

**Important Changes:**
- Local storage has been **removed** - GCS is the only supported storage backend
- No `storage-worker` service needed - uploads happen synchronously in archive workers
- Temporary files are used during archiving and deleted immediately after GCS upload
- No `COMPRESSION_ENABLED`, `CLEANUP_AFTER_UPLOAD`, or `ARTIFACTS_PATH` variables needed

**Alternative variable names (for compatibility):**
- `GOOGLE_CLOUD_PROJECT`: Alias for `GCS_PROJECT_ID`
- `GCS_CREDENTIALS_PATH`: Alias for `GOOGLE_APPLICATION_CREDENTIALS`

---

### Summarization (Optional)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_SUMMARIZATION` | bool | `true` | Enable summarization |
| `SUMMARIZATION_CONCURRENCY` | int | `5` | Summarization workers |
| `LLM_PROVIDER` | string | `huggingface` | LLM provider (huggingface/openai/mock) |
| `CHUNK_SIZE` | int | `4000` | Text chunk size |
| `CHUNK_OVERLAP` | int | `200` | Chunk overlap |

---

### HuggingFace Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HUGGINGFACE_API_URL` | **REQUIRED** (if using HF) | - | TGI endpoint URL |
| `HUGGINGFACE_API_KEY` | string | - | HuggingFace API key |

---

### OpenAI Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_KEY` | **REQUIRED** (if using OpenAI) | - | OpenAI API key |
| `OPENAI_MODEL` | string | `gpt-4o-mini` | OpenAI model name |

---

### Monitoring (Optional)

#### Flower (Celery Monitor)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLOWER_PORT` | int | `5555` | Flower UI port |
| `FLOWER_USER` | **REQUIRED** (if enabled) | `admin` | Basic auth username |
| `FLOWER_PASSWORD` | **REQUIRED** (if enabled) | - | Basic auth password |

#### Redis Commander

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REDIS_COMMANDER_PORT` | int | `8081` | Redis Commander port |
| `REDIS_COMMANDER_USER` | **REQUIRED** (if enabled) | `admin` | Basic auth username |
| `REDIS_COMMANDER_PASSWORD` | **REQUIRED** (if enabled) | - | Basic auth password |

---

### Reverse Proxy (Optional)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DOMAIN` | **REQUIRED** (if using Traefik) | `localhost` | Domain name |
| `ACME_EMAIL` | **REQUIRED** (if using Traefik) | `admin@example.com` | Let's Encrypt email |

---

## Configuration Examples

### Minimal (Development)

```bash
# Core
ENVIRONMENT=development
LOG_LEVEL=DEBUG
LOG_FORMAT=text

# Database (Firestore)
FIRESTORE_PROJECT_ID=my-dev-project
GOOGLE_APPLICATION_CREDENTIALS=./secrets/gcs-dev-credentials.json

# Storage (GCS - required)
GCS_BUCKET=htbase-dev-archives
GCS_PROJECT_ID=my-dev-project

# Authentication
API_KEYS=htbase_test_dev123

# Disable features
ENABLE_SUMMARIZATION=false
```

---

### Production

```bash
# Core
ENVIRONMENT=production
VERSION=latest
LOG_LEVEL=INFO
LOG_FORMAT=json

# Database (Firestore)
FIRESTORE_PROJECT_ID=my-production-project
FIRESTORE_COLLECTION=articles

# Storage (GCS)
GCS_BUCKET=htbase-production-archives
GCS_PROJECT_ID=my-production-project
GOOGLE_APPLICATION_CREDENTIALS=./secrets/gcs-credentials.json

# Authentication
API_KEYS=htbase_live_a1b2c3...,htbase_live_x7y8z9...

# API
API_PORT=8080
API_WORKERS=4
CORS_ORIGINS=https://app.htbase.com,https://htbase.com
API_RATE_LIMIT=100/minute

# Archivers
DEFAULT_ARCHIVERS=singlefile,monolith,readability,pdf,screenshot
SINGLEFILE_CONCURRENCY=3
MONOLITH_CONCURRENCY=3
READABILITY_CONCURRENCY=5
PDF_CONCURRENCY=3
SCREENSHOT_CONCURRENCY=3

# Summarization
ENABLE_SUMMARIZATION=true
LLM_PROVIDER=huggingface
HUGGINGFACE_API_URL=https://my-tgi-endpoint.com
SUMMARIZATION_CONCURRENCY=5
CHUNK_SIZE=4000
CHUNK_OVERLAP=200

# Monitoring
FLOWER_PORT=5555
FLOWER_USER=admin
FLOWER_PASSWORD=SecureFlowerPassword123!

REDIS_COMMANDER_PORT=8081
REDIS_COMMANDER_USER=admin
REDIS_COMMANDER_PASSWORD=SecureRedisCommanderPassword123!

# Reverse Proxy
DOMAIN=htbase.example.com
ACME_EMAIL=admin@example.com
```

---

## Environment Variable Precedence

HTBase uses Pydantic settings with the following precedence (highest to lowest):

1. **Environment variables** (e.g., `FIRESTORE_PROJECT_ID=my-project`)
2. **`.env` file** in project root
3. **Default values** in code

**Example:**
```bash
# Environment variable takes precedence over .env file
export GCS_BUCKET=production-bucket

# This value in .env will be ignored if env var is set
GCS_BUCKET=dev-bucket
```

---

## Validation Rules

### API Keys and Passwords

- **API_KEYS**: Comma-separated, no spaces
- **FLOWER_PASSWORD**: No restrictions
- **REDIS_COMMANDER_PASSWORD**: No restrictions

**Generate secure API keys:**
```bash
openssl rand -hex 32
```

**Generate secure passwords:**
```bash
openssl rand -base64 32
```

---

### Ports

- Must be valid port numbers (1-65535)
- Ensure no conflicts with other services

**Common ports:**
- `8080`: API Gateway
- `6379`: Redis
- `5555`: Flower
- `8081`: Redis Commander
- `80/443`: Traefik (HTTP/HTTPS)

---

### Paths

- **GOOGLE_APPLICATION_CREDENTIALS**: Must be readable JSON file containing GCP service account credentials
- **GCS_CREDENTIALS_PATH**: Alternative name for service account JSON path

**Docker volume mounting:**
```yaml
volumes:
  - ./secrets/gcs-credentials.json:/secrets/gcs-credentials.json:ro
```

**Notes:**
- No local artifact storage paths needed - GCS is used exclusively
- Temporary files are handled automatically and cleaned up

---

### URLs

- **REDIS_URL**: `redis://[user]:[password]@host:port/db`
- **HUGGINGFACE_API_URL**: `https://endpoint.com` or `http://tgi-service:80`
- **CORS_ORIGINS**: Comma-separated, no spaces

**Note:** No DATABASE_URL needed - Firestore uses project ID instead

---

## Security Recommendations

### Secrets Management

**Development:**
- Store in `.env.microservices` (git-ignored)

**Production:**
- Use secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault)
- Mount secrets as files in containers
- Use environment variables for non-sensitive config only

**Example (Docker Swarm secrets):**
```yaml
secrets:
  db_password:
    external: true
services:
  api-gateway:
    secrets:
      - db_password
```

---

### Password Requirements

**Minimum for production:**
- API_KEYS: 64 hex characters (use `openssl rand -hex 32`)
- All monitoring passwords: 16+ characters
- GCS service account: Use key rotation via GCP Console

---

### Key Rotation

**Recommended schedule:**
- API_KEYS: Every 90 days
- Monitoring passwords: Every 90 days
- GCS service account keys: Every 180 days (rotate via GCP Console)
- Firestore access: Controlled via GCS service account

**API Key rotation process:**
1. Generate new key: `openssl rand -hex 32`
2. Add to `API_KEYS` (keep old key): `API_KEYS=old_key,new_key`
3. Update clients to use new key
4. After grace period, remove old key from `API_KEYS`

**GCS Service Account rotation:**
1. Create new service account key in GCP Console
2. Download new JSON credentials file
3. Update `GOOGLE_APPLICATION_CREDENTIALS` path
4. Restart services
5. Delete old service account key in GCP Console

---

## Troubleshooting

### Variable Not Being Read

**Check precedence:**
```bash
# Print all environment variables (check Firestore and GCS vars)
docker compose exec api-gateway env | grep -E "FIRESTORE|GCS|GOOGLE"

# Check if .env file is being read
docker compose config
```

**Common issues:**
- Typo in variable name
- Extra spaces in `.env` file
- Wrong variable name (e.g., `GCS_CREDENTIALS_PATH` vs `GOOGLE_APPLICATION_CREDENTIALS`)
- Not restarting services after changes
- Service account JSON file not mounted correctly

---

### Invalid Values

**Check validation:**
```bash
# View service logs for validation errors
docker compose logs api-gateway | grep -i error
```

**Common validation errors:**
- Invalid port number
- Invalid URL format
- Non-existent file path
- Invalid enum value (e.g., `LLM_PROVIDER=invalid`)

---

### Defaults Not Working

**Verify defaults in code:**
- See `shared/config.py` for all default values
- Some defaults are context-dependent (e.g., auto-detect GCS project)

---

## Related Documentation

- **[Deployment Guide](./DEPLOYMENT.md)** - Complete deployment instructions
- **[Firebase API Flow](./FIREBASE_API_FLOW.md)** - API endpoint documentation
- **[Architecture Overview](./ARCHITECTURE_OVERVIEW.md)** - System architecture

---

## Support

**Issues:**
- GitHub Issues: https://github.com/yourusername/htbase/issues

**Questions:**
- Discord: [Your Discord Link]
- Discussions: https://github.com/yourusername/htbase/discussions
