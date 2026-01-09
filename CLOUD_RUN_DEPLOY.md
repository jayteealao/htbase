# Deploying to Google Cloud Run

This guide details how to deploy the application to Cloud Run securely, using Google's managed services for secrets and identity.

## 1. Prerequisites

- **Google Cloud Project** created.
- **gcloud CLI** installed and authenticated.
- **Docker** installed.

## 2. Infrastructure Setup

### Enable APIs
```bash
gcloud services enable \
  run.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  firestore.googleapis.com
```

### Create a Service Account
Create a dedicated service account for the application.
```bash
SA_NAME="htbase-app"
gcloud iam service-accounts create $SA_NAME
```

Grant necessary permissions:
- **Cloud SQL Client** (to connect to DB)
- **Storage Object Admin** (for GCS)
- **Firebase Admin** (for Firestore)
- **Secret Manager Secret Accessor** (to read secrets)

### Create Secrets
Store sensitive values in Google Secret Manager. Do NOT use environment variables for these.

- `DB_PASSWORD`
- `OPENAI_API_KEY`
- `HF_TOKEN` (HuggingFace token)

```bash
echo -n "your-db-password" | gcloud secrets create HTBASE_DB_PASSWORD --data-file=-
echo -n "your-openai-key" | gcloud secrets create HTBASE_OPENAI_API_KEY --data-file=-
```

## 3. Configuration (Environment Variables)

Set these directly in the Cloud Run service revision:

- `LOG_LEVEL`: `INFO`
- `DB_HOST`: `/cloudsql/YOUR_PROJECT:REGION:INSTANCE_NAME` (Unix socket connection)
- `DB_NAME`: `htbase` (or your DB name)
- `DB_USER`: `postgres` (or your user)
- `STORAGE_BACKEND`: `gcs`
- `GCS_BUCKET`: `your-archive-bucket-name`
- `GCS_PROJECT_ID`: `your-project-id`
- `FIRESTORE_PROJECT_ID`: `your-project-id`

## 4. Build and Push

```bash
# Set your region (e.g., us-central1)
REGION="us-central1"
PROJECT_ID=$(gcloud config get-value project)

# Build
gcloud builds submit --tag gcr.io/$PROJECT_ID/htbase:latest

# OR using Docker + Push
docker build -t gcr.io/$PROJECT_ID/htbase:latest .
docker push gcr.io/$PROJECT_ID/htbase:latest
```

## 5. Deploy

Deploy the service, linking secrets and the service account.

```bash
gcloud run deploy htbase-service \
  --image gcr.io/$PROJECT_ID/htbase:latest \
  --platform managed \
  --region $REGION \
  --service-account $SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars="LOG_LEVEL=INFO,DB_NAME=htbase,DB_USER=postgres,STORAGE_BACKEND=gcs,GCS_BUCKET=my-bucket,GCS_PROJECT_ID=$PROJECT_ID,FIRESTORE_PROJECT_ID=$PROJECT_ID" \
  --set-secrets="DB_PASSWORD=HTBASE_DB_PASSWORD:latest,OPENAI_API_KEY=HTBASE_OPENAI_API_KEY:latest" \
  --add-cloudsql-instances="YOUR_PROJECT:REGION:INSTANCE_NAME" \
  --allow-unauthenticated
```

## 6. Important Notes

- **Port:** Cloud Run expects the container to listen on `$PORT` (default 8080).
  - Ensure your `entrypoint.sh` or `Dockerfile` respects this. Currently, `entrypoint.sh` uses port 8000.
  - **Action Required:** Update `entrypoint.sh` to use `$PORT` or configure Cloud Run to forward to 8000.
- **Storage:** Cloud Run is stateless.
  - Local files in `/data` will vanish.
  - Ensure `STORAGE_BACKEND=gcs` is set so uploads go to GCS.
