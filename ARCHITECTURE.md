# HT Base Architecture Re-design

This document outlines the re-architecture of HT Base from a monolithic FastAPI application to a distributed microservices-based system using Celery for asynchronous task processing.

## Overview

The new architecture separates the application into distinct services to allow for independent scaling, better resource management (e.g., isolating heavy Chrome dependencies), and improved fault tolerance.

### Core Components

1.  **API Gateway (`ht-api`)**:
    *   **Role**: Entry point for all HTTP requests.
    *   **Tech**: Python FastAPI.
    *   **Responsibilities**:
        *   Receives archive/summary requests.
        *   Enqueues tasks to Redis (Celery Broker).
        *   Provides status endpoints.
        *   Handles database queries for the frontend.
    *   **Dependencies**: Minimal (Python, DB drivers).

2.  **Archiver Worker - Browser (`ht-worker-browser`)**:
    *   **Role**: Handles archiving tasks that require a headless browser.
    *   **Tech**: Python Celery Worker + Headless Chrome + Node.js (SingleFile).
    *   **Tasks**: `archive_singlefile`, `archive_pdf`, `archive_screenshot`.
    *   **Dependencies**: Heavy (Chromium, Node.js, Python).

3.  **Archiver Worker - Monolith (`ht-worker-monolith`)**:
    *   **Role**: Handles archiving using the `monolith` Rust tool.
    *   **Tech**: Python Celery Worker + Monolith binary.
    *   **Tasks**: `archive_monolith`.
    *   **Dependencies**: Rust binary, Python.

4.  **Summary Worker (`ht-worker-summary`)**:
    *   **Role**: Handles AI summarization tasks.
    *   **Tech**: Python Celery Worker.
    *   **Tasks**: `generate_summary`.
    *   **Dependencies**: Python (LLM libs).

5.  **Data Storage**:
    *   **PostgreSQL**: Primary source of truth for Article metadata, Archive Artifacts, and Summaries.
    *   **Firestore**: Read replica for mobile apps (synced by the workers or a sync service).
    *   **File Storage**: Dual write to Local Disk (or PVC in Cloud Run) and Google Cloud Storage (GCS).

6.  **Message Broker**:
    *   **Redis**: Handles Celery task queues.

## Directory Structure

We will transition to a structure that supports shared code while maintaining separate deployment artifacts.

```
.
├── app/
│   ├── common/             # Shared code (Models, DB, Storage, Config)
│   ├── api/                # FastAPI application
│   ├── workers/
│   │   ├── browser/        # Browser-based worker code
│   │   ├── monolith/       # Monolith worker code
│   │   └── summary/        # Summary worker code
│   └── tasks.py            # Celery task definitions (shared interface)
├── deploy/
│   ├── docker-compose.yml  # VPS Deployment
│   ├── Dockerfile.api
│   ├── Dockerfile.worker.browser
│   ├── Dockerfile.worker.monolith
│   └── Dockerfile.worker.summary
└── requirements.txt        # Base python requirements
```

## Data Flow

1.  **Archive Request**:
    *   User -> `POST /archive {url}` -> **API Service**.
    *   **API Service** validates request and creates a pending `Article` record in Postgres.
    *   **API Service** enqueues multiple Celery tasks (Fan-out):
        *   `tasks.archive_singlefile(url, item_id)` -> Queue: `browser_queue`
        *   `tasks.archive_monolith(url, item_id)` -> Queue: `monolith_queue`
        *   `tasks.archive_pdf(url, item_id)` -> Queue: `browser_queue`
    *   **API Service** returns `202 Accepted` with `item_id`.

2.  **Task Execution (e.g., SingleFile)**:
    *   **Browser Worker** picks up `archive_singlefile` task.
    *   Worker executes SingleFile CLI using local Chrome.
    *   Worker saves output to configured Storage (GCS/Local).
    *   Worker updates `ArchiveArtifact` status in Postgres (and syncs to Firestore).
    *   If successful, Worker *may* enqueue a `tasks.generate_summary` task (Chain).

## Deployment Guides

### 1. VPS (Docker Compose)

The `docker-compose.yml` orchestrates all services on a single machine.

*   **Network**: Internal bridge network.
*   **Volumes**: Shared volume for local file storage (if needed) and DB persistence.
*   **Scaling**: `docker-compose up -d --scale worker-browser=3`

### 2. Google Cloud Run

Each component is deployed as a separate Cloud Run Service.

*   **API Service**: Triggers on HTTP.
*   **Worker Services**: Run as "background" services (using `--no-cpu-throttling` if needed, though Cloud Run sidecars or just always-on CPU is recommended for Celery workers polling Redis). *Note: Cloud Run Jobs are also an option, but for low-latency, always-running workers are better suited if the queue is active.*
*   **Redis**: Memorystore (Redis) instance in the same VPC.
*   **Postgres**: Cloud SQL instance.
*   **Storage**: GCS Bucket (primary). Local storage is ephemeral in Cloud Run, so GCS is mandatory.

## Migration Steps

1.  **Refactor**: Move core logic to `app/common`.
2.  **Define Tasks**: Create Celery tasks in `app/tasks.py`.
3.  **Containerize**: Build Docker images for each service.
4.  **Deploy**: Spin up infrastructure.
