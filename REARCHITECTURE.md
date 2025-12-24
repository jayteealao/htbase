# htbase rearchitecture (cloud-agnostic)

This document turns the previous high-level proposal into an implementation-ready plan. It keeps the FastAPI surface and existing provider abstractions but decomposes responsibilities into small services that can run on Docker Compose (VPS), Kubernetes, or Cloud Run without code changes.

## Service architecture

### API Gateway (FastAPI)
- Exposes `/archives` and `/summaries` endpoints that **enqueue** work instead of executing archivers inline.
- Emits structured job IDs (UUIDv4) and persists a thin job record (status, timestamps, queue target) to Postgres/Firestore via the Storage API.
- Accepts callback webhooks from workers to update status and trigger follow-up actions (e.g., enqueue summary).
- Hosts minimal UI/health endpoints; no archiver binaries baked in.

### Archiver workers (Celery)
- One image per archiver type (`monolith`, `singlefile-cli`, `readability`, `pdf`, `screenshot`) reusing the `BaseArchiver` contract.
- Each worker defines a Celery task named `archive.<archiver>` bound to a queue of the same name.
- Tasks pull the original request payload (URL, options, request metadata) from the broker and:
  1. Run the archiver binary.
  2. Upload produced artifacts via the Storage API (`/files` endpoint) with idempotent keys (`{job_id}/{archiver}.{ext}`).
  3. Notify the API Gateway via callback (`/archives/{job_id}/complete`) with artifact locations and any errors.

### Summarization worker
- Celery task `summary.generate` on queue `summary` triggered by the API Gateway after an archive completes.
- Fetches artifacts through the Storage API download endpoint.
- Generates LLM summaries and writes results back through the Storage API (`/data/summaries`).
- Implements idempotency by hashing the artifact URLs + model ID; skips work if the hash already exists.

### Storage API
- FastAPI service that hides provider specifics and performs dual writes.
- Endpoints:
  - `POST /files`: accepts `provider_hint` (`gcs|local`) and streams bytes; returns canonical URI + etag.
  - `GET /files/{uri}`: proxies download to the active file provider.
  - `POST /data/archives` and `POST /data/summaries`: persist metadata first to Postgres, then asynchronously replicate to Firestore; returns record IDs.
- Applies ordering rules (Postgres-first, Firestore-best-effort) and emits metrics (`write_latency_ms`, `replica_status`).

### Redis + Celery
- Default broker/result backend; connection set via `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` env vars.
- Queue map:
  - `archive.monolith`, `archive.singlefile`, `archive.readability`, `archive.pdf`, `archive.screenshot`
  - `summary`
- Task payload schema (JSON): `{ "job_id": "<uuid>", "archiver": "monolith", "url": "...", "options": {...}, "callback_url": "https://api/archives/{job_id}/complete" }`.

## Deployment profiles

### Docker Compose (VPS/local)
- Services: `api-gateway`, `storage-api`, `redis`, one container per archiver worker, `summary-worker`.
- Bind-mount a volume for local file storage when `FILE_STORAGE_PROVIDER=local`.
- Example snippet:
  ```yaml
  services:
    redis:
      image: redis:7
    api-gateway:
      build: ./app
      environment:
        CELERY_BROKER_URL: redis://redis:6379/0
    storage-api:
      build: ./storage-api
    worker-monolith:
      build: ./workers/monolith
      environment:
        CELERY_BROKER_URL: redis://redis:6379/0
        QUEUE: archive.monolith
  ```

### Kubernetes / Cloud Run
- Reuse the same images; configure per-queue Deployments/Services (K8s) or per-queue revisions (Cloud Run).
- Use a managed Redis if available; otherwise deploy Redis in a small StatefulSet.
- Externalize secrets via K8s Secrets or Cloud Run env vars; mount Service Account credentials only for storage providers that need them.

## Migration roadmap
1. **Refactor FastAPI task managers** to publish Celery tasks instead of running archivers inline; store job metadata via Storage API.
2. **Extract archiver workers** into dedicated packages/images; wire Celery queue names and callback URLs; add health probes.
3. **Introduce Storage API** and swap direct provider calls in archivers/summarization to HTTP/gRPC client calls.
4. **Add summarization worker** with idempotent hashing and retries; trigger it from API Gateway callbacks.
5. **Harden operations**: structured logs with request IDs, metrics export (Prometheus/OpenTelemetry), and dashboards.
6. **Ship deployment artifacts**: `docker-compose.yml` profile for VPS/local, Helm charts or Terraform for Kubernetes/Cloud Run using the same env contract.

## Configuration reference (env vars)
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `FILE_STORAGE_PROVIDER` (`gcs|local`), `DATA_STORAGE_PROVIDER` (`postgres|firestore`)
- `POSTGRES_DSN`, `FIRESTORE_PROJECT_ID`, `GCS_BUCKET`, `LOCAL_STORAGE_PATH`
- `ARCHIVER_QUEUE` (per worker), `SUMMARY_QUEUE` (`summary`), `CALLBACK_BASE_URL`
- `LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`
- `SERVICE_ROLE` (`api-gateway`, `archiver-worker`, `summary-worker`, `all-in-one`) to keep a single image usable across roles
- `ARCHIVERS` (comma-separated list) to control which archiver queues a process is allowed to serve

## Acceptance criteria
- All archiving and summarization workloads leave the API Gateway process.
- Any deployment target (Docker Compose, Kubernetes, Cloud Run) can run the same images with only env-var changes.
- Dual writes remain coordinated by the Storage API with Postgres as the source of truth and Firestore as best-effort replica.
