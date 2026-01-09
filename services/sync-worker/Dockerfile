# Sync Worker Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module
COPY shared /app/shared

# Copy service code
COPY services/sync-worker /app/services/sync-worker

# Install Python dependencies
COPY requirements.microservices.txt /app/
RUN pip install --no-cache-dir -r requirements.microservices.txt

# Install Firebase Admin SDK for Firestore access
RUN pip install --no-cache-dir firebase-admin>=6.0.0

# Set Python path
ENV PYTHONPATH=/app:/app/services/sync-worker

# Create data directory
RUN mkdir -p /data && chmod 777 /data
ENV DATA_DIR=/data

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /data
USER appuser

# Run the worker
CMD ["python", "services/sync-worker/worker.py"]
