# Archive Worker Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Chromium and archiving tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-sandbox \
    curl \
    wget \
    git \
    npm \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install monolith
RUN wget -q https://github.com/Y2Z/monolith/releases/latest/download/monolith-gnu-linux-x86_64 \
    -O /usr/local/bin/monolith && chmod +x /usr/local/bin/monolith

# Install single-file CLI
RUN npm install -g single-file-cli

# Copy shared module
COPY shared /app/shared

# Copy service code
COPY services/archive-worker /app/services/archive-worker

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for archivers
RUN pip install --no-cache-dir httpx readability-lxml

# Set Python path
ENV PYTHONPATH=/app:/app/services/archive-worker

# Set binary paths
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV SINGLEFILE_BIN=/usr/local/bin/single-file
ENV MONOLITH_BIN=/usr/local/bin/monolith

# Create data directory
RUN mkdir -p /data && chmod 777 /data
ENV DATA_DIR=/data

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /data
USER appuser

# Run the worker
CMD ["python", "services/archive-worker/worker.py"]
