# ==============================================================================
# Multi-Stage Production Dockerfile for IncidentPilot
# ==============================================================================

# Stage 1: Build Dependencies
FROM python:3.10-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --upgrade pip && \
    pip install psycopg[binary] && \
    pip install .

# Stage 2: Production Runtime
FROM python:3.10-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api \
    PORT=8000 \
    WORKERS=4

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group
RUN groupadd -g 10001 incidentpilot && \
    useradd -u 10001 -g incidentpilot -s /bin/bash -m incidentpilot

# Copy installed python site-packages from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source, alembic migrations, and config
COPY --chown=incidentpilot:incidentpilot apps/api/app /app/apps/api/app
COPY --chown=incidentpilot:incidentpilot apps/api/alembic /app/apps/api/alembic
COPY --chown=incidentpilot:incidentpilot apps/api/alembic.ini /app/apps/api/alembic.ini
COPY --chown=incidentpilot:incidentpilot pyproject.toml /app/pyproject.toml

# Switch to non-root user
USER incidentpilot

EXPOSE 8000

# Healthcheck probe
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Entrypoint: Run migrations and start production uvicorn server
CMD ["sh", "-c", "cd /app/apps/api && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS}"]
