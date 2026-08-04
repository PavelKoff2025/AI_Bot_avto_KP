# Docker

Запуск API (и опционально Telegram-бота) в контейнере.

---

## Что установить на Mac

Для **запуска из Docker Hub** достаточно одного приложения:

| ПО | Зачем |
|----|--------|
| **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** | Docker Engine + Compose, GUI |

После установки:

1. Откройте Docker Desktop и дождитесь статуса **Running**.
2. В терминале проверьте: `docker version` и `docker compose version`.

**Не нужно** ставить отдельно, если работаете только через готовые образы:

- Go
- Python / venv
- WeasyPrint и системные библиотеки cairo/pango

Они уже внутри образов.

Дополнительно по желанию:

| ПО | Когда нужно |
|----|-------------|
| **Git** | клонировать репозиторий (`git clone`) |
| **curl** | уже есть в macOS — проверка `/health` |
| аккаунт **[Docker Hub](https://hub.docker.com/)** | push/pull своих образов (бесплатный аккаунт ок) |

> Порт **5000** на macOS часто занят AirPlay — мы используем **5001** (Flask) и **5002** (Go).

---

## Требования к `.env`

Секреты **не кладутся в Docker Hub** — только в локальный `.env` на каждой машине:

```bash
cp .env.example .env
```

Минимум:

```env
OPENAI_API_KEY=sk-...
FLASK_API_TOKEN=свой-секрет
TELEGRAM_BOT_TOKEN=...    # только если запускаете бота
```

---

## Перенос через Docker Hub

Схема:

```text
Mac A (сборка)  →  docker push  →  Docker Hub  →  docker pull  →  Mac B / сервер
                     образы                         .env локально
```

### A. Машина, где собираете (один раз)

```bash
# 1. Логин Docker Hub
docker login
# введите username и Access Token (или пароль)

# 2. Задайте логин Hub
export DOCKERHUB_USER=ваш_логин_dockerhub

# 3. Собрать и отправить оба образа
chmod +x scripts/push_dockerhub.sh scripts/pull_and_run.sh
./scripts/push_dockerhub.sh
# опционально с версией:
# ./scripts/push_dockerhub.sh v1.0.0
```

На Hub появятся:

- `ваш_логин/ai-auogeneration` — Flask API + bot  
- `ваш_логин/ai-auogeneration-go` — Go API  

### B. Другой Mac / сервер (без сборки)

```bash
# 1. Docker Desktop установлен и запущен

# 2. Код репозитория (нужны compose + .env.example + scripts)
git clone <ваш-repo> AI_Auogeneration
cd AI_Auogeneration
cp .env.example .env
nano .env   # OPENAI_API_KEY + FLASK_API_TOKEN

# 3. Подтянуть образы и запустить Go API
export DOCKERHUB_USER=ваш_логин_dockerhub
./scripts/pull_and_run.sh go-api

curl http://127.0.0.1:5002/health
```

Или вручную:

```bash
export DOCKERHUB_USER=ваш_логин
export DOCKERHUB_IMAGE_API=${DOCKERHUB_USER}/ai-auogeneration:latest
export DOCKERHUB_IMAGE_GO=${DOCKERHUB_USER}/ai-auogeneration-go:latest

docker compose pull go-api
docker compose up -d go-api
```

В `.env` можно прописать постоянно:

```env
DOCKERHUB_IMAGE_API=ваш_логин/ai-auogeneration:latest
DOCKERHUB_IMAGE_GO=ваш_логин/ai-auogeneration-go:latest
DOCKERHUB_USER=ваш_логин
```

---

## Быстрый старт (локальная сборка, без Hub)

### Flask API

```bash
docker compose build api
docker compose up -d api
curl http://127.0.0.1:5001/health
```

### Go API

```bash
docker compose up -d --build go-api
curl http://127.0.0.1:5002/health
BASE_URL=http://127.0.0.1:5002 ./scripts/check_endpoints.sh --quick
```

Проверка эндпоинтов:

```bash
# токен тот же, что в .env (не экспортируйте другой!)
unset FLASK_API_TOKEN
BASE_URL=http://127.0.0.1:5002 ./scripts/check_endpoints.sh --quick
./scripts/check_endpoints.sh --full
```

---

## На сервере (Linux)

То же самое: Docker Engine + Compose plugin, `.env`, `docker compose pull && up`.

```bash
git clone <repo> && cd AI_Auogeneration
cp .env.example .env && nano .env
export DOCKERHUB_USER=ваш_логин
./scripts/pull_and_run.sh go-api
```

---

## Порты

| Сервис | Хост | Контейнер | Env |
|--------|------|-----------|-----|
| Flask `api` | 5001 | 5000 | `API_HOST_PORT` |
| Go `go-api` | 5002 | 5001 | `GO_API_HOST_PORT` |

```bash
GO_API_HOST_PORT=8080 docker compose up -d go-api
```

---

## Telegram-бот

```bash
docker compose --profile bot up -d
```

Нужен `TELEGRAM_BOT_TOKEN` в `.env`. Образ тот же, что у Flask API.

---

## Volumes

- `./reports` — PDF  
- `./logs` — логи  

---

## Переменные

| Env | Назначение |
|-----|------------|
| `OPENAI_API_KEY` | генерация |
| `FLASK_API_TOKEN` | auth API |
| `DOCKERHUB_USER` | логин Hub для скриптов push/pull |
| `DOCKERHUB_IMAGE_API` | полный путь образа Flask/bot |
| `DOCKERHUB_IMAGE_GO` | полный путь образа Go |
| `API_HOST_PORT` | порт Flask на хосте |
| `GO_API_HOST_PORT` | порт Go на хосте |

## OpenAPI

[`docs/openapi.yaml`](openapi.yaml).
