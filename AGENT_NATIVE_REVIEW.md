# Agent-Native Architecture Review

**Date**: 2026-01-09
**Reviewer**: Agent-Native Architecture Specialist
**System**: HTBase Microservices Architecture

---

## Executive Summary

The HTBase microservices architecture demonstrates **moderate agent-native readiness** with several strong foundations but critical gaps in security, documentation, and operational tooling. The system is well-structured for programmatic access with clear REST APIs and Pydantic schemas, but lacks authentication, comprehensive examples, and webhook support.

**Overall Grade: C+ (70/100)**

### Key Findings

**Strengths:**
- Well-defined Pydantic request/response schemas with clear validation
- OpenAPI/Swagger documentation available at `/docs` and `/redoc`
- Asynchronous task-based architecture with clear status endpoints
- Batch operations support for efficient bulk processing
- Clear error responses with HTTP status codes

**Critical Gaps:**
- **No authentication mechanism** (blocks production deployment)
- Limited operational documentation for agents
- No webhook/callback support for async notifications
- Rate limiting configured but not enforced
- No CLI tooling for agent interactions

---

## Detailed Assessment

### 1. API Discoverability ✅ GOOD (8/10)

**Status**: API is discoverable through OpenAPI documentation

**Evidence:**
- OpenAPI docs exposed at `/docs` (Swagger UI)
- ReDoc documentation at `/redoc`
- FastAPI auto-generates comprehensive API documentation
- All endpoints properly tagged and organized

**Files:**
- `services/api-gateway/app/main.py` (lines 70-71)
- OpenAPI available at: `http://localhost:8080/docs`

**Missing:**
- No API versioning in documentation (all endpoints at `/api/v1`)
- Missing comprehensive examples with realistic use cases
- No code generation artifacts (client SDKs)

**Recommendation:**
```python
# Add more detailed endpoint descriptions
@router.post("/save",
    response_model=TaskAccepted,
    summary="Archive a URL",
    description="""
    Archive a URL using one or more archiving methods.

    **Common Use Cases:**
    - Archive blog posts for offline reading
    - Preserve research articles
    - Create snapshots of dynamic web content

    **For AI Agents:**
    This endpoint accepts a URL and returns a task_id immediately.
    Poll GET /tasks/{task_id} for status updates.
    """,
    responses={
        400: {"description": "Invalid archiver specified"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded"}
    }
)
async def save_url(...):
```

---

### 2. OpenAPI/Swagger Documentation ✅ PRESENT (7/10)

**Status**: OpenAPI documentation is available but needs enhancement

**Current Implementation:**
```python
app = FastAPI(
    title="HTBase API Gateway",
    description="API Gateway for HTBase archiving service",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
```

**What Works:**
- Auto-generated from FastAPI routes
- Interactive Swagger UI for testing
- ReDoc for cleaner documentation view
- Request/response schemas visible

**Missing:**
- No OpenAPI spec export endpoint (`/openapi.json` endpoint exists but not documented)
- Limited endpoint examples
- No authentication schemes documented in OpenAPI spec
- Missing error response schemas for most endpoints

**Recommendation:**
```python
# Add OpenAPI metadata and examples
app = FastAPI(
    title="HTBase API Gateway",
    description="""
    HTBase provides web archiving as a service using multiple archiving methods.

    ## For AI Agents

    - All endpoints return JSON
    - Async operations return task_id for polling
    - Rate limit: 100 requests/minute per API key
    - Authentication: Bearer token in Authorization header

    ## Quick Start

    1. Archive URL: POST /save with {"url": "https://example.com"}
    2. Get status: GET /tasks/{task_id}
    3. Download: GET /retrieve?id={item_id}
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",  # Explicit
    openapi_tags=[
        {"name": "saves", "description": "Archive URL operations"},
        {"name": "tasks", "description": "Task status and management"},
        {"name": "admin", "description": "Administrative operations"},
    ],
)

# Add example to model
class SaveRequest(BaseModel):
    url: HttpUrl
    id: str
    archivers: Optional[List[str]] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "url": "https://www.nytimes.com/2024/01/article",
                    "id": "article-2024-01-09",
                    "archivers": ["readability", "pdf"]
                }
            ]
        }
    }
```

**Action Items:**
- [ ] Add comprehensive examples to all Pydantic models
- [ ] Document authentication schemes in OpenAPI spec
- [ ] Add detailed error response schemas
- [ ] Export OpenAPI spec as downloadable JSON/YAML
- [ ] Include rate limit information in OpenAPI metadata

---

### 3. Clear Request/Response Contracts ✅ EXCELLENT (9/10)

**Status**: Well-defined Pydantic schemas with validation

**Evidence:**
```python
# From shared/models/__init__.py

class SaveRequest(BaseModel):
    """Request to save/archive a URL."""
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id", "item_id"),
    )
    archivers: Optional[List[str]] = Field(
        default=None,
        description="List of archivers to use, or None for all"
    )
    priority: int = Field(default=0, ge=0, le=10)

class TaskAccepted(BaseModel):
    """Response when task is accepted for async processing."""
    task_id: str
    count: int
    message: str = "Task accepted"
```

**Strengths:**
- All models use Pydantic BaseModel with type hints
- Field descriptions included
- Validation constraints specified (ge=0, le=10)
- Flexible field aliases for compatibility
- Clear separation of request/response models

**Database Schemas Also Clear:**
```python
# From shared/db/schemas.py

class ArtifactStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

class ArtifactSchema(BaseModel):
    artifact_id: int
    archiver: str
    status: Optional[str] = None
    # ... comprehensive fields
```

**Minor Issues:**
- Some models missing examples for OpenAPI docs
- Inconsistent optional field patterns (Optional[str] vs str | None)

**Recommendation**: Add comprehensive examples to all models for better agent understanding.

---

### 4. Error Messages ⚠️ NEEDS IMPROVEMENT (6/10)

**Status**: HTTP exceptions used but error messages could be more actionable

**Current Implementation:**
```python
# From saves.py
if invalid_archivers:
    raise HTTPException(
        status_code=400,
        detail=f"Invalid archivers: {invalid_archivers}. Valid options: {AVAILABLE_ARCHIVERS}",
    )

if not archived_url:
    raise HTTPException(status_code=404, detail="Archive not found")
```

**What Works:**
- Proper HTTP status codes (400, 404, 500)
- Clear error details in most cases
- Lists valid options for validation errors

**What's Missing:**
- No structured error response format
- Limited retry guidance
- No error codes for programmatic handling
- Missing troubleshooting hints

**Recommended Error Format:**
```python
class ErrorResponse(BaseModel):
    """Structured error response for agents."""
    error_code: str  # e.g., "INVALID_ARCHIVER"
    message: str     # Human-readable
    details: dict    # Additional context
    retry_after: Optional[int] = None  # Seconds to wait
    documentation_url: Optional[str] = None

# Usage
raise HTTPException(
    status_code=400,
    detail={
        "error_code": "INVALID_ARCHIVER",
        "message": "Archiver 'chrome-ext' is not supported",
        "details": {
            "requested": ["chrome-ext"],
            "available": ["singlefile", "monolith", "readability", "pdf", "screenshot"],
            "suggestion": "Did you mean 'singlefile'?"
        },
        "documentation_url": "https://docs.htbase.com/archivers"
    }
)
```

**Action Items:**
- [ ] Create structured error response model
- [ ] Add error codes for common failures
- [ ] Include retry guidance for transient errors
- [ ] Add documentation links to error responses
- [ ] Implement proper error logging with context

---

### 5. CLI Access ⚠️ LIMITED (5/10)

**Status**: REST API works with curl/httpie but no dedicated CLI tool

**Current State:**
- Agents can use curl/httpie to interact with API
- Documentation includes curl examples
- No official CLI wrapper

**Examples in Docs:**
```bash
# From REARCHITECTURE_PLAN.md
curl http://localhost:8080/health

curl -X POST http://localhost:8080/api/v2/archive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "archivers": ["readability"]}'

curl http://localhost:8080/api/v2/tasks/{task_id}
```

**Missing:**
- No dedicated htbase CLI tool
- No shell completions
- No configuration file support (~/.htbaserc)
- No output formatting options (JSON, table, etc.)

**Recommendation - Create CLI Tool:**

```python
# htbase_cli/main.py
import click
import httpx
from rich.console import Console
from rich.table import Table

@click.group()
@click.option('--api-url', envvar='HTBASE_API_URL', default='http://localhost:8080')
@click.option('--api-key', envvar='HTBASE_API_KEY')
@click.pass_context
def cli(ctx, api_url, api_key):
    """HTBase CLI - Web archiving from your terminal."""
    ctx.ensure_object(dict)
    ctx.obj['api_url'] = api_url
    ctx.obj['api_key'] = api_key

@cli.command()
@click.argument('url')
@click.option('--id', help='Custom identifier')
@click.option('--archiver', '-a', multiple=True, help='Archiver(s) to use')
@click.option('--wait/--no-wait', default=False, help='Wait for completion')
@click.pass_context
def archive(ctx, url, id, archiver, wait):
    """Archive a URL."""
    client = httpx.Client(base_url=ctx.obj['api_url'])

    response = client.post('/api/v1/save', json={
        'url': url,
        'id': id or url.split('/')[-1],
        'archivers': list(archiver) or None
    })

    data = response.json()
    click.echo(f"✓ Task created: {data['task_id']}")

    if wait:
        # Poll for completion
        import time
        while True:
            status = client.get(f'/api/v1/tasks/{data["task_id"]}').json()
            if status['status'] in ['completed', 'failed']:
                break
            click.echo(f"Progress: {status['progress']:.1f}%")
            time.sleep(2)

        if status['status'] == 'completed':
            click.echo(f"✓ Archive complete: {status['items'][0]['saved_path']}")
        else:
            click.echo(f"✗ Archive failed", err=True)

@cli.command()
@click.argument('task_id')
@click.option('--format', type=click.Choice(['json', 'table']), default='table')
@click.pass_context
def status(ctx, task_id, format):
    """Check task status."""
    client = httpx.Client(base_url=ctx.obj['api_url'])
    response = client.get(f'/api/v1/tasks/{task_id}')
    data = response.json()

    if format == 'json':
        click.echo(response.text)
    else:
        console = Console()
        table = Table(title=f"Task {task_id}")
        table.add_column("URL")
        table.add_column("Status")
        table.add_column("Archiver")

        for item in data['items']:
            table.add_row(item['url'], item['status'], item.get('archiver', 'N/A'))

        console.print(table)

if __name__ == '__main__':
    cli()
```

**Usage:**
```bash
# Install
pip install htbase-cli

# Configure
export HTBASE_API_URL=https://htbase.example.com
export HTBASE_API_KEY=your-key-here

# Use
htbase archive https://example.com --wait
htbase status abc123def456
htbase list --status completed
```

**Action Items:**
- [ ] Create official CLI package
- [ ] Add shell completions (bash, zsh, fish)
- [ ] Support config file (~/.htbaserc)
- [ ] Add output formatting options
- [ ] Publish to PyPI

---

### 6. Webhook Support ❌ MISSING (0/10)

**Status**: No webhook/callback mechanism implemented

**Current Limitation:**
- Agents must poll `/tasks/{task_id}` for status updates
- No push notifications when tasks complete
- Inefficient for long-running operations

**From Architecture Doc:**
```yaml
# REARCHITECTURE_PLAN.md mentions webhooks as "optional future enhancement"
POST /api/v2/archive
Request:
  url: string
  webhook_url: string  # Called on completion
```

**Impact:**
- Agents waste resources polling
- Increased API load from status checks
- Poor user experience for long tasks
- Cannot integrate with event-driven systems

**Recommended Implementation:**

```python
# Add to SaveRequest model
class SaveRequest(BaseModel):
    url: HttpUrl
    id: str
    archivers: Optional[List[str]] = None
    webhook_url: Optional[HttpUrl] = None
    webhook_secret: Optional[str] = Field(
        default=None,
        description="HMAC secret for webhook signature verification"
    )

# Celery task callback
@celery_app.task
def notify_webhook(task_id: str, webhook_url: str, webhook_secret: str, status: dict):
    """Send webhook notification when task completes."""
    import hmac
    import hashlib

    payload = {
        "task_id": task_id,
        "status": status['status'],
        "progress": status['progress'],
        "items": status['items'],
        "timestamp": datetime.utcnow().isoformat()
    }

    # Sign payload
    signature = hmac.new(
        webhook_secret.encode(),
        json.dumps(payload).encode(),
        hashlib.sha256
    ).hexdigest()

    # Send webhook
    httpx.post(
        webhook_url,
        json=payload,
        headers={
            "X-HTBase-Signature": signature,
            "X-HTBase-Event": "task.completed"
        },
        timeout=10
    )

# In archive workflow
if request.webhook_url:
    workflow = chain(
        archive_tasks,
        notify_webhook.s(
            task_id=workflow_id,
            webhook_url=str(request.webhook_url),
            webhook_secret=request.webhook_secret or "",
            status=TaskStatusResponse(...)
        )
    )
```

**Webhook Events:**
- `task.created` - Task accepted
- `task.progress` - Progress update (optional)
- `task.completed` - Task finished successfully
- `task.failed` - Task failed
- `archive.completed` - Individual archiver completed

**Action Items:**
- [ ] Add webhook_url field to SaveRequest
- [ ] Implement webhook notification task
- [ ] Add webhook signature verification
- [ ] Support retry logic for failed webhooks
- [ ] Add webhook delivery logs/dashboard
- [ ] Document webhook payload format

---

### 7. Batch Operations ✅ GOOD (8/10)

**Status**: Batch operations supported at API level

**Evidence:**
```python
# From saves.py
@router.post("/save/batch", response_model=TaskAccepted)
async def save_batch(request: BatchSaveRequest, db: Session = Depends(get_db)):
    """Archive multiple URLs in batch."""
    batch_id = uuid.uuid4().hex
    # ... creates tasks for all items
```

**Batch Endpoints:**
- `POST /save/batch` - Archive multiple URLs
- `POST /archive/{archiver}/batch` - Batch with specific archiver
- Returns single task_id for entire batch

**Strengths:**
- Efficient bulk submission
- Single task_id for tracking batch
- Parallel processing via Celery groups
- Skip duplicate checking

**Limitations:**
- No pagination support for large batches (>1000 items)
- No bulk delete/requeue endpoints
- No batch priority management
- Limited batch size (no documented limit)

**Missing Batch Operations:**
```python
# Recommended additions

@router.post("/save/batch-by-file")
async def save_batch_from_file(
    file: UploadFile,
    format: str = "json"  # json, csv, txt
):
    """Upload file with URLs to archive."""
    # Parse file and create batch
    pass

@router.post("/admin/batch-requeue")
async def batch_requeue(
    status: str = "failed",
    archivers: Optional[List[str]] = None,
    limit: int = 1000
):
    """Requeue multiple failed tasks."""
    pass

@router.delete("/admin/batch-delete")
async def batch_delete(
    filters: Dict[str, Any],
    dry_run: bool = True
):
    """Bulk delete archives matching filters."""
    pass
```

**Action Items:**
- [ ] Add pagination for large batches
- [ ] Document batch size limits
- [ ] Add batch upload from file endpoint
- [ ] Implement bulk administrative operations
- [ ] Add batch progress aggregation

---

### 8. Rate Limiting ⚠️ CONFIGURED BUT NOT ENFORCED (3/10)

**Status**: Rate limit configuration exists but not implemented

**Evidence:**

**Configuration Present:**
```python
# From REARCHITECTURE_PLAN.md
# Celery task annotations
task_annotations={
    'archive_worker.tasks.archive_url': {
        'rate_limit': '10/m',
    },
    'summarization_worker.tasks.summarize_article': {
        'rate_limit': '30/m',
    },
}
```

**Environment Variable:**
```bash
# From .env.microservices.example
API_RATE_LIMIT=100/minute
```

**But NOT Enforced in API Gateway:**
```python
# main.py has no rate limiting middleware
# No slowapi or similar rate limiting library imported
# No rate limit headers in responses
```

**Critical Issue:**
Without rate limiting, the API is vulnerable to:
- Resource exhaustion attacks
- Cost explosions (expensive Chromium workers)
- Service degradation for legitimate users

**Recommended Implementation:**

```python
# Add to main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to routes
@router.post("/save")
@limiter.limit("10/minute")  # Per IP
async def save_url(...):
    pass

# Or per API key (after auth implemented)
def get_api_key_from_request(request: Request) -> str:
    return request.headers.get("Authorization", "").replace("Bearer ", "")

limiter = Limiter(key_func=get_api_key_from_request)

# Different limits for different operations
@limiter.limit("100/hour")  # Archive operations
@limiter.limit("1000/hour")  # Status checks (less expensive)
```

**Rate Limit Response:**
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

**Headers to Include:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704801300
Retry-After: 45
```

**Action Items:**
- [ ] **CRITICAL**: Implement rate limiting before production
- [ ] Add slowapi or similar library
- [ ] Configure per-endpoint rate limits
- [ ] Add rate limit headers to responses
- [ ] Support different limits for authenticated users
- [ ] Add rate limit bypass for admin users
- [ ] Document rate limits in API docs

---

### 9. Authentication ❌ CRITICAL MISSING (0/10)

**Status**: **NO AUTHENTICATION - BLOCKS PRODUCTION DEPLOYMENT**

**Critical Security Issue:**
From `/.claude/todos/002-pending-p1-no-authentication-api-gateway.md`:

> API Gateway has zero authentication or authorization. All endpoints are publicly accessible, allowing:
> - Unauthenticated users to submit expensive archive tasks
> - Access to task status and results
> - Potential abuse for cryptocurrency mining, DDoS amplification
> - Unauthorized access to archived content and summaries

**Impact:**
- **Resource exhaustion** from malicious submissions
- **Cloud cost explosion** (Chromium workers are expensive)
- **Data privacy violations**
- **Compliance failures** (GDPR, SOC 2)

**No Auth on Critical Endpoints:**
- `POST /save` - Submit archive tasks
- `POST /save/batch` - Batch tasks
- `GET /tasks/{task_id}` - View status
- `GET /retrieve` - Download archives
- `POST /admin/summarize` - Trigger expensive LLM operations

**From Todo:**
```python
# Proposed Option 1: API Key Authentication (Recommended for MVP)

from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    api_key = credentials.credentials
    valid_keys = os.getenv("API_KEYS", "").split(",")

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return api_key

# Apply to routes
@router.post("/save", dependencies=[Depends(verify_api_key)])
```

**Recommended Implementation Steps:**

1. **Phase 1: API Key Auth (1-2 days)**
   ```python
   # shared/auth.py
   from fastapi import Security, HTTPException, Depends
   from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

   security = HTTPBearer()

   async def verify_api_key(
       credentials: HTTPAuthorizationCredentials = Security(security),
       db: Session = Depends(get_db)
   ) -> APIKey:
       """Verify API key and return key metadata."""
       api_key = credentials.credentials

       # Check in database (not env var for production)
       key_record = db.query(APIKey).filter(
           APIKey.key_hash == hashlib.sha256(api_key.encode()).hexdigest(),
           APIKey.is_active == True,
           APIKey.expires_at > datetime.utcnow()
       ).first()

       if not key_record:
           raise HTTPException(
               status_code=401,
               detail={
                   "error_code": "INVALID_API_KEY",
                   "message": "API key is invalid or expired",
                   "documentation_url": "https://docs.htbase.com/auth"
               }
           )

       # Update last_used_at
       key_record.last_used_at = datetime.utcnow()
       db.commit()

       return key_record

   # Apply globally or per-route
   @router.post("/save", dependencies=[Depends(verify_api_key)])
   async def save_url(...):
       pass
   ```

2. **Database Schema for API Keys:**
   ```python
   class APIKey(Base):
       __tablename__ = "api_keys"

       id = Column(Integer, primary_key=True)
       name = Column(String, nullable=False)
       key_hash = Column(String, unique=True, nullable=False)  # SHA256
       key_prefix = Column(String(8))  # For display (e.g., "sk_live_abc123...")
       is_active = Column(Boolean, default=True)
       created_at = Column(DateTime, default=datetime.utcnow)
       expires_at = Column(DateTime, nullable=True)
       last_used_at = Column(DateTime, nullable=True)
       rate_limit_override = Column(Integer, nullable=True)
       scopes = Column(JSON, default=list)  # ["archive", "admin"]
   ```

3. **Key Generation Endpoint:**
   ```python
   @router.post("/admin/api-keys", dependencies=[Depends(verify_admin)])
   async def create_api_key(
       name: str,
       expires_in_days: int = 365,
       scopes: List[str] = ["archive"],
       db: Session = Depends(get_db)
   ):
       """Create a new API key (admin only)."""
       # Generate key
       key = f"sk_{'live' if ENVIRONMENT == 'production' else 'test'}_{secrets.token_urlsafe(32)}"
       key_hash = hashlib.sha256(key.encode()).hexdigest()

       # Store
       api_key = APIKey(
           name=name,
           key_hash=key_hash,
           key_prefix=key[:16] + "...",
           expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
           scopes=scopes
       )
       db.add(api_key)
       db.commit()

       return {
           "key": key,  # ONLY shown once
           "key_prefix": api_key.key_prefix,
           "expires_at": api_key.expires_at.isoformat()
       }
   ```

**Action Items:**
- [ ] **BLOCKS MERGE**: Implement API key authentication
- [ ] Create APIKey database table
- [ ] Add verify_api_key dependency
- [ ] Protect all endpoints
- [ ] Store keys in Secret Manager (not env vars)
- [ ] Add key rotation mechanism
- [ ] Implement scope-based permissions
- [ ] Add audit logging
- [ ] Document authentication in OpenAPI
- [ ] Create key management endpoints

---

### 10. Documentation Quality ⚠️ NEEDS IMPROVEMENT (6/10)

**Status**: Technical documentation exists but lacks agent-oriented guidance

**Available Documentation:**
- `docs/REARCHITECTURE_PLAN.md` (63KB) - Comprehensive architecture
- `CLAUDE.md` - Project instructions
- `README.md` - Basic setup
- OpenAPI docs at `/docs`

**Strengths:**
- Detailed architecture documentation
- Clear migration plan with phases
- Deployment profiles explained
- Code examples in architecture doc

**Gaps for Agent Accessibility:**

1. **No API Quick Start Guide**
   - Missing "Hello World" example
   - No common workflows documented
   - No troubleshooting section

2. **No Error Reference**
   - Error codes not documented
   - No resolution guidance
   - Missing common error scenarios

3. **No SDKs or Client Libraries**
   - No Python client
   - No JavaScript/TypeScript SDK
   - No code generation examples

4. **Limited Agent-Specific Guidance:**
   - No best practices for agents
   - No polling vs webhook guidance
   - No batch processing examples
   - No rate limit handling advice

**Recommended Documentation Structure:**

```
docs/
├── REARCHITECTURE_PLAN.md        # ✅ Exists
├── API_QUICKSTART.md              # ❌ Missing
├── API_REFERENCE.md               # ❌ Missing (OpenAPI only)
├── ERROR_CODES.md                 # ❌ Missing
├── AUTHENTICATION.md              # ❌ Missing
├── BEST_PRACTICES.md              # ❌ Missing
├── AGENT_GUIDE.md                 # ❌ Missing
├── WEBHOOKS.md                    # ❌ Missing
├── RATE_LIMITING.md               # ❌ Missing
├── examples/
│   ├── python/                    # ❌ Missing
│   │   ├── simple_archive.py
│   │   ├── batch_archive.py
│   │   ├── webhook_handler.py
│   │   └── error_handling.py
│   ├── javascript/                # ❌ Missing
│   ├── curl/                      # ⚠️ Partial (in REARCHITECTURE_PLAN)
│   └── httpie/                    # ❌ Missing
└── sdk/
    ├── python/                    # ❌ Missing
    └── typescript/                # ❌ Missing
```

**API_QUICKSTART.md Template:**

```markdown
# HTBase API Quick Start

## For AI Agents

HTBase is designed for programmatic access. This guide shows you how to:
1. Archive a URL
2. Check task status
3. Download the archived content

## Authentication

All requests require an API key in the Authorization header:

```bash
Authorization: Bearer sk_live_your_key_here
```

Get your API key from: [Dashboard](https://htbase.example.com/keys)

## Basic Workflow

### 1. Archive a URL

**Request:**
```bash
curl -X POST https://api.htbase.com/api/v1/save \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.example.com/article",
    "id": "article-2024-01-09",
    "archivers": ["readability", "pdf"]
  }'
```

**Response:**
```json
{
  "task_id": "abc123def456",
  "count": 2,
  "message": "Archive tasks dispatched for 2 archiver(s)"
}
```

### 2. Poll for Status

**Request:**
```bash
curl https://api.htbase.com/api/v1/tasks/abc123def456 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response (In Progress):**
```json
{
  "task_id": "abc123def456",
  "status": "in_progress",
  "progress": 50.0,
  "items": [
    {
      "url": "https://www.example.com/article",
      "id": "article-2024-01-09",
      "status": "success",
      "archiver": "readability",
      "saved_path": "/data/article-2024-01-09/readability/output.json"
    },
    {
      "url": "https://www.example.com/article",
      "id": "article-2024-01-09",
      "status": "in_progress",
      "archiver": "pdf"
    }
  ]
}
```

### 3. Download Archive

**Request:**
```bash
curl https://api.htbase.com/api/v1/retrieve?id=article-2024-01-09 \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
{
  "id": "article-2024-01-09",
  "url": "https://www.example.com/article",
  "archives": [
    {
      "archiver": "readability",
      "saved_path": "/data/article-2024-01-09/readability/output.json",
      "gcs_path": "gs://htbase/article-2024-01-09/readability/output.json",
      "size_bytes": 45678
    },
    {
      "archiver": "pdf",
      "saved_path": "/data/article-2024-01-09/pdf/output.pdf",
      "size_bytes": 234567
    }
  ]
}
```

## Error Handling

### Common Errors

**401 Unauthorized:**
```json
{
  "error_code": "INVALID_API_KEY",
  "message": "API key is invalid or expired",
  "documentation_url": "https://docs.htbase.com/auth"
}
```

**Solution:** Check your API key and ensure it hasn't expired.

**429 Rate Limit Exceeded:**
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

**Solution:** Wait for `retry_after` seconds before retrying.

## Agent Best Practices

### 1. Use Webhooks Instead of Polling

Save resources by registering a webhook:

```json
{
  "url": "https://example.com/article",
  "id": "article-2024-01-09",
  "webhook_url": "https://your-agent.com/webhook"
}
```

### 2. Batch Operations

Archive multiple URLs efficiently:

```bash
curl -X POST https://api.htbase.com/api/v1/save/batch \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"url": "https://example.com/1", "id": "article-1"},
      {"url": "https://example.com/2", "id": "article-2"}
    ]
  }'
```

### 3. Handle Rate Limits

```python
import time
import httpx

def archive_with_retry(url: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            response = httpx.post(
                "https://api.htbase.com/api/v1/save",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"url": url, "id": url.split("/")[-1]}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                time.sleep(retry_after)
            else:
                raise
    raise Exception("Max retries exceeded")
```

## Next Steps

- [Full API Reference](/docs/API_REFERENCE.md)
- [Authentication Guide](/docs/AUTHENTICATION.md)
- [Webhook Setup](/docs/WEBHOOKS.md)
- [Python SDK](/docs/sdk/python/)
```

**Action Items:**
- [ ] Create API_QUICKSTART.md
- [ ] Create ERROR_CODES.md with all error codes
- [ ] Create AGENT_GUIDE.md with best practices
- [ ] Add examples/ directory with code samples
- [ ] Create Python SDK package
- [ ] Add TypeScript SDK
- [ ] Document all error scenarios
- [ ] Add troubleshooting guide

---

## Summary of Action Items

### Critical (Blocks Production)

1. **Implement API Key Authentication**
   - Priority: P0
   - Effort: 2-3 days
   - Blocks: Production deployment
   - Risk: High (security vulnerability)

2. **Implement Rate Limiting**
   - Priority: P0
   - Effort: 1 day
   - Blocks: Production deployment
   - Risk: High (cost/abuse)

### High Priority (Needed for Agent-Native)

3. **Add Webhook Support**
   - Priority: P1
   - Effort: 2-3 days
   - Impact: Major improvement to agent UX

4. **Enhance Error Responses**
   - Priority: P1
   - Effort: 1-2 days
   - Impact: Better error recovery

5. **Create API Documentation**
   - Priority: P1
   - Effort: 2-3 days
   - Impact: Improved discoverability

6. **Build CLI Tool**
   - Priority: P2
   - Effort: 3-4 days
   - Impact: Better dev/agent experience

### Medium Priority (Quality of Life)

7. **Add OpenAPI Examples**
   - Priority: P2
   - Effort: 1 day
   - Impact: Better documentation

8. **Create Python SDK**
   - Priority: P2
   - Effort: 3-5 days
   - Impact: Easier integration

9. **Enhance Batch Operations**
   - Priority: P3
   - Effort: 2-3 days
   - Impact: Bulk operation efficiency

---

## Conclusion

The HTBase microservices architecture has a **solid foundation** for agent-native access with clear REST APIs, well-defined schemas, and async task handling. However, **critical security gaps** (no auth, no rate limiting) must be addressed before production deployment.

**Key Recommendations:**

1. **Immediately implement authentication and rate limiting** (P0)
2. Add webhook support for better async handling (P1)
3. Improve documentation with agent-focused guides (P1)
4. Create official CLI and SDK (P2)
5. Enhance error responses with structured format (P2)

**Timeline to Production-Ready Agent-Native API:**
- Critical fixes: 3-4 days
- High priority improvements: 5-7 days
- **Total: 2 weeks** to production-grade agent-native system

With these improvements, HTBase will be **highly accessible** to AI agents with:
- ✅ Clear, discoverable API
- ✅ Robust authentication
- ✅ Efficient async handling (webhooks)
- ✅ Comprehensive documentation
- ✅ Great developer experience

---

## References

**Key Files Reviewed:**
- `services/api-gateway/app/main.py`
- `services/api-gateway/app/routes/saves.py`
- `services/api-gateway/app/routes/tasks.py`
- `services/api-gateway/app/routes/admin.py`
- `shared/models/__init__.py`
- `shared/db/schemas.py`
- `docs/REARCHITECTURE_PLAN.md`
- `.claude/todos/002-pending-p1-no-authentication-api-gateway.md`

**Architecture:**
- Microservices on Cloud Run
- Celery + Redis for task queue
- PostgreSQL for metadata
- GCS for file storage
- FastAPI for API Gateway

**Contact:**
For questions about this review, see:
- Project maintainer documentation
- `.claude/agents/review/agent-native-reviewer.md`
