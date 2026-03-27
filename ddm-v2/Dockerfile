FROM python:3.11-slim

# Accept proxy settings as build-time args (forwarded from host env by docker-compose)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DDM_ROOT_DIR=/app \
    DDM_DATA_DIR=/app/data \
    DDM_DB_PATH=/app/data/runtime-db.json \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy}

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --upgrade pip \
    && pip install -e . \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "ddm_v2.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]