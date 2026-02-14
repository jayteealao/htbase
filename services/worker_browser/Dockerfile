FROM python:3.11-slim

WORKDIR /app

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-kacst fonts-freefont-ttf libxss1 \
      --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for SingleFile)
RUN apt-get update && apt-get install -y ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install SingleFile CLI
RUN npm install -g single-file-cli

# Set Chrome binary location for consistency
ENV CHROMIUM_BIN=/usr/bin/google-chrome

# Install python dependencies
COPY services/worker_browser/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY common /app/common

# Copy service code
COPY services/worker_browser /app/services/worker_browser

# Set python path
ENV PYTHONPATH=/app

# Command to run Celery worker
CMD ["celery", "-A", "services.worker_browser.main.celery_app", "worker", "-Q", "browser_queue", "--loglevel=info"]
