# Summarization Worker Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module
COPY shared /app/shared

# Copy service code
COPY services/summarization-worker /app/services/summarization-worker

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for summarization
RUN pip install --no-cache-dir \
    httpx \
    pydantic \
    chonkie

# Set Python path
ENV PYTHONPATH=/app:/app/services/summarization-worker

# Create data directory
RUN mkdir -p /data && chmod 777 /data
ENV DATA_DIR=/data

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /data
USER appuser

# Run the worker
CMD ["python", "services/summarization-worker/worker.py"]
