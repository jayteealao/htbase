# HT Base Microservices Rearchitecture Plan

## Executive Summary

This document outlines the migration of HT Base from a monolithic FastAPI application to a distributed microservices architecture running on Google Cloud Run, using Celery for task orchestration and Redis for message brokering.

---

## Current Architecture Analysis

### Monolithic Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Monolith (server.py)                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Saves     │  │   Tasks     │  │        Admin            │  │
│  │    API      │  │    API      │  │         API             │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                │
│  ┌──────▼────────────────▼─────────────────────▼──────────────┐ │
│  │                  Archiver Factory                          │ │
│  │  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌─────┐ ┌──────┐│ │
│  │  │SingleFile │ │ Monolith │ │Readability│ │ PDF │ │Screen││ │
│  │  └───────────┘ └──────────┘ └───────────┘ └─────┘ └──────┘│ │
│  └────────────────────────────────────────────────────────────┘ │
│         │                                                       │
│  ┌──────▼─────────────────┐  ┌────────────────────────────────┐ │
│  │ ArchiverTaskManager    │  │ SummarizationTaskManager       │ │
│  │ (queue.Queue + Thread) │  │ (queue.Queue + Thread)         │ │
│  └────────────────────────┘  └────────────────────────────────┘ │
│         │                           │                           │
│  ┌──────▼───────────────────────────▼─────────────────────────┐ │
│  │              Storage Layer                                 │ │
│  │  ┌─────────────┐  ┌────────────────┐  ┌──────────────────┐│ │
│  │  │ GCS Storage │  │ Local Storage  │  │ Database Storage ││ │
│  │  └─────────────┘  └────────────────┘  │ (Postgres+Fire)  ││ │
│  │                                       └──────────────────┘│ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Current Pain Points

1. **Synchronous Blocking**: API endpoints wait up to 300s for archiver completion
2. **Single Process Bottleneck**: All work competes for one Python process
3. **Tight Coupling**: Archivers directly manage storage, database, and cleanup
4. **No Horizontal Scaling**: Can't scale individual components independently
5. **Resource Contention**: Chrome/Chromium processes compete for memory
6. **No Fault Isolation**: One archiver failure can impact others

---

## Target Architecture

### High-Level Design

```
                                    ┌─────────────────────┐
                                    │   Cloud Load        │
                                    │   Balancer          │
                                    └──────────┬──────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
           ┌────────▼────────┐       ┌─────────▼─────────┐      ┌─────────▼─────────┐
           │   API Gateway   │       │   API Gateway     │      │   API Gateway     │
           │   (Cloud Run)   │       │   (Cloud Run)     │      │   (Cloud Run)     │
           └────────┬────────┘       └───────────────────┘      └───────────────────┘
                    │                         │ (auto-scaled replicas)
                    │
        ┌───────────┴───────────────────────────────────────────┐
        │                                                       │
        ▼                                                       ▼
┌───────────────┐                                     ┌───────────────────┐
│    Redis      │◄────────────────────────────────────│  Redis Sentinel   │
│ (Cloud        │                                     │  (High Avail)     │
│  Memorystore) │                                     └───────────────────┘
└───────┬───────┘
        │
        │ Celery Task Queue
        │
        ├─────────────────────────────────────────────────────────────────────┐
        │                              │                                      │
┌───────▼───────┐             ┌────────▼────────┐                   ┌─────────▼─────────┐
│   Archive     │             │  Summarization  │                   │     Storage       │
│   Workers     │             │     Workers     │                   │     Workers       │
│  (Cloud Run)  │             │   (Cloud Run)   │                   │   (Cloud Run)     │
├───────────────┤             ├─────────────────┤                   ├───────────────────┤
│ ┌───────────┐ │             │ ┌─────────────┐ │                   │ ┌───────────────┐ │
│ │SingleFile │ │             │ │ LLM Provider│ │                   │ │ GCS Upload    │ │
│ │ Worker    │ │             │ │   Chain     │ │                   │ │    Worker     │ │
│ ├───────────┤ │             │ ├─────────────┤ │                   │ ├───────────────┤ │
│ │ Monolith  │ │             │ │   Chunker   │ │                   │ │ File Cleanup  │ │
│ │  Worker   │ │             │ ├─────────────┤ │                   │ │    Worker     │ │
│ ├───────────┤ │             │ │   Parser    │ │                   │ └───────────────┘ │
│ │Readability│ │             │ └─────────────┘ │                   └───────────────────┘
│ │  Worker   │ │             └─────────────────┘
│ ├───────────┤ │
│ │PDF/Screen │ │
│ │  Worker   │ │
│ └───────────┘ │
└───────────────┘
        │
        └──────────────────────────────────────────────────────────────────┐
                                                                           │
                    ┌──────────────────────────────────────────────────────┤
                    │                            │                         │
           ┌────────▼────────┐          ┌────────▼────────┐     ┌──────────▼──────────┐
           │   PostgreSQL    │          │   Firestore     │     │    GCS Bucket       │
           │   (Cloud SQL)   │          │   (Optional)    │     │   (Archive Files)   │
           └─────────────────┘          └─────────────────┘     └─────────────────────┘
```

---

## Microservices Breakdown

### 1. API Gateway Service

**Purpose**: HTTP entry point, request routing, authentication, rate limiting

**Deployment**: Cloud Run (auto-scaling, min 1 instance)

**Responsibilities**:
- Accept HTTP requests from clients
- Validate input and authenticate requests
- Enqueue tasks to Celery
- Serve task status queries
- Serve archived file downloads (proxy to GCS or delegate)

**Technology**:
- FastAPI (lightweight, existing knowledge)
- Celery client (task submission only)

**Endpoints**:
```
POST /api/v2/archive                  → Enqueue archive task
POST /api/v2/archive/batch            → Enqueue batch archive tasks
GET  /api/v2/tasks/{task_id}          → Get task status
GET  /api/v2/archives/{id}/{archiver} → Retrieve archive file
GET  /api/v2/archives/{id}/all        → Download all artifacts
POST /api/v2/summarize/{id}           → Trigger summarization
GET  /api/v2/summaries/{id}           → Get article summary
GET  /api/v2/health                   → Health check
```

**Code Structure**:
```
services/
  api-gateway/
    ├── Dockerfile
    ├── requirements.txt
    ├── app/
    │   ├── main.py              # FastAPI app
    │   ├── config.py            # Settings
    │   ├── routers/
    │   │   ├── archive.py       # Archive endpoints
    │   │   ├── tasks.py         # Task status
    │   │   ├── files.py         # File serving
    │   │   └── health.py        # Health checks
    │   ├── schemas/
    │   │   ├── requests.py      # Pydantic models
    │   │   └── responses.py
    │   └── tasks/
    │       └── client.py        # Celery task client
    └── tests/
```

---

### 2. Archive Worker Service

**Purpose**: Execute archiving operations (SingleFile, Monolith, Readability, PDF, Screenshot)

**Deployment**: Cloud Run (CPU-intensive, higher memory, longer timeout)

**Responsibilities**:
- Consume archive tasks from Celery queue
- Run archiver CLIs (via CommandRunner pattern)
- Enqueue storage upload tasks upon completion
- Enqueue summarization tasks for readability output
- Update task status in Redis

**Technology**:
- Celery worker
- Chrome/Chromium (installed in container)
- SingleFile, Monolith binaries

**Container Requirements**:
- Base: Python 3.11 + Chromium
- Memory: 2-4GB (Chrome is memory-hungry)
- CPU: 2+ vCPUs
- Timeout: 15 minutes max (Cloud Run limit)

**Task Definitions**:
```python
# Celery tasks
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def archive_url(self, task_id: str, item_id: str, url: str, archiver: str):
    """Archive a single URL with specified archiver."""

@celery.task(bind=True)
def archive_batch(self, task_id: str, items: list[dict], archivers: list[str]):
    """Archive multiple URLs with multiple archivers."""
```

**Code Structure**:
```
services/
  archive-worker/
    ├── Dockerfile              # Chrome + SingleFile + Monolith
    ├── requirements.txt
    ├── app/
    │   ├── celery_app.py       # Celery configuration
    │   ├── config.py
    │   ├── tasks/
    │   │   ├── archive.py      # Archive task definitions
    │   │   └── callbacks.py    # Success/failure callbacks
    │   ├── archivers/
    │   │   ├── base.py         # BaseArchiver (simplified)
    │   │   ├── singlefile.py
    │   │   ├── monolith.py
    │   │   ├── readability.py
    │   │   ├── pdf.py
    │   │   └── screenshot.py
    │   ├── core/
    │   │   ├── command_runner.py
    │   │   └── chromium.py
    │   └── models/
    │       └── results.py      # ArchiveResult dataclass
    └── tests/
```

---

### 3. Summarization Worker Service

**Purpose**: Generate LLM summaries from archived content

**Deployment**: Cloud Run (GPU optional, network-intensive for API calls)

**Responsibilities**:
- Consume summarization tasks from Celery queue
- Fetch article text from database
- Chunk text and generate summaries
- Parse LLM responses
- Store summaries in database

**Technology**:
- Celery worker
- LLM provider clients (HuggingFace TGI, OpenAI)
- httpx for async HTTP calls

**Task Definitions**:
```python
@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def summarize_article(self, task_id: str, archived_url_id: int, item_id: str):
    """Generate summary for an archived article."""

@celery.task(bind=True)
def summarize_batch(self, task_id: str, article_ids: list[int]):
    """Batch summarization for multiple articles."""
```

**Code Structure**:
```
services/
  summarization-worker/
    ├── Dockerfile
    ├── requirements.txt
    ├── app/
    │   ├── celery_app.py
    │   ├── config.py
    │   ├── tasks/
    │   │   └── summarize.py
    │   ├── providers/
    │   │   ├── base.py
    │   │   ├── huggingface.py
    │   │   ├── openai.py
    │   │   └── chain.py
    │   ├── pipeline/
    │   │   ├── chunker.py
    │   │   ├── prompts.py
    │   │   └── parser.py
    │   └── db/
    │       └── client.py       # Database operations
    └── tests/
```

---

### 4. Storage Worker Service

**Purpose**: Handle file uploads to GCS and cleanup operations

**Deployment**: Cloud Run (network I/O intensive)

**Responsibilities**:
- Consume upload tasks from Celery queue
- Upload files to GCS with compression
- Update database with storage metadata
- Handle file cleanup after successful uploads
- Generate signed URLs when requested

**Technology**:
- Celery worker
- Google Cloud Storage client
- gzip compression

**Task Definitions**:
```python
@celery.task(bind=True, max_retries=5, default_retry_delay=10)
def upload_to_gcs(self, task_id: str, local_path: str, gcs_path: str,
                  item_id: str, archiver: str, compress: bool = True):
    """Upload a file to GCS."""

@celery.task(bind=True)
def cleanup_local_files(self, item_id: str, paths: list[str]):
    """Clean up local temporary files."""

@celery.task(bind=True)
def generate_signed_url(self, gcs_path: str, expiration: int = 3600) -> str:
    """Generate a signed URL for file access."""
```

**Code Structure**:
```
services/
  storage-worker/
    ├── Dockerfile
    ├── requirements.txt
    ├── app/
    │   ├── celery_app.py
    │   ├── config.py
    │   ├── tasks/
    │   │   ├── upload.py
    │   │   ├── cleanup.py
    │   │   └── urls.py
    │   ├── providers/
    │   │   ├── gcs.py
    │   │   └── local.py        # For development
    │   └── db/
    │       └── client.py
    └── tests/
```

---

### 5. Database Service (Optional - can be direct access)

**Purpose**: Centralized database operations and data consistency

**Deployment**: Cloud Run or direct database access from workers

**Decision Point**:
- **Option A**: Each worker connects directly to PostgreSQL/Firestore
- **Option B**: Centralized DB service with API

**Recommendation**: Start with **Option A** (direct access) for simplicity, evolve to Option B if needed.

For direct access, each worker includes:
```python
# Shared database client module
from shared.db import DatabaseClient

class DatabaseClient:
    def __init__(self, connection_string: str):
        self.engine = create_async_engine(connection_string)

    async def get_archived_url(self, item_id: str) -> ArchivedUrl
    async def update_artifact_status(self, id: int, status: str, ...)
    async def get_article_metadata(self, archived_url_id: int) -> UrlMetadata
    async def save_summary(self, archived_url_id: int, summary: ArticleSummary)
```

---

## Celery Configuration

### Celery App Setup

```python
# shared/celery_config.py
from celery import Celery

celery_app = Celery(
    'htbase',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/1',
    include=[
        'archive_worker.tasks.archive',
        'summarization_worker.tasks.summarize',
        'storage_worker.tasks.upload',
    ]
)

celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Result backend settings
    result_expires=86400,  # 24 hours

    # Task routing
    task_routes={
        'archive_worker.tasks.*': {'queue': 'archive'},
        'summarization_worker.tasks.*': {'queue': 'summarization'},
        'storage_worker.tasks.*': {'queue': 'storage'},
    },

    # Concurrency settings (per worker type)
    # Archive workers: low concurrency (Chrome is heavy)
    # Summarization workers: medium concurrency
    # Storage workers: high concurrency (I/O bound)

    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Rate limiting
    task_annotations={
        'archive_worker.tasks.archive_url': {
            'rate_limit': '10/m',  # Limit archiving rate
        },
        'summarization_worker.tasks.summarize_article': {
            'rate_limit': '30/m',  # LLM API rate limits
        },
    },

    # Visibility timeout for long-running tasks
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour for archive tasks
    },
)
```

### Queue Configuration

```python
# Queue definitions
CELERY_QUEUES = {
    'archive': {
        'exchange': 'archive',
        'routing_key': 'archive.#',
        'priority': 10,
    },
    'summarization': {
        'exchange': 'summarization',
        'routing_key': 'summarization.#',
        'priority': 5,
    },
    'storage': {
        'exchange': 'storage',
        'routing_key': 'storage.#',
        'priority': 8,
    },
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
    },
}
```

---

## Task Workflow Orchestration

### Archive Workflow (Celery Chain)

```python
from celery import chain, group, chord

def create_archive_workflow(task_id: str, item_id: str, url: str, archivers: list[str]):
    """Create a Celery workflow for archiving a URL with multiple archivers."""

    # Step 1: Archive with each archiver (can run in parallel)
    archive_tasks = group([
        archive_url.s(task_id, item_id, url, archiver)
        for archiver in archivers
    ])

    # Step 2: After all archives complete, upload results (chord callback)
    upload_callback = upload_results.s(task_id, item_id)

    # Step 3: After uploads, trigger summarization if readability succeeded
    summarize_callback = maybe_summarize.s(task_id, item_id)

    # Chain: archive_all → upload → summarize
    workflow = chain(
        archive_tasks,
        upload_callback,
        summarize_callback,
    )

    return workflow

# Alternative: Use chord for fan-out/fan-in pattern
def create_archive_workflow_v2(task_id: str, item_id: str, url: str, archivers: list[str]):
    """Use chord for parallel archive + single callback."""

    archive_group = group([
        archive_url.s(task_id, item_id, url, archiver)
        for archiver in archivers
    ])

    callback = process_archive_results.s(task_id, item_id)

    return chord(archive_group, callback)
```

### Batch Processing Workflow

```python
def create_batch_workflow(task_id: str, items: list[dict], archivers: list[str]):
    """Process a batch of URLs with all archivers."""

    # Create individual workflows for each item
    item_workflows = [
        create_archive_workflow(
            task_id=f"{task_id}-{item['item_id']}",
            item_id=item['item_id'],
            url=item['url'],
            archivers=archivers
        )
        for item in items
    ]

    # Run all item workflows in parallel
    batch_workflow = group(item_workflows)

    # Add final callback to update batch status
    batch_callback = finalize_batch.s(task_id)

    return chain(batch_workflow, batch_callback)
```

---

## Task Status Tracking

### Redis-based Status Store

```python
# shared/status.py
import redis
import json
from datetime import datetime
from enum import Enum
from typing import Optional
from dataclasses import dataclass, asdict

class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class TaskState:
    task_id: str
    status: TaskStatus
    progress: float  # 0.0 to 1.0
    message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    subtasks: Optional[dict] = None  # For batch tasks

class TaskStatusStore:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.prefix = "htbase:task:"
        self.ttl = 86400 * 7  # 7 days

    def set_status(self, task_id: str, state: TaskState):
        key = f"{self.prefix}{task_id}"
        data = asdict(state)
        data['status'] = state.status.value
        data['started_at'] = state.started_at.isoformat() if state.started_at else None
        data['completed_at'] = state.completed_at.isoformat() if state.completed_at else None
        self.redis.setex(key, self.ttl, json.dumps(data))

    def get_status(self, task_id: str) -> Optional[TaskState]:
        key = f"{self.prefix}{task_id}"
        data = self.redis.get(key)
        if not data:
            return None
        parsed = json.loads(data)
        parsed['status'] = TaskStatus(parsed['status'])
        return TaskState(**parsed)

    def update_progress(self, task_id: str, progress: float, message: str = None):
        state = self.get_status(task_id)
        if state:
            state.progress = progress
            if message:
                state.message = message
            self.set_status(task_id, state)
```

---

## Data Flow Diagrams

### Single URL Archive Flow

```
┌────────┐     POST /archive      ┌─────────────┐
│ Client │────────────────────────│ API Gateway │
└────────┘                        └──────┬──────┘
                                         │
                        ┌────────────────┴────────────────┐
                        │ 1. Validate request             │
                        │ 2. Generate task_id             │
                        │ 3. Create TaskState(PENDING)    │
                        │ 4. Enqueue archive workflow     │
                        │ 5. Return {task_id} immediately │
                        └────────────────┬────────────────┘
                                         │
    ┌────────────────────────────────────┼────────────────────────────────────┐
    │                              Redis Queue                                 │
    └────────────────────────────────────┼────────────────────────────────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────────┐
            │                            │                                │
   ┌────────▼────────┐         ┌─────────▼────────┐             ┌─────────▼────────┐
   │ Archive Worker  │         │ Archive Worker   │             │ Archive Worker   │
   │ (SingleFile)    │         │ (Monolith)       │             │ (Readability)    │
   └────────┬────────┘         └─────────┬────────┘             └─────────┬────────┘
            │                            │                                │
            │         Archive Results (local files)                       │
            └───────────────────────────┬┬────────────────────────────────┘
                                        ││
                                        ▼▼
                              ┌─────────────────────┐
                              │   Storage Worker    │
                              │   (GCS Upload)      │
                              └──────────┬──────────┘
                                         │
                           ┌─────────────┴─────────────┐
                           │                           │
                  ┌────────▼────────┐       ┌──────────▼──────────┐
                  │   GCS Bucket    │       │    PostgreSQL       │
                  │   (files)       │       │    (metadata)       │
                  └─────────────────┘       └─────────────────────┘
                                                      │
                                        ┌─────────────┴─────────────┐
                                        │  If readability success   │
                                        └─────────────┬─────────────┘
                                                      │
                                       ┌──────────────▼──────────────┐
                                       │   Summarization Worker     │
                                       │   (LLM API calls)          │
                                       └──────────────┬──────────────┘
                                                      │
                                       ┌──────────────▼──────────────┐
                                       │   PostgreSQL                │
                                       │   (summaries)               │
                                       └─────────────────────────────┘
```

### Task Status Polling Flow

```
┌────────┐   GET /tasks/{id}    ┌─────────────┐    GET     ┌───────────┐
│ Client │──────────────────────│ API Gateway │────────────│   Redis   │
└────┬───┘                      └──────┬──────┘            └─────┬─────┘
     │                                 │                         │
     │                                 │◄────────────────────────┤
     │                                 │   TaskState JSON        │
     │                                 │                         │
     │◄────────────────────────────────┤                         │
     │  {                              │                         │
     │    "task_id": "...",            │                         │
     │    "status": "processing",      │                         │
     │    "progress": 0.6,             │                         │
     │    "subtasks": {...}            │                         │
     │  }                              │                         │
```

---

## Infrastructure Components

### Google Cloud Services

| Component | GCP Service | Configuration |
|-----------|-------------|---------------|
| API Gateway | Cloud Run | Min: 1, Max: 10, 512MB RAM |
| Archive Workers | Cloud Run | Min: 0, Max: 20, 4GB RAM, 15min timeout |
| Summarization Workers | Cloud Run | Min: 0, Max: 10, 1GB RAM |
| Storage Workers | Cloud Run | Min: 0, Max: 10, 512MB RAM |
| Message Broker | Memorystore (Redis) | 1GB, Standard tier |
| Primary Database | Cloud SQL (PostgreSQL) | db-custom-2-4096 |
| File Storage | Cloud Storage | Standard class |
| Secrets | Secret Manager | API keys, credentials |
| Logging | Cloud Logging | Structured logs |
| Monitoring | Cloud Monitoring | Custom metrics, alerts |

### Container Images

```dockerfile
# Base image with common dependencies
# services/base/Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY shared/ /app/shared/

# Archive worker with Chrome
# services/archive-worker/Dockerfile
FROM htbase-base:latest

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

# Install SingleFile CLI
RUN npm install -g single-file-cli

# Install Monolith
RUN curl -L https://github.com/Y2Z/monolith/releases/download/v2.8.1/monolith-gnu-linux-x86_64 \
    -o /usr/local/bin/monolith && chmod +x /usr/local/bin/monolith

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

CMD ["celery", "-A", "app.celery_app", "worker", "-Q", "archive", "-c", "2"]
```

---

## Shared Module Structure

### Shared Python Package

```
shared/
├── __init__.py
├── celery_config.py      # Celery app configuration
├── config.py             # Common settings
├── status.py             # TaskStatusStore
├── models/
│   ├── __init__.py
│   ├── tasks.py          # Task-related dataclasses
│   ├── archive.py        # ArchiveResult, etc.
│   └── database.py       # ORM models (if shared)
├── db/
│   ├── __init__.py
│   ├── client.py         # Async database client
│   └── repositories.py   # Repository pattern
├── storage/
│   ├── __init__.py
│   ├── gcs.py            # GCS client wrapper
│   └── signed_urls.py    # URL generation
└── utils/
    ├── __init__.py
    ├── logging.py        # Structured logging
    └── retry.py          # Retry decorators
```

---

## Migration Strategy

### Phase 1: Infrastructure Setup (Week 1)

1. **Set up Redis on Memorystore**
   - Create Redis instance
   - Configure VPC connector for Cloud Run
   - Test connectivity

2. **Create shared module package**
   - Extract common code from monolith
   - Set up package publishing (Artifact Registry or pip install from git)

3. **Create base Docker images**
   - Base image with common dependencies
   - Archive worker image with Chrome

### Phase 2: API Gateway Migration (Week 2)

1. **Create API Gateway service**
   - Port existing FastAPI routers
   - Replace synchronous archiver calls with Celery task submission
   - Implement task status endpoints

2. **Set up Celery client**
   - Configure task submission
   - Implement status store integration

3. **Deploy and test**
   - Deploy to Cloud Run
   - Test with mock workers

### Phase 3: Archive Worker Migration (Week 3)

1. **Extract archiver code**
   - Simplify BaseArchiver (remove storage logic)
   - Create Celery task wrappers
   - Handle local file management

2. **Implement task callbacks**
   - On success: enqueue storage upload
   - On failure: update status, handle retries

3. **Deploy and test**
   - Test each archiver independently
   - Test parallel execution

### Phase 4: Storage Worker Migration (Week 4)

1. **Extract storage code**
   - Port GCS upload logic
   - Implement compression
   - Database updates

2. **Implement cleanup tasks**
   - Local file cleanup
   - Failed upload handling

3. **Deploy and test**
   - End-to-end archive → upload flow
   - Verify GCS uploads

### Phase 5: Summarization Worker Migration (Week 5)

1. **Extract summarization code**
   - Port provider chain
   - Port chunking and parsing logic
   - Create Celery tasks

2. **Integrate with archive workflow**
   - Trigger on readability success
   - Handle LLM rate limits

3. **Deploy and test**
   - Test with various article sizes
   - Verify database persistence

### Phase 6: Integration and Cutover (Week 6)

1. **Full integration testing**
   - End-to-end batch processing
   - Error handling scenarios
   - Performance testing

2. **Monitoring and alerting**
   - Set up Cloud Monitoring dashboards
   - Configure alerts

3. **Gradual traffic migration**
   - Route 10% traffic to new system
   - Monitor and increase
   - Full cutover

---

## API Contract Changes

### Current API (Synchronous)

```yaml
# Current: Blocks until archive complete
POST /saves/{archiver}
Request:
  url: string
  item_id: string (optional)
Response: (after up to 300s)
  success: boolean
  path: string
  ...
```

### New API (Asynchronous)

```yaml
# New: Returns immediately with task_id
POST /api/v2/archive
Request:
  url: string
  item_id: string (optional)
  archivers: string[] (default: all)
Response: (immediate)
  task_id: string
  status: "pending"
  status_url: string  # /api/v2/tasks/{task_id}

# Poll for status
GET /api/v2/tasks/{task_id}
Response:
  task_id: string
  status: "pending" | "processing" | "success" | "failed"
  progress: number (0.0-1.0)
  subtasks:
    singlefile: {status, progress, result}
    monolith: {status, progress, result}
    ...
  created_at: datetime
  completed_at: datetime (if complete)

# Webhook notification (optional future enhancement)
POST /api/v2/archive
Request:
  url: string
  webhook_url: string  # Called on completion
```

### Backward Compatibility

Provide a compatibility endpoint that mimics synchronous behavior:

```yaml
# Compatibility endpoint (deprecated)
POST /api/v2/archive/sync
Request:
  url: string
  timeout: number (default: 300)
Response: (blocks until complete or timeout)
  # Same as current /saves/{archiver} response

Implementation:
  1. Submit task
  2. Poll status until complete or timeout
  3. Return result
```

---

## Configuration Management

### Environment Variables per Service

```bash
# API Gateway
REDIS_URL=redis://10.0.0.5:6379
DATABASE_URL=postgresql://...
GCS_BUCKET=htbase-archives
API_RATE_LIMIT=100/minute
CORS_ORIGINS=https://app.htbase.com

# Archive Worker
REDIS_URL=redis://10.0.0.5:6379
DATABASE_URL=postgresql://...
CHROMIUM_PATH=/usr/bin/chromium
SINGLEFILE_PATH=/usr/local/bin/single-file
MONOLITH_PATH=/usr/local/bin/monolith
ARCHIVE_TIMEOUT=300
WORKER_CONCURRENCY=2

# Summarization Worker
REDIS_URL=redis://10.0.0.5:6379
DATABASE_URL=postgresql://...
LLM_PROVIDER=huggingface
HUGGINGFACE_API_URL=https://...
HUGGINGFACE_API_KEY=...
OPENAI_API_KEY=...
WORKER_CONCURRENCY=5

# Storage Worker
REDIS_URL=redis://10.0.0.5:6379
DATABASE_URL=postgresql://...
GCS_BUCKET=htbase-archives
GCS_PROJECT_ID=htbase-project
WORKER_CONCURRENCY=10
```

### Secret Management

```yaml
# Use Google Secret Manager
secrets:
  - name: database-password
    secret: htbase-db-password
    version: latest
  - name: huggingface-api-key
    secret: htbase-hf-api-key
    version: latest
  - name: openai-api-key
    secret: htbase-openai-key
    version: latest
```

---

## Monitoring and Observability

### Metrics to Track

```python
# Celery task metrics
celery_task_submitted_total{task, queue}
celery_task_completed_total{task, queue, status}
celery_task_duration_seconds{task, queue}
celery_task_retries_total{task, queue}

# Archiver-specific metrics
archive_duration_seconds{archiver}
archive_success_total{archiver}
archive_failure_total{archiver, error_type}
archive_file_size_bytes{archiver}

# Storage metrics
gcs_upload_duration_seconds
gcs_upload_bytes_total
gcs_upload_errors_total{error_type}

# Summarization metrics
summarization_duration_seconds{provider}
summarization_tokens_used{provider}
summarization_errors_total{provider, error_type}

# Queue metrics
redis_queue_length{queue}
redis_queue_oldest_message_age_seconds{queue}
```

### Logging Structure

```python
# Structured logging with correlation
import structlog

logger = structlog.get_logger()

logger.info(
    "archive_started",
    task_id=task_id,
    item_id=item_id,
    url=url,
    archiver=archiver,
)

logger.info(
    "archive_completed",
    task_id=task_id,
    item_id=item_id,
    archiver=archiver,
    duration_seconds=duration,
    file_size_bytes=size,
    exit_code=exit_code,
)
```

### Alerting Rules

```yaml
alerts:
  - name: ArchiveQueueBacklog
    condition: redis_queue_length{queue="archive"} > 100
    for: 5m
    severity: warning

  - name: ArchiveWorkerErrors
    condition: rate(archive_failure_total[5m]) > 0.1
    for: 5m
    severity: critical

  - name: SummarizationLatency
    condition: histogram_quantile(0.95, summarization_duration_seconds) > 60
    for: 10m
    severity: warning

  - name: GCSUploadFailures
    condition: rate(gcs_upload_errors_total[5m]) > 0.05
    for: 5m
    severity: critical
```

---

## Cost Estimation

### Cloud Run Pricing (Estimated Monthly)

| Service | vCPU | Memory | Requests/day | Monthly Cost |
|---------|------|--------|--------------|--------------|
| API Gateway | 1 | 512MB | 10,000 | ~$15 |
| Archive Workers | 2 | 4GB | 1,000 | ~$50 |
| Summarization Workers | 1 | 1GB | 500 | ~$10 |
| Storage Workers | 1 | 512MB | 2,000 | ~$5 |

### Other Services

| Service | Tier | Monthly Cost |
|---------|------|--------------|
| Memorystore (Redis) | Basic 1GB | ~$35 |
| Cloud SQL (PostgreSQL) | db-custom-2-4096 | ~$70 |
| Cloud Storage | Standard (100GB) | ~$2 |
| Networking | VPC Connector | ~$10 |

**Estimated Total: ~$200/month** (at moderate usage)

---

## Directory Structure (Final)

```
htbase/
├── services/
│   ├── api-gateway/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── routers/
│   │   │   ├── schemas/
│   │   │   └── tasks/
│   │   └── tests/
│   │
│   ├── archive-worker/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── celery_app.py
│   │   │   ├── tasks/
│   │   │   ├── archivers/
│   │   │   └── core/
│   │   └── tests/
│   │
│   ├── summarization-worker/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app/
│   │   │   ├── celery_app.py
│   │   │   ├── tasks/
│   │   │   ├── providers/
│   │   │   └── pipeline/
│   │   └── tests/
│   │
│   └── storage-worker/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── app/
│       │   ├── celery_app.py
│       │   ├── tasks/
│       │   └── providers/
│       └── tests/
│
├── shared/
│   ├── pyproject.toml
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── celery_config.py
│   │   ├── config.py
│   │   ├── status.py
│   │   ├── models/
│   │   ├── db/
│   │   ├── storage/
│   │   └── utils/
│   └── tests/
│
├── infrastructure/
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── cloud_run.tf
│   │   ├── redis.tf
│   │   ├── cloudsql.tf
│   │   └── gcs.tf
│   │
│   └── kubernetes/  # Alternative to Cloud Run
│       ├── api-gateway/
│       ├── archive-worker/
│       └── ...
│
├── docker-compose.yml          # Local development
├── docker-compose.override.yml # Local overrides
├── cloudbuild.yaml             # CI/CD pipeline
└── README.md
```

---

## Deployment Profiles

This section covers deployment configurations for different environments.

### Profile 1: VPS / Docker Compose (Self-Hosted)

For VPS or bare-metal deployments, use Docker Compose with all services running on a single machine or small cluster.

**File**: `docker-compose.microservices.yml`

```bash
# Start all services
docker compose -f docker-compose.microservices.yml up -d

# Start with monitoring (Flower + Redis Commander)
docker compose -f docker-compose.microservices.yml --profile monitoring up -d

# Start with SSL reverse proxy
docker compose -f docker-compose.microservices.yml --profile proxy up -d

# Scale specific workers
docker compose -f docker-compose.microservices.yml up -d --scale archive-worker-singlefile=3
```

**Architecture on VPS**:
```
┌─────────────────────────────────────────────────────────────────┐
│                         VPS / Server                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Caddy     │  │   Redis     │  │      PostgreSQL         │  │
│  │  (proxy)    │  │  (queue)    │  │      (database)         │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                │
│  ┌──────▼────────────────▼─────────────────────▼──────────────┐ │
│  │                    Docker Network                          │ │
│  └────────────────────────────────────────────────────────────┘ │
│         │                                                       │
│  ┌──────▼──────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │ API Gateway │  │ Archive Workers│  │ Storage/Summary     │  │
│  │  (FastAPI)  │  │ (5 containers) │  │    Workers          │  │
│  └─────────────┘  └────────────────┘  └─────────────────────┘  │
│                                                                 │
│  Local Volumes:  /data/artifacts  /data/postgres  /data/redis  │
└─────────────────────────────────────────────────────────────────┘
```

**Configuration**:
- Copy `.env.microservices.example` to `.env.microservices`
- Set `STORAGE_PROVIDER=local` for local-only storage, or configure GCS
- Mount `/data/artifacts` for persistent archive storage
- Configure worker concurrency based on available RAM

**Resource Requirements (Minimum)**:
| Component | CPU | RAM |
|-----------|-----|-----|
| API Gateway | 0.5 | 512MB |
| Archive Workers (5) | 4 | 12GB |
| Summarization Worker | 0.5 | 512MB |
| Storage Worker | 0.5 | 256MB |
| Redis | 0.25 | 512MB |
| PostgreSQL | 0.5 | 1GB |
| **Total** | **6.25** | **~15GB** |

---

### Profile 2: Kubernetes / Cloud Run (Managed)

For production deployments on GCP, use Terraform to provision Cloud Run services with Memorystore Redis and Cloud SQL PostgreSQL.

**Files**: `infrastructure/terraform/`

```bash
cd infrastructure/terraform

# Initialize Terraform
terraform init

# Plan deployment
terraform plan -var-file="environments/production.tfvars"

# Apply
terraform apply -var-file="environments/production.tfvars"
```

**Architecture on GCP**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    Google Cloud Platform                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────┐        ┌─────────────────────────────┐   │
│   │  Cloud Load     │        │     Artifact Registry       │   │
│   │  Balancer       │        │     (Container Images)      │   │
│   └────────┬────────┘        └─────────────────────────────┘   │
│            │                                                    │
│   ┌────────▼────────┐                                          │
│   │   Cloud Run     │◄─── Auto-scaling (0-N instances)         │
│   │   API Gateway   │                                          │
│   └────────┬────────┘                                          │
│            │                                                    │
│   ┌────────▼────────┐    ┌─────────────────────────────────┐   │
│   │   VPC           │    │        Memorystore              │   │
│   │   Connector     │───►│        (Redis)                  │   │
│   └────────┬────────┘    └─────────────────────────────────┘   │
│            │                                                    │
│   ┌────────▼────────────────────────────────────────────────┐  │
│   │              Cloud Run Workers (Auto-scaled)            │  │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │  │
│   │  │SingleFile│ │ Monolith │ │   PDF    │ │ Screenshot │ │  │
│   │  │ 0-20     │ │  0-20    │ │  0-10    │ │   0-10     │ │  │
│   │  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │  │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐                │  │
│   │  │Readability│ │ Summary │ │ Storage  │                │  │
│   │  │  0-20    │ │  0-10    │ │  0-15    │                │  │
│   │  └──────────┘ └──────────┘ └──────────┘                │  │
│   └─────────────────────────────────────────────────────────┘  │
│            │                                                    │
│   ┌────────▼────────┐    ┌─────────────────────────────────┐   │
│   │   Cloud SQL     │    │     Cloud Storage               │   │
│   │   (PostgreSQL)  │    │     (Archives Bucket)           │   │
│   └─────────────────┘    └─────────────────────────────────┘   │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                   Secret Manager                        │  │
│   │   (DB Password, API Keys)                               │  │
│   └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features**:
- **Scale to Zero**: Workers scale down when idle, reducing costs
- **Auto-scaling**: Up to 20 instances per worker type based on queue depth
- **Managed Services**: Redis and PostgreSQL fully managed by GCP
- **VPC Connector**: Secure private networking between services
- **Secret Manager**: Secure credential storage

**Terraform Resources Created**:
| Resource | Purpose |
|----------|---------|
| `google_redis_instance` | Celery broker and result backend |
| `google_sql_database_instance` | PostgreSQL database |
| `google_storage_bucket` | Archive file storage |
| `google_cloud_run_v2_service` | API Gateway and workers |
| `google_vpc_access_connector` | Private network access |
| `google_secret_manager_secret` | API keys and passwords |

---

### Profile 3: Local Development

For local development and testing, use the development override which:
- Uses a single combined archive worker
- Enables hot-reload for code changes
- Uses mock LLM provider (no API costs)
- Disables compression for faster iteration
- Includes pgAdmin for database management

**Files**: `docker-compose.local.yml`

```bash
# Start local development environment
docker compose -f docker-compose.microservices.yml -f docker-compose.local.yml up

# Start specific services for focused development
docker compose -f docker-compose.microservices.yml -f docker-compose.local.yml up api-gateway archive-worker

# Run with real LLM provider
LLM_PROVIDER=openai docker compose -f docker-compose.microservices.yml -f docker-compose.local.yml up
```

**Local Development Stack**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    Local Development                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Redis     │  │  PostgreSQL │  │       pgAdmin           │ │
│  │   :6379     │  │    :5432    │  │        :5050            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 API Gateway                             │   │
│  │                   :8080                                 │   │
│  │              (hot-reload enabled)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │          Combined Archive Worker                        │   │
│  │   (handles all queues: singlefile, monolith, etc.)     │   │
│  │              (hot-reload enabled)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────┐   │
│  │ Summarization│  │    Storage    │  │      Flower       │   │
│  │    Worker    │  │    Worker     │  │      :5555        │   │
│  │ (mock LLM)   │  │ (local only)  │  │ (task monitor)    │   │
│  └──────────────┘  └───────────────┘  └───────────────────┘   │
│                                                                 │
│  Mounted Volumes:                                               │
│    ./services/*/app → /app/app  (source code)                  │
│    ./data/artifacts → /app/artifacts  (output files)           │
└─────────────────────────────────────────────────────────────────┘
```

**Development URLs**:
| Service | URL |
|---------|-----|
| API Gateway | http://localhost:8080 |
| Flower (Celery monitor) | http://localhost:5555 |
| Redis Commander | http://localhost:8081 |
| pgAdmin | http://localhost:5050 |

**Testing Endpoints**:
```bash
# Health check
curl http://localhost:8080/health

# Submit archive task
curl -X POST http://localhost:8080/api/v2/archive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "archivers": ["readability"]}'

# Check task status
curl http://localhost:8080/api/v2/tasks/{task_id}
```

---

### Comparison of Deployment Profiles

| Feature | VPS/Docker Compose | Cloud Run/GKE | Local Dev |
|---------|-------------------|---------------|-----------|
| Cost | Fixed (VPS rental) | Pay-per-use | Free |
| Scaling | Manual | Automatic | N/A |
| Setup Time | 30 min | 1-2 hours | 5 min |
| Maintenance | Self-managed | Managed | None |
| SSL/TLS | Caddy (Let's Encrypt) | Automatic | None |
| Best For | Small-medium loads | Variable/high loads | Development |

---

### Environment Configuration Reference

| Variable | VPS | Cloud Run | Local |
|----------|-----|-----------|-------|
| `STORAGE_PROVIDER` | `gcs` or `local` | `gcs` | `local` |
| `LLM_PROVIDER` | `huggingface`/`openai` | `huggingface`/`openai` | `mock` |
| `COMPRESSION_ENABLED` | `true` | `true` | `false` |
| `CLEANUP_AFTER_UPLOAD` | `true` | `true` | `false` |
| `LOG_FORMAT` | `json` | `json` | `pretty` |
| `LOG_LEVEL` | `INFO` | `INFO` | `DEBUG` |

---

## Next Steps

1. **Review and approve this architecture plan**
2. **Prioritize which features to migrate first**
3. **Set up development environment with Docker Compose**
4. **Begin Phase 1: Infrastructure Setup**

---

## Appendix: Alternative Considerations

### A. Why Celery over Cloud Tasks?

| Feature | Celery + Redis | Cloud Tasks |
|---------|----------------|-------------|
| Task chaining | Native support | Manual orchestration |
| Priority queues | Yes | Yes |
| Rate limiting | Built-in | Built-in |
| Retry logic | Flexible | Flexible |
| Local development | Easy (Redis in Docker) | Emulator available |
| Cost | Redis hosting | Per-task pricing |
| Vendor lock-in | None | GCP-specific |

**Recommendation**: Celery provides more flexibility for complex workflows (chains, chords, groups) which are needed for the archive → upload → summarize pipeline.

### B. Alternative: Cloud Run Jobs

Cloud Run Jobs could be used for batch processing instead of Celery workers:

```yaml
# Trigger via Pub/Sub or Scheduler
apiVersion: run.googleapis.com/v1
kind: Job
metadata:
  name: archive-batch-job
spec:
  template:
    spec:
      containers:
      - image: gcr.io/project/archive-worker
        resources:
          limits:
            cpu: "2"
            memory: "4Gi"
```

**Trade-off**: Less real-time responsiveness, but simpler for scheduled batch processing.

### C. Event-Driven with Pub/Sub

Replace Celery with Cloud Pub/Sub for pure GCP solution:

```
API Gateway → Pub/Sub (archive-topic) → Cloud Run (push subscription)
```

**Trade-off**: Simpler GCP-native approach but loses Celery's workflow primitives.
