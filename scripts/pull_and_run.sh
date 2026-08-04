#!/usr/bin/env bash
# Запуск с образами из Docker Hub (без локальной сборки).
#
# Usage:
#   export DOCKERHUB_USER=yourname
#   ./scripts/pull_and_run.sh go-api     # только Go API
#   ./scripts/pull_and_run.sh api       # только Flask
#   ./scripts/pull_and_run.sh all       # api + go-api

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

USER_NAME="${DOCKERHUB_USER:-}"
TARGET="${1:-go-api}"

if [[ -z "$USER_NAME" ]]; then
  echo "Задайте DOCKERHUB_USER, например: export DOCKERHUB_USER=pavelkoff"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Нет .env — скопируйте: cp .env.example .env и заполните ключи"
  exit 1
fi

export DOCKERHUB_IMAGE_API="${DOCKERHUB_IMAGE_API:-${USER_NAME}/ai-auogeneration:latest}"
export DOCKERHUB_IMAGE_GO="${DOCKERHUB_IMAGE_GO:-${USER_NAME}/ai-auogeneration-go:latest}"

echo "API image: $DOCKERHUB_IMAGE_API"
echo "GO  image: $DOCKERHUB_IMAGE_GO"

case "$TARGET" in
  go-api|go)
    docker compose pull go-api
    docker compose up -d go-api
    echo "Go API → http://127.0.0.1:${GO_API_HOST_PORT:-5002}/health"
    ;;
  api|flask)
    docker compose pull api
    docker compose up -d api
    echo "Flask API → http://127.0.0.1:${API_HOST_PORT:-5001}/health"
    ;;
  all)
    docker compose pull api go-api
    docker compose up -d api go-api
    echo "Flask → :${API_HOST_PORT:-5001}  Go → :${GO_API_HOST_PORT:-5002}"
    ;;
  *)
    echo "Usage: $0 [go-api|api|all]"
    exit 1
    ;;
esac
