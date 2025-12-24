FROM python:3.11-slim

WORKDIR /app

# Install python dependencies
COPY services/worker_summary/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY common /app/common

# Copy service code
COPY services/worker_summary /app/services/worker_summary

# Set python path
ENV PYTHONPATH=/app

CMD ["celery", "-A", "services.worker_summary.main.celery_app", "worker", "-Q", "summary_queue", "--loglevel=info"]
