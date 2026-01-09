# HTBase Environment Variables Reference

**Quick reference guide for all HTBase environment variables**

Last Updated: 2026-01-09

---

## Required Variables (Minimum Configuration)

These variables MUST be set for HTBase to run:

```bash
# Database
DB_PASSWORD=your_secure_database_password

# Authentication
API_KEYS=htbase_live_key1,htbase_live_key2

# Storage
STORAGE_PROVIDER=local  # or 'gcs'
```

**If using GCS storage, also required:**
```bash
GCS_BUCKET=your-bucket-name
GCS_PROJECT_ID=your-gcp-project-id
GCS_CREDENTIALS_PATH=./secrets/gcs-credentials.json
```

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

### Database Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DB_HOST` | string | `postgres` | PostgreSQL host |
| `DB_PORT` | int | `5432` | PostgreSQL port |
| `DB_NAME` | string | `htbase` | Database name |
| `DB_USER` | string | `htbase` | Database username |
| `DB_PASSWORD` | **REQUIRED** | - | Database password |
| `DB_POOL_SIZE` | int | `5` | Connection pool size |
| `DB_MAX_OVERFLOW` | int | `10` | Max overflow connections |
| `DB_SOCKET` | string | - | Cloud SQL socket path |

**Derived (auto-set):**
- `DATABASE_URL`: `postgresql://user:pass@host:port/db`

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

### Storage Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STORAGE_PROVIDER` | **REQUIRED** | `gcs` | Storage provider (gcs/local) |
| `ARTIFACTS_PATH` | string | `./data/artifacts` | Local storage path |
| `COMPRESSION_ENABLED` | bool | `true` | Enable gzip compression |
| `CLEANUP_AFTER_UPLOAD` | bool | `true` | Delete local files after upload |
| `STORAGE_CONCURRENCY` | int | `10` | Storage worker concurrency |

---

### Google Cloud Storage (GCS)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GCS_BUCKET` | **REQUIRED** (if using GCS) | - | GCS bucket name |
| `GCS_PROJECT_ID` | **REQUIRED** (if using GCS) | - | GCP project ID |
| `GCS_CREDENTIALS_PATH` | **REQUIRED** (if using GCS) | `./secrets/gcs-credentials.json` | Service account JSON path |

**Alternative:**
- `GOOGLE_CLOUD_PROJECT`: Alias for `GCS_PROJECT_ID`
- `GOOGLE_APPLICATION_CREDENTIALS`: Alias for `GCS_CREDENTIALS_PATH`

---

### Firestore (Optional)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FIRESTORE_PROJECT_ID` | string | - | Firestore project ID |
| `FIRESTORE_COLLECTION` | string | `articles` | Collection name |

**Notes:**
- Optional - only needed for mobile client sync
- Uses same GCS credentials
- Can use `GOOGLE_CLOUD_PROJECT` instead

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

### Minimal (Local Development)

```bash
# Core
ENVIRONMENT=development
LOG_LEVEL=DEBUG
LOG_FORMAT=text

# Database (using defaults)
DB_PASSWORD=dev_password_not_for_production

# Authentication
API_KEYS=htbase_test_dev123

# Storage
STORAGE_PROVIDER=local
ARTIFACTS_PATH=./data/artifacts

# Disable features
ENABLE_SUMMARIZATION=false
```

---

### Production (with GCS)

```bash
# Core
ENVIRONMENT=production
VERSION=latest
LOG_LEVEL=INFO
LOG_FORMAT=json

# Database
DB_USER=htbase
DB_PASSWORD=SecurePasswordHere123!@#
DB_NAME=htbase
DB_PORT=5432

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

# Storage
STORAGE_PROVIDER=gcs
GCS_BUCKET=htbase-production-archives
GCS_PROJECT_ID=my-gcp-project
GCS_CREDENTIALS_PATH=./secrets/gcs-credentials.json
COMPRESSION_ENABLED=true
CLEANUP_AFTER_UPLOAD=true
STORAGE_CONCURRENCY=10

# Firestore
FIRESTORE_PROJECT_ID=my-firebase-project
FIRESTORE_COLLECTION=articles

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

### Production (Local Storage Only)

```bash
# Core
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json

# Database
DB_PASSWORD=SecurePasswordHere123!@#

# Authentication
API_KEYS=htbase_live_a1b2c3...,htbase_live_x7y8z9...

# Storage (local only)
STORAGE_PROVIDER=local
ARTIFACTS_PATH=/mnt/archives
COMPRESSION_ENABLED=false
CLEANUP_AFTER_UPLOAD=false

# Disable features
ENABLE_SUMMARIZATION=false
```

---

## Environment Variable Precedence

HTBase uses Pydantic settings with the following precedence (highest to lowest):

1. **Environment variables** (e.g., `DB_HOST=postgres`)
2. **Nested environment variables** (e.g., `DATABASE__HOST=postgres`)
3. **`.env` file** in project root
4. **Default values** in code

**Example:**
```bash
# Both are equivalent:
DB_HOST=postgres
DATABASE__HOST=postgres
```

---

## Validation Rules

### Passwords

- **DB_PASSWORD**: No restrictions (but use strong passwords in production)
- **API_KEYS**: Comma-separated, no spaces
- **FLOWER_PASSWORD**: No restrictions
- **REDIS_COMMANDER_PASSWORD**: No restrictions

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
- `5432`: PostgreSQL
- `6379`: Redis
- `5555`: Flower
- `8081`: Redis Commander
- `80/443`: Traefik (HTTP/HTTPS)

---

### Paths

- **ARTIFACTS_PATH**: Must be writable by container user
- **GCS_CREDENTIALS_PATH**: Must be readable JSON file
- **DATA_DIR**: Must be writable

**Docker volume mounting:**
```yaml
volumes:
  - ./data/artifacts:/app/artifacts
  - ./secrets/gcs-credentials.json:/secrets/gcs-credentials.json:ro
```

---

### URLs

- **REDIS_URL**: `redis://[user]:[password]@host:port/db`
- **DATABASE_URL**: `postgresql://user:pass@host:port/dbname`
- **HUGGINGFACE_API_URL**: `https://endpoint.com` or `http://tgi-service:80`
- **CORS_ORIGINS**: Comma-separated, no spaces

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
- DB_PASSWORD: 32+ characters
- API_KEYS: 64 hex characters (use `openssl rand -hex 32`)
- All monitoring passwords: 16+ characters

---

### Key Rotation

**Recommended schedule:**
- API_KEYS: Every 90 days
- DB_PASSWORD: Every 180 days
- Monitoring passwords: Every 90 days
- GCS credentials: Every 180 days

**API Key rotation process:**
1. Generate new key: `openssl rand -hex 32`
2. Add to `API_KEYS` (keep old key): `API_KEYS=old_key,new_key`
3. Update clients to use new key
4. After grace period, remove old key from `API_KEYS`

---

## Troubleshooting

### Variable Not Being Read

**Check precedence:**
```bash
# Print all environment variables
docker compose exec api-gateway env | grep DB_

# Check if .env file is being read
docker compose config
```

**Common issues:**
- Typo in variable name
- Extra spaces in `.env` file
- Using wrong prefix (e.g., `DATABASE_HOST` instead of `DB_HOST`)
- Not restarting services after changes

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
