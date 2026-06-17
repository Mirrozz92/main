# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (no editable install — we use PYTHONPATH)
RUN pip install --upgrade pip setuptools wheel && \
    pip install \
        "aiogram==3.28.2" \
        "fastapi==0.136.1" \
        "uvicorn[standard]==0.34.0" \
        "sqlalchemy[asyncio]==2.0.49" \
        "asyncpg==0.31.0" \
        "alembic==1.14.1" \
        "psycopg2-binary==2.9.10" \
        "redis[hiredis]==5.2.1" \
        "taskiq==0.11.18" \
        "taskiq-redis==1.0.9" \
        "pydantic==2.11.3" \
        "pydantic-settings==2.7.1" \
        "httpx==0.28.1" \
        "structlog==25.4.0" \
        "prometheus-client==0.21.1" \
        "python-dateutil==2.9.0.post0" \
        "orjson==3.10.18" \
        "tenacity==9.0.0" \
        "cryptography==43.0.1" \
        "python-multipart==0.0.20"

# Copy source AFTER deps for better caching
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY pyproject.toml ./

# Non-root user
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
