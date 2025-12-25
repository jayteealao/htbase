# Storage Worker Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module
COPY shared /app/shared

# Copy service code
COPY services/storage-worker /app/services/storage-worker

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install GCS and Firestore clients
RUN pip install --no-cache-dir \
    google-cloud-storage \
    google-cloud-firestore \
    psycopg[binary]

# Set Python path
ENV PYTHONPATH=/app:/app/services/storage-worker

# Create data directory
RUN mkdir -p /data && chmod 777 /data
ENV DATA_DIR=/data

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /data
USER appuser

# Run the worker
CMD ["python", "services/storage-worker/worker.py"]
