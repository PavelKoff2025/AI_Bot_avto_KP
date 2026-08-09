# AI Bot — автогенерация КП

**Telegram-помощник менеджера отдела продаж** компании «Дом-Мастер»: из транскрибации клиентского звонка за минуты собирает коммерческие предложения, архитектурный и инженерный пакеты и отдаёт готовые PDF прямо в чат.

> **About (для GitHub):** Telegram-бот и HTTP API («Дом-Мастер»): из транскрибации — КП, АР, ИР и сводный PDF. Docker · Go API · OpenAPI.

📚 **Полная документация:** [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md)  
📡 **OpenAPI 3.1:** [`docs/openapi.yaml`](docs/openapi.yaml)  
🐳 **Docker:** [`docs/DOCKER.md`](docs/DOCKER.md) · **Docker Hub → сервер:** [`docs/DOCKER_HUB.md`](docs/DOCKER_HUB.md)  
📄 **Отчёт для куратора:** [`docs/ОТЧЁТ_ДЛЯ_КУРАТОРА_AI_автоматизация.md`](docs/ОТЧЁТ_ДЛЯ_КУРАТОРА_AI_автоматизация.md)  
🔍 **Аудит кода:** [`AUDIT.md`](AUDIT.md)

---

## Зачем это нужно

После звонка менеджер обычно вручную собирает смету, КП и приложения. Бот берёт **текст транскрибации**, проверяет, хватает ли данных, спрашивает нужный вариант дома и приложения — и генерирует **готовые документы** через OpenAI + Jinja2 + WeasyPrint.

Менеджер получает файлы в Telegram: скачать по одному, собрать всё в один PDF, упаковать в ZIP.

---

## Что умеет бот

### 1. Приём транскрибации
- Файл `.txt` или текст сообщением
- Команды `/start`, `/help`, сброс сессии «Новый звонок»

### 2. Проверка достаточности данных (LLM)
Сравнение с эталоном `knowledge_base/etalon_protocol.md` (fallback: `sample_dialog.txt`):
- хватает ли площади, этажности, материалов, бюджета, сроков, пожеланий;
- извлекает имя заказчика для документов;
- если данных мало — бот просит дополнить транскрибацию и указывает, чего не хватает.

### 3. Выбор варианта коммерческого предложения
Три варианта тёплого контура:

| Вариант в боте | Содержание |
|---|---|
| **Базовый** | Газобетон · базовый тёплый контур |
| **Средний (оптимальный)** | Клееный брус · средний |
| **Средний +** | Газобетон · средний + |

### 4. Опциональные приложения
- **АР** — архитектурный бриф: текст + AI-визуализация экстерьера + план помещений
- **ИР** — инженерный раздел: водоснабжение, канализация, газовое отопление, тёплые полы, вентиляция и ориентировочная смета

### 5. Сборка и выдача документов
После генерации менеджер может:
- **📥 Скачать файлы** — отдельные PDF пакета
- **📄 Собрать все в один документ** — сводная смета по 3 вариантам КП + отдельные КП + АР/ИР (если выбраны)
- **🗜 ZIP** — архив финального комплекта
- **✉️ E-mail** — заготовка под отправку (пока stub; логика подсказывает сначала сделать ZIP)

### 6. Надёжность
- Поэтапные логи в консоль и `logs/bot.log`
- Allowlist пользователей (`TELEGRAM_ALLOWED_IDS`)
- Сообщения об ошибках без утечки внутренних деталей
- Глобальный обработчик необработанных исключений
- Блокировка повторных тяжёлых задач на одного пользователя

---

## Стек

| Слой | Технологии |
|---|---|
| Бот | Python 3.11+, aiogram 3, FSM |
| LLM / картинки | OpenAI API |
| PDF | Jinja2 → HTML → WeasyPrint |
| Merge PDF | pypdf |
| Конфиг | python-dotenv |
| Шрифты кириллицы | DejaVu Sans (`fonts/`) |
| HTTP API | Flask (`flask_app.py`) или Go (`go_server/`) |
| Контейнеры | Docker, Docker Compose, образы на Docker Hub |

Зависимости: [`requirements.txt`](requirements.txt) (диапазоны) и [`requirements.lock.txt`](requirements.lock.txt) (зафиксированные версии).

---

## Быстрый старт

### 1. Клонирование

```bash
git clone https://github.com/PavelKoff2025/AI_Bot_avto_KP.git
cd AI_Bot_avto_KP
```

### 2. Окружение

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# или воспроизводимая установка:
# pip install -r requirements.lock.txt
```

На macOS для WeasyPrint могут понадобиться системные библиотеки (cairo, pango) — см. [документацию WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) и [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md).

### 3. Ключи

```bash
cp .env.example .env
```

Заполните `.env`:

| Переменная | Назначение |
|---|---|
| `OPENAI_API_KEY` | ключ OpenAI |
| `OPENAI_MODEL` | текстовая модель (по умолчанию `gpt-4o-mini`) |
| `OPENAI_IMAGE_MODEL` | модель картинок (например `gpt-image-1`) |
| `OPENAI_IMAGE_SIZE` | размер изображений |
| `TELEGRAM_BOT_TOKEN` | токен от [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_ALLOWED_IDS` | user id через запятую (рекомендуется) |
| `FLASK_API_TOKEN` | токен для HTTP API (рекомендуется вне localhost) |
| `FLASK_PORT` | порт Flask (по умолчанию `5000`) |
| `ETALON_KP_THRESHOLD` | порог заполнения эталона (%) для генерации КП в CRM (по умолчанию `80`) |

### 4. Запуск бота

```bash
python bot.py
```

Логи: консоль и файл `logs/bot.log`.

### 5. CLI без Telegram (отчёты / КП)

```bash
# клиентский / дизайн / АР / ИР отчёт
python main.py sample_dialog.txt --type ar

# коммерческие предложения
python main.py --kp
python main.py --kp --with-fz --with-engineering sample_dialog.txt
```

### 6. Flask API (опционально)

```bash
python main.py --serve
# или: python flask_app.py
```

Подробности эндпоинтов и авторизации — в [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md#8-http-api-flask_appy).

### 7. Go API Server (альтернатива Flask)

HTTP-сервер на Go с теми же эндпоинтами (`/health`, `/api/report`, `/api/kp`):

```bash
cd go_server
go run ./cmd/server
# http://127.0.0.1:5001
```

Инструкции: [`go_server/README.md`](go_server/README.md).  
OpenAPI: [`docs/openapi.yaml`](docs/openapi.yaml) (копия в [`go_server/openapi.yaml`](go_server/openapi.yaml)).

### 8. Docker

```bash
# Flask API → http://127.0.0.1:5001
docker compose up -d --build api

# Go API → http://127.0.0.1:5002
docker compose up -d --build go-api

BASE_URL=http://127.0.0.1:5002 ./scripts/check_endpoints.sh --quick
```

Подробности: [`docs/DOCKER.md`](docs/DOCKER.md), [`go_server/README.md`](go_server/README.md).

---

## Сценарий работы менеджера

```text
Транскрибация (.txt / текст)
        ↓
  LLM: данных достаточно?
        ↓ да
  Выбор КП: Базовый / Средний / Средний+
        ↓
  Нужен АР?  →  Нужен ИР?
        ↓
  Генерация PDF-пакета
        ↓
  Скачать · Объединить · ZIP · (E-mail)
```

### CRM (`web_app/`): проверка по эталону

В веб-CRM сравнение с эталоном **детерминированное** (regex-парсер + % заполнения полей):

```text
Транскрибация / файл
        ↓
  parse_transcript_local + validate_against_etalon()
        ↓
  score = % заполненных полей эталона
        ↓
  < 100%  →  страница «Недостающие данные» + вопросы клиенту
  ≥ ETALON_KP_THRESHOLD (80%)  →  можно генерировать КП
  < 80%   →  КП заблокировано, нужно дособрать
```

Обязательные поля эталона: телефон, email, участок, площадь, материал, сроки, финансирование. Бюджет и Telegram — опциональны; основной канал отправки КП — email.  
Тесты: `cd web_app && PYTHONPATH=. python3 -m unittest tests.test_etalon_validation -v`

---

## Структура проекта

```text
├── bot.py                 # Telegram-бот (FSM)
├── main.py                # CLI: отчёты и КП
├── flask_app.py           # HTTP API (Python/Flask)
├── go_server/             # тот же HTTP API на Go
├── Dockerfile             # образ Flask/bot
├── docker-compose.yml     # api / go-api / bot
├── scripts/               # push/pull Docker Hub, check endpoints
├── sample_dialog.txt      # пример транскрибации (fallback эталона)
├── knowledge_base/
│   ├── etalon_protocol.md          # эталон обязательных полей для КП
│   ├── company_standards.md        # стандарты «Дом-Мастер» (RAG)
│   ├── company_complectations.md   # виды комплектаций (RAG)
│   └── complectations_short.md     # краткая справка для вставки в КП
├── web_app/               # CRM менеджера: сделки + проверка эталона
├── requirements.txt       # зависимости (диапазоны)
├── requirements.lock.txt  # зафиксированные версии
├── AUDIT.md               # аудит кода
├── ABOUT.md               # текст About для GitHub
├── .env.example
├── fonts/                 # DejaVu — кириллица в PDF
├── templates/             # Jinja2-шаблоны PDF
├── utils/                 # генерация КП / АР / ИР / PDF
├── docs/
│   ├── DOCUMENTATION.md   # полная документация
│   ├── openapi.yaml       # OpenAPI 3.1
│   ├── DOCKER.md          # локальный Docker
│   ├── DOCKER_HUB.md      # Hub → сервер
│   └── screenshots/
├── reports/               # PDF/HTML (в git не попадают)
└── logs/                  # bot.log
```

---

## Типы документов

| Документ | Содержание |
|---|---|
| **КП** | Тёплый контур: состав работ, материалы, ориентировочная стоимость |
| **АР** | Бриф + экстерьер (AI) + план помещений (AI) |
| **ИР** | Инженерные системы + базовая смета пакета |
| **Сводный PDF** | Смета по всем 3 КП + отдельные КП + опционально АР/ИР |
| **Клиентский / design** | Отчёты из `main.py` (анализ диалога, дизайн-сайт) |

Цены в документах — **ориентировочные**; финал после выезда и спецификации.  
Семантика сводной сметы — в [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md#10-типы-документов-и-цены).

---

## Пример эталона

В репозитории лежит `sample_dialog.txt` — протокол переговоров (строительство дома). Им удобно тестировать бота и CLI.

---

## Скриншоты

Скриншоты интерфейса и документов кладите в [`docs/screenshots/`](docs/screenshots/).

---

## Возможное развитие бота

1. **Актуальные прайс-листы из БД компании** — интеграция с 1С / ERP.
2. **Отправка КП по e-mail** — SMTP или корпоративный API.
3. **Выгрузка КП в CRM** — Битрикс24, amoCRM и т.п.
4. **ТЗ для внешней инженерной компании** — отдельный пакет для подрядчика.

---

## Лицензия

Проект распространяется под лицензией [MIT](LICENSE).

---

## Автор

[PavelKoff2025](https://github.com/PavelKoff2025) — учебный / продуктовый прототип автоматизации КП для отдела продаж.
