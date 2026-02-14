FROM python:3.11-slim

WORKDIR /app

# Install Monolith (Rust tool)
# We can install from cargo or download a binary.
# For speed, let's assume we install cargo or download.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (if building) or download binary
# Using cargo to install monolith
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN cargo install monolith

# Install python dependencies
COPY services/worker_monolith/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY common /app/common

# Copy service code
COPY services/worker_monolith /app/services/worker_monolith

# Set python path
ENV PYTHONPATH=/app

CMD ["celery", "-A", "services.worker_monolith.main.celery_app", "worker", "-Q", "monolith_queue", "--loglevel=info"]
