#!/usr/bin/env bash
# Сборка и публикация образов в Docker Hub.
#
# Usage:
#   export DOCKERHUB_USER=yourname
#   ./scripts/push_dockerhub.sh
#   ./scripts/push_dockerhub.sh v1.0.0    # с дополнительным тегом версии
#
# Нужно: docker login (один раз)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

USER_NAME="${DOCKERHUB_USER:-}"
if [[ -z "$USER_NAME" ]]; then
  echo "Задайте DOCKERHUB_USER (логин Docker Hub), например:"
  echo "  export DOCKERHUB_USER=pavelkoff"
  echo "  ./scripts/push_dockerhub.sh"
  exit 1
fi

TAG="${1:-latest}"
API_IMAGE="${USER_NAME}/ai-auogeneration"
GO_IMAGE="${USER_NAME}/ai-auogeneration-go"

echo "==> docker login (если ещё не залогинены)"
docker info >/dev/null
if ! docker system info 2>/dev/null | grep -qi username; then
  docker login
fi

echo "==> build Flask/bot image: ${API_IMAGE}:${TAG}"
docker build -t "${API_IMAGE}:${TAG}" -t "${API_IMAGE}:latest" .

echo "==> build Go API image: ${GO_IMAGE}:${TAG}"
docker build -f go_server/Dockerfile -t "${GO_IMAGE}:${TAG}" -t "${GO_IMAGE}:latest" .

echo "==> push"
docker push "${API_IMAGE}:${TAG}"
docker push "${API_IMAGE}:latest"
docker push "${GO_IMAGE}:${TAG}"
docker push "${GO_IMAGE}:latest"

echo
echo "Готово. На другой машине:"
echo "  export DOCKERHUB_IMAGE_API=${API_IMAGE}:latest"
echo "  export DOCKERHUB_IMAGE_GO=${GO_IMAGE}:latest"
echo "  # или пропишите в .env и:"
echo "  docker compose pull go-api"
echo "  docker compose up -d go-api"
