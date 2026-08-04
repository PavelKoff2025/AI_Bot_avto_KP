# Multi-stage: Go HTTP API + Python bridge (utils / WeasyPrint)
# Build context = корень репозитория:
#   docker build -f go_server/Dockerfile -t ai-auogeneration-go .
#   docker compose up -d go-api

# ---------- build Go ----------
FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go_server/go.mod ./
COPY go_server/cmd ./cmd
COPY go_server/internal ./internal
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/server ./cmd/server

# ---------- runtime ----------
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app \
    PROJECT_ROOT=/app \
    PYTHON_BIN=python3 \
    BRIDGE_SCRIPT=/app/go_server/bridge/generate.py \
    GO_SERVER_HOST=0.0.0.0 \
    GO_SERVER_PORT=5001

WORKDIR ${APP_HOME}

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        libcairo2 \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY fonts ./fonts
COPY templates ./templates
COPY utils ./utils
COPY sample_dialog.txt ./
COPY go_server/bridge ./go_server/bridge
COPY --from=build /out/server /usr/local/bin/go-api

RUN mkdir -p reports/kp reports/engineering reports/images logs \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser ${APP_HOME}

USER appuser

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${GO_SERVER_PORT:-5001}/health" || exit 1

CMD ["go-api"]
