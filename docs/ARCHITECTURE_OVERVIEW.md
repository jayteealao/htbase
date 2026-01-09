# HTBase Architecture Overview

## Table of Contents

- [Introduction](#introduction)
- [System Components](#system-components)
- [Component Architecture](#component-architecture)
- [Communication Patterns](#communication-patterns)
- [Storage Strategy](#storage-strategy)
- [Task Management Architecture](#task-management-architecture)
- [Data Flow](#data-flow)
- [Deployment Architecture](#deployment-architecture)
- [Scalability Considerations](#scalability-considerations)

---

## Introduction

HTBase is a multi-archiver web content preservation system designed for both web and mobile applications. The system provides:

- **Multiple Archival Formats**: Readability (text), Monolith/SingleFile (HTML), PDF, and Screenshots
- **Dual Database Architecture**: PostgreSQL (primary) + Firestore (mobile replica)
- **Cloud Storage Integration**: Google Cloud Storage with local backup
- **Asynchronous Processing**: Background workers with task queuing
- **Mobile-Optimized APIs**: Firebase endpoints with signed download URLs
- **AI Summarization**: Automatic content summarization pipeline

**Core Design Principles:**
- PostgreSQL as single source of truth
- Eventual consistency for mobile replica
- Fail-fast for primary database, best-effort for replica
- Asynchronous processing for long-running tasks
- Multi-provider storage with redundancy

---

## System Components

### 1. API Gateway (`services/api-gateway/`)

**Responsibilities:**
- HTTP request handling (FastAPI)
- Authentication (API key verification)
- Rate limiting (Redis-based)
- Request validation (Pydantic models)
- Response formatting

**Endpoints:**
- `/api/v1/firebase/*` - Mobile-optimized endpoints
- `/api/v1/save` - Standard save endpoint
- `/api/v1/tasks/*` - Status polling
- `/api/v1/content/*` - Content retrieval
- `/api/v1/health` - Health checks

**Code Location:** `services/api-gateway/app/routes/`

---

### 2. Database Layer (`shared/storage/`)

**Components:**
- **DualDatabaseStorage**: Orchestrator for dual writes
- **PostgresStorage**: Primary database implementation (SQLAlchemy)
- **FirestoreStorage**: Mobile replica implementation (Firebase Admin SDK)
- **SyncFilter**: Data filtering for Firestore writes

**Responsibilities:**
- CRUD operations for articles, artifacts, metadata
- Dual-write orchestration
- Failure mode handling
- Data consistency guarantees

**Tables (PostgreSQL):**
- `archived_urls` - Article metadata and URLs
- `url_metadata` - Rich metadata (Pocket data, summaries, entities)
- `archive_artifact` - Archival artifacts and status

**Collections (Firestore):**
- `articles/{item_id}` - Filtered article data for mobile

**Code Location:** `shared/storage/`

---

### 3. Task Management System (`app/task_manager/`)

**Managers:**

**ArchiverTaskManager**
- Receives archive requests from API
- Creates BatchTask with items
- Dispatches to in-memory queue
- Coordinates archiver execution
- Updates database with results

**SummarizationTaskManager**
- Triggered when readability archiver succeeds
- Generates AI summaries (title, excerpt, summary)
- Extracts entities and keywords
- Updates database with summaries

**CleanupTaskManager**
- Monitors local storage usage
- Deletes local files after retention period
- Preserves cloud storage copies
- Enforces storage quotas

**Architecture:**
- In-memory Python `queue.Queue()` (NOT Celery/Redis currently)
- Daemon threads for background processing
- Thread-safe task coordination
- Status tracking per artifact

**Code Location:** `app/task_manager/`

---

### 4. Archiver System (`app/archivers/`)

**Base Architecture:**
- **BaseArchiver**: Abstract base with storage integration
- **archive_with_storage()**: Core method for archive + upload
- Multi-provider upload in parallel
- Atomic database updates

**Archiver Implementations:**

| Archiver | Technology | Output | Typical Size |
|----------|-----------|--------|--------------|
| `readability` | Mozilla Readability | HTML (cleaned text) | 50-500KB |
| `monolith` | Monolith CLI | Single-file HTML | 1-10MB |
| `singlefile-cli` | SingleFile CLI | Single-file HTML | 1-10MB |
| `pdf` | Playwright/Chromium | PDF | 500KB-5MB |
| `screenshot` | Playwright/Chromium | PNG | 100KB-2MB |

**Features:**
- URL rewriting (paywall bypass: Twitter → Freedium)
- Timeout handling (per archiver)
- Error recovery and retry logic
- Metadata extraction
- Storage path generation

**Code Location:** `app/archivers/`

---

### 5. Storage Providers (`shared/storage/providers/`)

**Google Cloud Storage (GCS)**
- Primary cloud storage
- Signed URL generation (time-limited downloads)
- Bucket: `gs://htbase-archives/`
- Structure: `archives/{item_id}/{archiver}/output.{ext}`

**Local Storage**
- Development/backup storage
- Retention-based cleanup
- Directory: `{data_dir}/{item_id}/{archiver}/`

**Multi-Provider Upload:**
```python
# Upload to all providers in parallel
tasks = [provider.upload(...) for provider in providers]
results = await asyncio.gather(*tasks)
```

**Code Location:** `shared/storage/providers/`

---

### 6. AI Services (`app/services/`)

**SummarizationService**
- Generates article summaries using LLM
- Extracts title, excerpt, summary, entities
- Updates `url_metadata` table
- Configurable model (OpenAI, Anthropic, etc.)

**Features:**
- Async processing (doesn't block archival)
- Fallback to metadata extraction if LLM fails
- Token limit handling
- Cost optimization

**Code Location:** `app/services/summarization_service.py`

---

## Component Architecture

```mermaid
graph TB
    Client[Client App<br/>Web/Mobile]

    subgraph API Gateway
        FastAPI[FastAPI Server]
        Auth[API Key Auth]
        RateLimit[Rate Limiter<br/>Redis]
        Routes[Route Handlers]
    end

    subgraph Database Layer
        DualDB[DualDatabaseStorage<br/>Orchestrator]
        PG[(PostgreSQL<br/>Primary)]
        FS[(Firestore<br/>Replica)]
        Filter[SyncFilter]
    end

    subgraph Task System
        ATM[ArchiverTaskManager]
        STM[SummarizationTaskManager]
        CTM[CleanupTaskManager]
        Queue[In-Memory Queue]
    end

    subgraph Archivers
        Base[BaseArchiver]
        Read[Readability]
        Mono[Monolith]
        SF[SingleFile]
        PDF[PDF]
        SS[Screenshot]
    end

    subgraph Storage
        GCS[Google Cloud Storage]
        Local[Local Storage]
    end

    subgraph AI Services
        LLM[Summarization Service<br/>OpenAI/Anthropic]
    end

    Client -->|HTTP Request| FastAPI
    FastAPI --> Auth
    Auth --> RateLimit
    RateLimit --> Routes
    Routes --> DualDB

    DualDB -->|Write| PG
    DualDB -->|Filter + Write| Filter
    Filter -->|Filtered Data| FS

    Routes -->|Enqueue| ATM
    ATM --> Queue
    Queue --> Base

    Base --> Read
    Base --> Mono
    Base --> SF
    Base --> PDF
    Base --> SS

    Read -->|Upload| GCS
    Read -->|Upload| Local
    Mono -->|Upload| GCS
    Mono -->|Upload| Local

    Read -->|Trigger| STM
    STM --> LLM
    LLM -->|Update| DualDB

    CTM -->|Delete After Retention| Local

    PG -.->|Read| Routes
    FS -.->|Mobile Reads| Client
```

---

## Communication Patterns

### 1. Request-Response Pattern (Synchronous)

**Used For:**
- Authentication
- Rate limit checks
- Database reads
- Status polling

**Example:** GET /firebase/download/{item_id}/{archiver}
```
Client → API Gateway → Database → API Gateway → Client
(all synchronous, ~50-200ms)
```

---

### 2. Request-Acknowledge-Poll Pattern (Asynchronous)

**Used For:**
- Article archival (long-running)
- Batch operations

**Flow:**
```
1. Client → POST /firebase/add-pocket-article
2. API Gateway → Database (create article) → Enqueue Task
3. API Gateway → Client (202 Accepted, task_id)
4. Client → Poll GET /tasks/{task_id}
5. Background Worker → Archive → Upload → Update Database
6. Client → Poll GET /tasks/{task_id} → Status: completed
```

**Advantages:**
- Client doesn't block waiting for archival
- Can handle long-running operations (30+ seconds)
- Fault tolerance (retry on failure)

---

### 3. Event-Driven Pattern (Internal)

**Used For:**
- Triggering summarization after readability succeeds
- Scheduling cleanup after upload completes
- Firestore sync after PostgreSQL write

**Example:**
```python
# After readability succeeds
if archiver == "readability" and status == "success":
    summarization_manager.enqueue(item_id, artifact_path)
```

**Characteristics:**
- Loosely coupled components
- Async execution (daemon threads)
- No blocking between stages

---

### 4. Dual-Write Pattern (Database)

**Used For:**
- PostgreSQL + Firestore synchronization

**Flow:**
```
1. Write to PostgreSQL (REQUIRED)
   └─ If fails: Return error, no Firestore write
2. Filter data (remove large fields)
3. Write to Firestore (BEST-EFFORT)
   └─ If fails: Log warning, continue (default mode)
```

**Failure Modes:**
- `fail_fast`: Fail entire operation if Firestore fails
- `log_and_continue`: Log warning, continue with PostgreSQL only ✅ (default)
- `queue_retry`: Queue for background retry (NOT IMPLEMENTED)

---

## Storage Strategy

### Primary Storage (PostgreSQL)

**What's Stored:**
- ALL article metadata (URLs, titles, authors, tags)
- ALL artifact data (status, paths, sizes, error messages)
- FULL text content (extracted text from readability)
- FULL summaries (AI-generated summaries, entities, keywords)
- User data (user_id, pocket_data)

**Characteristics:**
- ACID transactions
- Single source of truth
- Complete audit trail
- No data filtering

---

### Replica Storage (Firestore)

**What's Stored:**
- FILTERED metadata (see SyncFilter)
- Basic artifact status (status, gcs_path, file_size)
- Pocket data (for mobile display)
- NO text_content (too large for mobile)
- NO summaries (not needed for mobile)

**Characteristics:**
- Eventual consistency
- Mobile-optimized (smaller payloads)
- Best-effort writes
- NoSQL document model

**Filtering Rules:**
```python
ALLOWED_METADATA_FIELDS = {
    "item_id", "url", "name", "created_at", "updated_at",
    "user_id", "pocket_data"
}

POSTGRES_ONLY_FIELDS = {
    "text_content",  # Too large for mobile
    "summary",       # Not needed for mobile UI
    "excerpt",       # Pocket excerpt used instead
    "entities",      # AI-extracted, not for mobile
    "keywords"       # AI-extracted, not for mobile
}
```

---

### File Storage (Cloud + Local)

**Google Cloud Storage (Production):**
- Path: `gs://htbase-archives/archives/{item_id}/{archiver}/output.{ext}`
- Signed URLs with expiration (default: 24 hours)
- Multi-region redundancy
- CDN integration

**Local Storage (Development/Backup):**
- Path: `{data_dir}/{item_id}/{archiver}/output.{ext}`
- Retention-based cleanup (default: 7 days after successful upload)
- Used for local development
- Backup if cloud upload fails

**Upload Strategy:**
```python
# Upload to all providers in parallel
for provider in storage_providers:
    await provider.upload_artifact(local_path, cloud_path)

# If all uploads succeed → Schedule local cleanup
# If any upload fails → Keep local copy, retry later
```

---

## Task Management Architecture

### Thread Model

```mermaid
graph TB
    Main[Main Thread<br/>FastAPI Server]

    subgraph Background Threads
        AT[Archiver Thread<br/>Daemon]
        ST[Summarization Thread<br/>Daemon]
        CT[Cleanup Thread<br/>Daemon]
    end

    subgraph Queues
        AQ[Archiver Queue<br/>queue.Queue]
        SQ[Summarization Queue<br/>queue.Queue]
        CQ[Cleanup Queue<br/>queue.Queue]
    end

    Main -->|enqueue| AQ
    AQ --> AT
    AT -->|enqueue| SQ
    AT -->|enqueue| CQ
    SQ --> ST
    CQ --> CT

    AT -.->|update| DB[(Database)]
    ST -.->|update| DB
    CT -.->|delete| FS[Local Files]
```

**Thread Safety:**
- `queue.Queue()` is thread-safe (Python GIL)
- Database connections use connection pooling
- No shared mutable state between threads

---

### Task Lifecycle

**1. Task Creation**
```python
# API endpoint receives request
task = BatchTask(
    task_id=uuid4(),
    items=[BatchItem(url=url, archiver=archiver)],
    status="pending"
)
```

**2. Task Queuing**
```python
# ArchiverTaskManager.enqueue()
self.queue.put(task)
return task.task_id  # Return immediately (202 Accepted)
```

**3. Task Processing**
```python
# Background thread picks up task
while True:
    task = self.queue.get()
    for item in task.items:
        # Execute archiver
        result = archiver.archive(item.url)
        # Update database
        self.db.update_artifact_status(...)
```

**4. Status Polling**
```python
# Client polls for status
GET /tasks/{task_id}
→ Query artifacts by task_id
→ Aggregate status (pending/success/failed)
```

---

### Scalability Considerations

**Current Architecture (In-Memory Queues):**
- ✅ Simple implementation
- ✅ Low latency (no network overhead)
- ✅ Good for single-server deployments
- ❌ Not horizontally scalable
- ❌ Tasks lost on server restart
- ❌ No distributed workers

**Future Architecture (Celery/Redis):**
- ✅ Horizontally scalable (multiple workers)
- ✅ Persistent task queue (Redis)
- ✅ Task retry with backoff
- ✅ Priority queues
- ✅ Distributed locking
- ❌ Increased complexity
- ❌ Additional infrastructure (Redis, RabbitMQ)

**Migration Path:**
1. Extract task interfaces (already done with TaskManager)
2. Implement Celery backend adapter
3. Replace `queue.Queue()` with Celery tasks
4. Deploy Redis for task persistence
5. Scale workers horizontally

---

## Data Flow

### Complete Article Archival Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as API Gateway
    participant DB as Database Layer
    participant Queue as Task Queue
    participant Worker as Background Worker
    participant Archiver
    participant Storage as Cloud Storage
    participant AI as AI Service

    Client->>API: POST /firebase/add-pocket-article
    API->>API: Authenticate & Rate Limit

    API->>DB: Create Article + Metadata
    DB->>DB: Write to PostgreSQL
    DB->>DB: Filter & Write to Firestore
    DB-->>API: Success (item_id)

    API->>Queue: Enqueue Archive Task
    Queue-->>API: task_id
    API-->>Client: 202 Accepted (task_id)

    Client->>API: Poll GET /tasks/{task_id}
    API-->>Client: Status: pending

    Worker->>Queue: Dequeue Task
    Worker->>Archiver: Execute archive()
    Archiver->>Archiver: Run archiver locally
    Archiver->>Storage: Upload to GCS + Local
    Storage-->>Archiver: Upload complete

    Archiver->>DB: Update artifact status
    DB->>DB: Update PostgreSQL
    DB->>DB: Update Firestore

    alt Readability Success
        Archiver->>AI: Trigger Summarization
        AI->>AI: Generate Summary (LLM)
        AI->>DB: Update metadata
    end

    Archiver->>Worker: Schedule Cleanup
    Worker->>Worker: Delete local file (after retention)

    Client->>API: Poll GET /tasks/{task_id}
    API->>DB: Query artifact status
    DB-->>API: Status: completed
    API-->>Client: Status: completed (with download URLs)
```

---

### Read Flow (Download URL Generation)

```mermaid
sequenceDiagram
    participant Client
    participant API as API Gateway
    participant DB as PostgreSQL
    participant GCS as Google Cloud Storage

    Client->>API: GET /firebase/download/{item_id}/{archiver}
    API->>API: Authenticate & Rate Limit

    API->>DB: Find article by item_id
    DB-->>API: Article found

    API->>DB: Find successful artifact for archiver
    DB-->>API: Artifact found (with gcs_path)

    API->>GCS: Generate signed URL (24h expiration)
    GCS-->>API: Signed URL with token

    API-->>Client: {download_url, expires_in, gcs_path}

    Client->>GCS: Download file (using signed URL)
    GCS-->>Client: File content
```

**Performance:**
- Signed URL generation: ~50ms
- No actual file transfer through API (client downloads directly from GCS)
- CDN acceleration for global distribution

---

## Deployment Architecture

### Single-Server Deployment (Current)

```mermaid
graph TB
    subgraph Server[Single Server]
        subgraph Docker[Docker Compose]
            API[API Gateway<br/>FastAPI]
            PG[(PostgreSQL<br/>Database)]
            Redis[(Redis<br/>Rate Limiting)]
        end

        Workers[Background Workers<br/>Daemon Threads]
        Local[Local Storage<br/>/data/archives]
    end

    GCS[Google Cloud Storage<br/>Bucket]
    FS[Firebase Firestore<br/>Mobile Replica]

    Internet[Internet] --> API
    API --> PG
    API --> Redis
    API --> Workers
    Workers --> Local
    Workers --> GCS
    Workers --> FS

    Mobile[Mobile App] --> FS
    Mobile --> GCS
```

**Components:**
- **API Gateway**: FastAPI (Uvicorn/Gunicorn)
- **Database**: PostgreSQL 15
- **Cache/Rate Limit**: Redis 7
- **Storage**: Local filesystem + GCS
- **Mobile Replica**: Firebase Firestore

**Deployment Method:**
- Docker Compose for local development
- Single VM for production (DigitalOcean, AWS EC2, GCP Compute)
- Traefik for reverse proxy + SSL
- Automated backups (PostgreSQL + local storage)

---

### Recommended Production Deployment

```mermaid
graph TB
    subgraph Load Balancer
        LB[Load Balancer<br/>Traefik/Nginx]
    end

    subgraph API Tier
        API1[API Gateway 1]
        API2[API Gateway 2]
        API3[API Gateway 3]
    end

    subgraph Worker Tier
        W1[Worker 1]
        W2[Worker 2]
        W3[Worker 3]
    end

    subgraph Data Tier
        PG[(PostgreSQL<br/>Primary + Replicas)]
        Redis[(Redis<br/>Cluster)]
        Queue[(Task Queue<br/>Celery + Redis)]
    end

    subgraph External
        GCS[Google Cloud Storage]
        FS[Firebase Firestore]
        CDN[CDN<br/>Cloudflare]
    end

    Internet[Internet] --> CDN
    CDN --> LB
    LB --> API1
    LB --> API2
    LB --> API3

    API1 --> PG
    API2 --> PG
    API3 --> PG

    API1 --> Redis
    API2 --> Redis
    API3 --> Redis

    API1 --> Queue
    API2 --> Queue
    API3 --> Queue

    Queue --> W1
    Queue --> W2
    Queue --> W3

    W1 --> GCS
    W2 --> GCS
    W3 --> GCS

    W1 --> FS
    W2 --> FS
    W3 --> FS
```

**Improvements:**
- **Horizontal Scaling**: Multiple API servers behind load balancer
- **Worker Separation**: Dedicated worker tier (CPU-intensive archiving)
- **Persistent Queue**: Celery + Redis for task distribution
- **Database Replication**: PostgreSQL primary + read replicas
- **CDN**: Cloudflare for static assets and GCS file downloads
- **Monitoring**: Prometheus + Grafana
- **Logging**: ELK stack or Loki

---

## Scalability Considerations

### Current Bottlenecks

**1. In-Memory Task Queue**
- **Problem**: Single server, tasks lost on restart
- **Solution**: Migrate to Celery + Redis
- **Impact**: Enables horizontal scaling of workers

**2. Single Database Connection**
- **Problem**: Connection pool exhaustion under load
- **Solution**: Increase pool size, add read replicas
- **Impact**: Better read performance, reduced primary load

**3. Synchronous Archiver Execution**
- **Problem**: Workers blocked during long-running archives
- **Solution**: Already async (daemon threads), but could use multiprocessing
- **Impact**: Better CPU utilization

**4. Firestore Write Latency**
- **Problem**: Firestore writes add latency to request
- **Solution**: Already async (best-effort), could make fully async with queue
- **Impact**: Faster API responses

---

### Scaling Strategy

**Vertical Scaling (Current):**
- ✅ Increase CPU/RAM for single server
- ✅ Add more worker threads
- ✅ Optimize database queries
- Limit: Single server capacity (~100 req/min sustained)

**Horizontal Scaling (Future):**
- ✅ Multiple API servers behind load balancer
- ✅ Dedicated worker tier (scale independently)
- ✅ PostgreSQL read replicas
- ✅ Redis cluster for rate limiting
- ✅ Celery workers distributed across nodes
- Target: 1000+ req/min sustained

**Performance Targets:**

| Metric | Current | Target |
|--------|---------|--------|
| API Response Time (p95) | 200ms | 100ms |
| Archive Processing Time | 30-60s | 20-40s |
| Concurrent Archives | 10-20 | 100+ |
| Database Connections | 20 | 100+ |
| Storage Upload Speed | 5MB/s | 50MB/s |

---

## Configuration

### Environment Variables

**API Gateway:**
```bash
API_KEYS=htbase_live_key1,htbase_test_key2
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

**Database:**
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/htbase
ENABLE_DUAL_PERSISTENCE=true
DUAL_WRITE_FAILURE_MODE=log_and_continue
FIRESTORE_PROJECT_ID=your-firebase-project
FIRESTORE_CREDENTIALS_PATH=/path/to/credentials.json
```

**Storage:**
```bash
GCS_BUCKET=htbase-archives
STORAGE_PROVIDERS=gcs,local
LOCAL_STORAGE_DIR=/data/archives
CLEANUP_RETENTION_DAYS=7
```

**Task Management:**
```bash
MAX_CONCURRENT_ARCHIVES=10
ARCHIVER_TIMEOUT_SECONDS=120
ENABLE_SUMMARIZATION=true
SUMMARIZATION_MODEL=gpt-4o-mini
```

---

## Related Documentation

- **[Firebase API Flow](./FIREBASE_API_FLOW.md)** - Detailed endpoint documentation
- **[Request Flow Complete](./REQUEST_FLOW_COMPLETE.md)** - End-to-end request tracing
- **[Dual Database Architecture](./DUAL_DATABASE_ARCHITECTURE.md)** - Database pattern details
- **[Sequence Diagrams](./diagrams/SEQUENCE_DIAGRAMS.md)** - Visual flow diagrams

---

## Code References

**Key Files:**
- `services/api-gateway/app/main.py` - FastAPI application setup
- `services/api-gateway/app/routes/firebase.py` - Firebase endpoints
- `shared/storage/dual_database_storage.py` - Database orchestrator
- `app/task_manager/archiver.py` - Task management
- `app/archivers/base.py` - Base archiver implementation
- `core/config.py` - Configuration management
- `server.py` - Server initialization

**Configuration:**
- `.env.example` - Environment variable template
- `docker-compose.yml` - Development deployment
- `docker-compose.prod.yml` - Production deployment
