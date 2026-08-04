# Go API Server — AI_Auogeneration

HTTP-сервер на **Go**, совместимый с Python `flask_app.py`: те же эндпоинты, авторизация и лимиты.

Генерация PDF (OpenAI + Jinja2 + WeasyPrint) выполняется через тонкий **Python bridge** к существующему пакету `utils/` — документы получаются теми же, что у Flask/CLI. HTTP-слой, auth, таймауты и раздача файлов — на Go.

```text
Клиент (curl / фронт)
        │
        ▼
┌─────────────────────┐
│  go_server (Go)     │  /health, /api/report, /api/kp
│  auth · limits      │
└─────────┬───────────┘
          │ JSON stdin/stdout
          ▼
┌─────────────────────┐
│ bridge/generate.py  │
│ → utils/*           │  OpenAI, WeasyPrint, reports/
└─────────────────────┘
```

---

## Требования

| Компонент | Версия |
|-----------|--------|
| **Go** | 1.22+ ([установка](https://go.dev/dl/)) |
| **Python** | 3.11+ с зависимостями корневого проекта (`.venv` + `requirements.txt`) |
| **OpenAI / .env** | корневой `.env` с `OPENAI_API_KEY` (и при необходимости `FLASK_API_TOKEN`) |

Системные библиотеки WeasyPrint — как для Python-проекта (см. [`docs/DOCUMENTATION.md`](../docs/DOCUMENTATION.md)).

---

## Быстрый старт

### Вариант A — Docker (рекомендуется, Go устанавливать не нужно)

Из **корня** репозитория:

```bash
# 1) .env с OPENAI_API_KEY и FLASK_API_TOKEN
cp -n .env.example .env   # если ещё нет
# отредактируйте .env

# 2) собрать образ и запустить Go API
docker compose up -d --build go-api

# 3) проверка (порт на хосте: 5002)
curl http://127.0.0.1:5002/health
# {"status":"ok"}

./scripts/check_endpoints.sh --quick
# или явно:
BASE_URL=http://127.0.0.1:5002 ./scripts/check_endpoints.sh --quick
```

Остановка:

```bash
docker compose stop go-api
# или удалить контейнер:
docker compose down
```

Логи:

```bash
docker compose logs -f go-api
```

Свой порт на хосте:

```bash
GO_API_HOST_PORT=8080 docker compose up -d --build go-api
```

---

### Вариант B — локально без Docker

Нужны **Go 1.22+** и Python-окружение проекта.

#### 1. Python

```bash
cd /path/to/AI_Auogeneration
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# .env с OPENAI_API_KEY
```

#### 2. Собрать и запустить Go-сервер

```bash
cd go_server
go build -o bin/server ./cmd/server
./bin/server
```

По умолчанию: **`http://127.0.0.1:5001`**.

```bash
# без бинарника
go run ./cmd/server

GO_SERVER_HOST=127.0.0.1 GO_SERVER_PORT=8080 go run ./cmd/server
```

#### 3. Проверка

```bash
curl http://127.0.0.1:5001/health
BASE_URL=http://127.0.0.1:5001 ./scripts/check_endpoints.sh --quick
```

Успешный старт в логе:

```text
Go API server starting addr=http://0.0.0.0:5001 ...
```

---

### Порты (кратко)

| Сервис | Хост (default) | В контейнере |
|--------|----------------|--------------|
| Flask `api` | **5001** | 5000 |
| Go `go-api` | **5002** | 5001 |
| Локальный `go run` | **5001** | — |
---

## Конфигурация

Сервер читает `.env` из `go_server/.env` или из **корня** Python-проекта (туда же кладутся `OPENAI_API_KEY`, `FLASK_API_TOKEN`).

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `GO_SERVER_HOST` | `127.0.0.1` | адрес bind |
| `GO_SERVER_PORT` / `PORT` | `5001` | порт |
| `FLASK_API_TOKEN` или `API_TOKEN` | пусто | API-токен; без токена — только localhost |
| `PROJECT_ROOT` | родитель `go_server/` | корень с `utils/` и `.env` |
| `PYTHON_BIN` | `.venv/bin/python` или `python3` | интерпретатор для bridge |
| `BRIDGE_SCRIPT` | `go_server/bridge/generate.py` | путь к bridge |

Пример `go_server/.env`:

```env
GO_SERVER_HOST=127.0.0.1
GO_SERVER_PORT=5001
FLASK_API_TOKEN=my-secret-token
```

Шаблон: [`.env.example`](.env.example).

---

## API

Базовый URL: `http://127.0.0.1:5001`

Спецификация **OpenAPI 3.1:** [`openapi.yaml`](openapi.yaml)  
(каноническая копия также в [`../docs/openapi.yaml`](../docs/openapi.yaml)).

Просмотр в Swagger UI / Redoc:

```bash
# пример: Docker Swagger UI
docker run --rm -p 8088:8080 \
  -e SWAGGER_JSON=/api/openapi.yaml \
  -v "$(pwd)/openapi.yaml:/api/openapi.yaml:ro" \
  swaggerapi/swagger-ui
# откройте http://127.0.0.1:8088
```

### Авторизация

Если задан `FLASK_API_TOKEN` / `API_TOKEN`, передайте один из заголовков:

```http
X-API-Token: <token>
Authorization: Bearer <token>
```

Без токена запросы с не-localhost отклоняются с `401`.

Лимит тела запроса: **2 МБ**.

---

### `GET /health`

Проверка живости (без токена).

```bash
curl http://127.0.0.1:5001/health
```

```json
{"status":"ok"}
```

---

### `POST /api/report`

Генерирует PDF-отчёт и отдаёт файл.

**JSON:**

```bash
curl -X POST http://127.0.0.1:5001/api/report \
  -H "Content-Type: application/json" \
  -H "X-API-Token: $FLASK_API_TOKEN" \
  -d '{"text":"Клиент Иван, дом 130 м², бюджет 8 млн…","type":"ar"}' \
  --output report.pdf
```

| Поле | Описание |
|------|----------|
| `text` | транскрибация (обязательно) |
| `type` | `client` \| `design` \| `ar` \| `engineering` (алиасы `1`–`4`, `ir`) |

**multipart** (файл `.txt`):

```bash
curl -X POST http://127.0.0.1:5001/api/report \
  -H "X-API-Token: $FLASK_API_TOKEN" \
  -F "file=@../sample_dialog.txt" \
  -F "type=engineering" \
  --output ir.pdf
```

Ответ: `application/pdf` (attachment).  
Ошибки клиента: JSON `{"error":"..."}` с кодом 400/401.  
Внутренние ошибки: `500` с текстом `"Внутренняя ошибка сервера"` (детали в логе сервера / stderr Python).

> Генерация АР с картинками может занять **1–3+ минуты** (таймаут bridge — 10 минут).

---

### `POST /api/kp`

Формирует 3 коммерческих предложения (± ФЗ / ИР).

```bash
curl -X POST http://127.0.0.1:5001/api/kp \
  -H "Content-Type: application/json" \
  -H "X-API-Token: $FLASK_API_TOKEN" \
  -d '{
    "with_fz": false,
    "with_engineering": true,
    "client_name": "Иван",
    "text": "текст транскрибации для AI-брифа ИР (опционально)"
  }'
```

Пример ответа:

```json
{
  "with_fz": false,
  "with_engineering": true,
  "files": [
    "reports/kp/batch_…/KP_01_….pdf",
    "reports/kp/batch_…/KP_02_….pdf",
    "reports/kp/batch_…/KP_03_….pdf",
    "reports/kp/batch_…/attachment_IR_engineering.pdf"
  ]
}
```

Пути относительные к корню Python-проекта. Абсолютные пути наружу не отдаются.

---

## Структура каталога

```text
go_server/
├── README.md
├── go.mod
├── Makefile
├── .env.example
├── cmd/server/main.go          # точка входа
├── bridge/generate.py          # Python bridge → utils/
└── internal/
    ├── app/                    # сборка DI (config→services→routes)
    ├── models/                 # DTO: API + bridge
    ├── config/                 # конфигурация из env
    ├── routes/                 # регистрация маршрутов
    ├── handlers/               # HTTP-обработчики
    ├── middleware/             # auth, logging, body limit
    ├── services/               # бизнес-логика генерации
    ├── bridge/                 # клиент Python bridge
    ├── utils/                  # http/json, path, net, errors, payload
    └── dotenv/                 # загрузка .env
```

Слои:

| Пакет | Ответственность |
|-------|-----------------|
| `models` | структуры запросов/ответов |
| `routes` | привязка URL → handlers |
| `handlers` | разбор HTTP, коды ответов |
| `middleware` | auth / лимиты / логи |
| `services` | оркестрация генерации PDF/КП |
| `bridge` | вызов `generate.py` |
| `utils` | переиспользуемые хелперы |
| `app` | wiring приложения |
---

## Совместимость с Flask

| | Flask (`flask_app.py`) | Go (`go_server`) |
|--|------------------------|------------------|
| Порт по умолчанию | 5000 | **5001** |
| `GET /health` | да | да |
| `POST /api/report` | да | да |
| `POST /api/kp` | да | да |
| Токен | `FLASK_API_TOKEN` | тот же + `API_TOKEN` |
| Loopback без токена | да | да |
| PDF-движок | Python utils | тот же через bridge |

Можно держать оба сервера одновременно на разных портах.

---

## Отладка

**Bridge вручную:**

```bash
cd /path/to/AI_Auogeneration
echo '{"action":"report","text":"тест диалог про дом 130м2 бюджет","type":"client"}' \
  | .venv/bin/python go_server/bridge/generate.py
```

**Частые проблемы**

| Симптом | Что проверить |
|---------|----------------|
| `bridge script не найден` | запуск из `go_server/` или задайте `PROJECT_ROOT` / `BRIDGE_SCRIPT` |
| `python bridge failed` | `.venv`, `pip install -r requirements.txt`, WeasyPrint libs, `OPENAI_API_KEY` |
| `401` с удалённого хоста | задайте `FLASK_API_TOKEN` и передайте заголовок |
| Долгий `/api/report` type=ar | нормально: 2 картинки + PDF |

Логи HTTP — в stdout Go-процесса (`method`, `path`, `status`, `dur_ms`).

---

## Разработка

```bash
cd go_server
go vet ./...
go build -o bin/server ./cmd/server
```

Зависимости только стандартная библиотека Go (внешних модулей нет).

---

## Лицензия

Тот же проект / MIT, что и корневой репозиторий.
