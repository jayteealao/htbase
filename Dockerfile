ARG DEBIAN_FRONTEND=noninteractive
ARG MONOLITH_VERSION=v2.10.1
ARG HT_VERSION=v0.4.0

FROM debian:bookworm-slim AS base

ARG DEBIAN_FRONTEND
ARG MONOLITH_VERSION
ARG HT_VERSION

# Install dependencies + Chromium + Node.js + npm
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
     ca-certificates curl bash python3 python3-pip python3-venv \
     chromium fonts-liberation fonts-dejavu-core fonts-noto-color-emoji \
     nodejs npm \
      # --- Chromium runtime deps (headless) ---
     libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 \
     libx11-xcb1 libxcomposite1 libxrandr2 libxi6 libxdamage1 \
     libxfixes3 libdrm2 libgbm1 libxshmfence1 libxext6 \
     libpango-1.0-0 libcairo2 libxcb1 libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

# Install monolith (static binary)
RUN set -eux; \
  arch="x86_64"; \
  case "$(uname -m)" in \
    aarch64) arch="aarch64" ;; \
    arm64) arch="aarch64" ;; \
    x86_64) arch="x86_64" ;; \
    *) echo "Unsupported arch: $(uname -m)"; exit 1 ;; \
  esac; \
  url="https://github.com/Y2Z/monolith/releases/download/${MONOLITH_VERSION}/monolith-gnu-linux-${arch}"; \
  echo "Downloading monolith from ${url}"; \
  curl -fsSL "${url}" -o /usr/local/bin/monolith; \
  chmod +x /usr/local/bin/monolith; \
  /usr/local/bin/monolith --version || true

# Install ht (linux gnu binary)
RUN set -eux; \
  arch="x86_64-unknown-linux-gnu"; \
  case "$(uname -m)" in \
    aarch64) arch="aarch64-unknown-linux-gnu" ;; \
    arm64) arch="aarch64-unknown-linux-gnu" ;; \
    x86_64) arch="x86_64-unknown-linux-gnu" ;; \
    *) echo "Unsupported arch: $(uname -m)"; exit 1 ;; \
  esac; \
  url="https://github.com/andyk/ht/releases/download/${HT_VERSION}/ht-${arch}"; \
  echo "Downloading ht from ${url}"; \
  curl -fsSL "${url}" -o /usr/local/bin/ht; \
  chmod +x /usr/local/bin/ht; \
  /usr/local/bin/ht --help >/dev/null || true
RUN which chromium && chromium --version || true

# Install SingleFile CLI via npm (provides `single-file` on PATH)
RUN set -eux; \
  npm install -g single-file-cli; \
  single-file --help >/dev/null || true; \
  which single-file && single-file --version || true

WORKDIR /app

COPY app/requirements.txt /app/requirements.txt

# Create and use an isolated virtual environment to avoid PEP 668 restrictions
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY app /app
# Copy Alembic migrations and config
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

# location for saved pages
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080 7681

ENV PYTHONUNBUFFERED=1
# Safer defaults for SingleFile (avoid sandbox + tiny /dev/shm issues)
ENV NODE_OPTIONS="--dns-result-order=ipv4first"
# Browser args as JSON array for SingleFile (no nested quotes - Python will handle JSON)
ENV SINGLEFILE_FLAGS="--browser-executable-path=/usr/bin/chromium --browser-args=[\\\"--headless=new\\\",\\\"--no-sandbox\\\",\\\"--disable-dev-shm-usage\\\",\\\"--hide-scrollbars\\\",\\\"--mute-audio\\\",\\\"--disable-gpu\\\",\\\"--disable-software-rasterizer\\\",\\\"--run-all-compositor-stages-before-draw\\\",\\\"--no-first-run\\\",\\\"--no-default-browser-check\\\",\\\"--disable-features=LockProfileCookieDatabase\\\"]"


# Use the venv's interpreter/binaries via PATH
# Run DB migrations via Alembic, then start the API
# Copy entrypoint script and make it executable
COPY app/scripts/entrypoint.sh /app/scripts/entrypoint.sh
RUN chmod +x /app/scripts/entrypoint.sh

# Run Alembic migrations on startup, then launch the API
CMD ["/app/scripts/entrypoint.sh"]
