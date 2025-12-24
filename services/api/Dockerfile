FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Rust and ht (for /ht endpoints)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN cargo install --git https://github.com/andyk/ht

# Install python dependencies
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY common /app/common

# Copy service code
COPY services/api /app/services/api

# Set python path
ENV PYTHONPATH=/app

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
