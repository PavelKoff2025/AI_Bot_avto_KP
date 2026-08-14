# Документация OfferDesk

**Продукт:** OfferDesk — рабочее место менеджера ОП «Дом-Мастер»  
**Назначение:** из транскрибации звонка за минуты собрать КП (CRM / Telegram / API)  
**Стек:** Python 3.11+, aiogram 3, OpenAI, Jinja2, WeasyPrint, Flask/Waitress CRM  
**Дата актуализации:** 2026-08-14

---

## Содержание

1. [Обзор](#1-обзор)
2. [Требования](#2-требования)
3. [Установка](#3-установка)
4. [Конфигурация (.env)](#4-конфигурация-env)
5. [Запуск](#5-запуск)
6. [Сценарий менеджера (бот)](#6-сценарий-менеджера-бот)
7. [CLI (`main.py`)](#7-cli-mainpy)
8. [HTTP API (`flask_app.py`)](#8-http-api-flask_appy)
9. [Архитектура и модули](#9-архитектура-и-модули)
10. [Типы документов и цены](#10-типы-документов-и-цены)
11. [Безопасность](#11-безопасность)
12. [Логи и артефакты](#12-логи-и-артефакты)
13. [Разработка и расширение](#13-разработка-и-расширение)
14. [Известные ограничения](#14-известные-ограничения)
15. [Связанные файлы](#15-связанные-файлы)
16. [OfferDesk CRM и production](#16-offerdesk-crm-и-production)

**Отдельные документы:**

- Менеджеры ОП: [`РУКОВОДСТВО_МЕНЕДЖЕРА.md`](РУКОВОДСТВО_МЕНЕДЖЕРА.md)
- Ops / VPS / proxy / systemd: [`OPS_CRM.md`](OPS_CRM.md)

---

## 1. Обзор

OfferDesk — система подготовки КП, не Telegram-бот. Основной контур — веб-CRM; бот и HTTP API — точки входа в тот же пайплайн.

После звонка менеджер вставляет в CRM (или присылает боту) `.txt` / текст транскрибации. Система:

1. проверяет достаточность данных относительно эталона `sample_dialog.txt` (LLM);
2. предлагает выбрать вариант КП (базовый / средний+ / оптимальный);
3. спрашивает, нужны ли приложения **АР** и **ИР**;
4. генерирует PDF через OpenAI + Jinja2 + WeasyPrint;
5. отдаёт файлы в чат: скачать, собрать сводный PDF, упаковать в ZIP.

Дополнительно доступны CLI и локальный Flask API для генерации отчётов без Telegram.

```text
Транскрибация
    → sufficiency (LLM)
    → package (1 КП ± АР ± ИР)
    → combine (смета + 3 КП ± АР ± ИР) → ZIP
```

---

## 2. Требования

| Компонент | Версия / примечание |
|-----------|---------------------|
| Python | **3.11+** (рекомендуется 3.11) |
| OpenAI API | ключ с доступом к Chat Completions и Images |
| Telegram Bot | токен от [@BotFather](https://t.me/BotFather) |
| Системные библиотеки | для WeasyPrint: cairo, pango, gdk-pixbuf (см. [документацию WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)) |

Python-зависимости перечислены в [`requirements.txt`](../requirements.txt) в корне репозитория.

### macOS (Homebrew), пример

```bash
brew install python@3.11 cairo pango gdk-pixbuf libffi
```

### Linux (Debian/Ubuntu), пример

```bash
sudo apt-get install -y python3-venv python3-pip \
  libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
  shared-mime-info fonts-dejavu-core
```

В репозитории уже лежат шрифты DejaVu в `fonts/` для кириллицы в PDF.

---

## 3. Установка

```bash
git clone https://github.com/PavelKoff2025/OfferDesk.git
cd OfferDesk   # локально папка может называться AI_Auogeneration

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# отредактируйте .env — см. раздел 4
```

Проверка импорта:

```bash
python -c "from utils.report_service import create_report; print('OK')"
```

---

## 4. Конфигурация (.env)

Скопируйте `.env.example` → `.env`. Файл `.env` **не коммитится**.

| Переменная | Обязательно | Описание | По умолчанию |
|------------|-------------|----------|--------------|
| `OPENAI_API_KEY` | да | ключ OpenAI | — |
| `OPENAI_MODEL` | нет | текстовая модель | `gpt-4o-mini` |
| `OPENAI_IMAGE_MODEL` | нет | модель изображений | `gpt-image-1` |
| `OPENAI_IMAGE_SIZE` | нет | размер картинок | `1024x1024` |
| `TELEGRAM_BOT_TOKEN` | да (для бота) | токен бота | — |
| `OPENAI_PROXY` | нет | HTTP/SOCKS прокси для OpenAI (`http://user:pass@host:8888`) | — |
| `ETALON_KP_THRESHOLD` | нет | порог % эталона для генерации КП в CRM | `80` |
| `CRM_PUBLIC_URL` | рекомендуется (CRM) | публичный URL CRM | — |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | для email КП | SMTP отправки из CRM | — |
| `HEALTH_ALERT_CHAT_ID` | нет | Telegram chat для health FAIL | первый из `TELEGRAM_ALLOWED_IDS` |
| `TELEGRAM_ALLOWED_IDS` | рекомендуется | Telegram user id через запятую | пусто = без ограничения (warning в лог) |
| `FLASK_API_TOKEN` | рекомендуется | токен API (`X-API-Token` или `Bearer`) | пусто = только localhost |
| `FLASK_PORT` | нет | порт при запуске `flask_app.py` | `5000` |

### Как узнать свой Telegram user id

Напишите любому боту вроде `@userinfobot` или посмотрите в логах при `/start`: строка `user_id=…`.

Пример:

```env
TELEGRAM_ALLOWED_IDS=123456789,987654321
FLASK_API_TOKEN=change-me-to-a-long-secret
```

---

## 5. Запуск

### Telegram-канал (бот)

```bash
source .venv/bin/activate
python bot.py
```

Логи: консоль + `logs/bot.log`.

### CLI

```bash
python main.py sample_dialog.txt --type ar
python main.py --kp
python main.py --kp --with-fz --with-engineering sample_dialog.txt
python main.py --serve --host 127.0.0.1 --port 5000
```

### Flask напрямую

```bash
python flask_app.py
# слушает 127.0.0.1:FLASK_PORT, debug=False
```

### Go API Server

Альтернативный HTTP-сервер на Go (те же маршруты, порт по умолчанию **5001**):

```bash
cd go_server
go run ./cmd/server
```

Полная инструкция: [`go_server/README.md`](../go_server/README.md).  
Спецификация OpenAPI 3.1: [`openapi.yaml`](openapi.yaml).

---

## 6. Сценарий менеджера (бот)

```text
/start
  → прислать .txt или текст транскрибации
  → оценка достаточности (score, чего не хватает)
  → если can_form_kp: выбор варианта КП
  → АР: да/нет
  → ИР: да/нет
  → сборка пакета (1–3 минуты, особенно с АР)
  → действия:
       📥 Скачать файлы
       📄 Собрать все в один документ
       🗜 ZIP
       ✉️ E-mail (пока stub)
       🔄 Новый звонок
```

### Варианты КП

| Ключ | Название в боте | Содержание |
|------|-----------------|------------|
| `basic` | Базовый | Газобетон · базовый тёплый контур |
| `plus` | Средний + | Газобетон · усиленный |
| `optimal` | Средний (оптимальный) | Клееный брус · средний |

### Команды

| Команда | Действие |
|---------|----------|
| `/start` | новая сессия, ожидание транскрибации |
| `/help` | краткая справка |

### Ограничения ввода

- `.txt` до **2 МБ**;
- устаревшие inline-кнопки после `/start` обрабатываются с подсказкой перезапустить сценарий;
- на одного пользователя — один тяжёлый job (package/combine) одновременно (lock).

---

## 7. CLI (`main.py`)

```bash
python main.py [FILE] [опции]
```

| Опция | Описание |
|-------|----------|
| `FILE` | путь к транскрибации (или stdin) |
| `-t` / `--type` | `client` \| `design` \| `ar` \| `engineering` (или `1`–`4`, `ir`) |
| `--ar` | сокращение для АР |
| `--engineering` | сокращение для ИР |
| `--kp` | сгенерировать 3 КП |
| `--with-fz` | с `--kp`: добавить ФЗ (фасад) |
| `--with-engineering` | с `--kp`: пакет ИР в смету + PDF |
| `--serve` | запустить Flask |
| `--host` / `--port` | хост/порт для `--serve` |
| `--no-open` | не открывать PDF в системном просмотрщике |

Примеры:

```bash
python main.py sample_dialog.txt -t client
python main.py sample_dialog.txt --ar --no-open
python main.py --kp --with-engineering sample_dialog.txt
```

---

## 8. HTTP API (`flask_app.py`)

Базовый URL по умолчанию: `http://127.0.0.1:5000`

### Авторизация

- если задан `FLASK_API_TOKEN` — обязателен заголовок:
  - `X-API-Token: <token>` **или**
  - `Authorization: Bearer <token>`
- если токен **не** задан — запросы принимаются **только** с `127.0.0.1` / `::1`
- лимит тела запроса: **2 МБ** (`MAX_CONTENT_LENGTH`)

### `GET /health`

```bash
curl http://127.0.0.1:5000/health
# {"status":"ok"}
```

### `POST /api/report`

Тело JSON:

```json
{
  "text": "текст транскрибации…",
  "type": "client"
}
```

`type`: `client` | `design` | `ar` | `engineering` (алиасы `1`–`4`, `ir`).

Либо `multipart/form-data` с полем `file` и опционально `type`.

Ответ: PDF (`application/pdf`).

```bash
curl -X POST http://127.0.0.1:5000/api/report \
  -H "X-API-Token: $FLASK_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"…","type":"ar"}' \
  --output report.pdf
```

### `POST /api/kp`

```json
{
  "with_fz": false,
  "with_engineering": true,
  "text": "опционально для AI-брифа ИР",
  "client_name": "Иван"
}
```

Ответ JSON со списком относительных путей к файлам.

---

## 9. Архитектура и модули

```text
bot.py / main.py / flask_app.py
        │
        ▼
┌───────────────────────────────────────┐
│                 utils/                │
│  sufficiency → package_builder        │
│       │              │                │
│       │         kp_generator          │
│       │         engineering_generator │
│       │         report_service        │
│       │              │                │
│  ai_processor / image_generator       │
│              │                        │
│         pdf_generator (Jinja+Weasy)   │
│  combined_document (pypdf merge)      │
└───────────────────────────────────────┘
        │
        ▼
   reports/  +  templates/  +  fonts/
```

| Модуль | Назначение |
|--------|------------|
| `utils/ai_processor.py` | Chat Completions → структурированный JSON |
| `utils/image_generator.py` | генерация PNG (экстерьер, план) |
| `utils/pdf_generator.py` | рендер HTML → PDF |
| `utils/report_service.py` | пайплайны client/design/ar/engineering |
| `utils/kp_generator.py` | 3 варианта КП, цены, ФЗ/ИР |
| `utils/engineering_generator.py` | проект ИР + смета пакета |
| `utils/package_builder.py` | пакет одного варианта для бота |
| `utils/combined_document.py` | сводная смета + merge PDF |
| `utils/sufficiency.py` | проверка готовности к КП |
| `utils/config.py` | env, типы отчётов, allowlist, sanitize |
| `utils/money.py` | форматирование сумм |
| `utils/logging_setup.py` | консоль + `logs/bot.log` |

Шаблоны PDF: `templates/*.html` (Jinja2, autoescape включён).

---

## 10. Типы документов и цены

| Документ | Содержание |
|----------|------------|
| **КП** | Тёплый контур: работы, материалы, ориентировочная стоимость |
| **АР** | Бриф + AI-визуализация экстерьера + план помещений |
| **ИР** | Инженерные системы + базовая смета (~1 580 000 ₽ пакета) |
| **Сводный PDF** | Титульная смета по 3 вариантам + страницы КП + опционально АР/ИР |
| **Клиентский / design** | Аналитические отчёты через CLI/API |

Цены — **ориентировочные**. Финал — после выезда и спецификации.

### Семантика сводной сметы

- **Тёплый контур** уже включает *рабочий* комплект АР/КР.
- **Презентационный АР** (180 000 ₽) — отдельно (визуализация + план); входит в итог только если менеджер выбрал АР.
- **ИР** входит в итог сводной только если выбран ИР.
- Страницы КП внутри сводного PDF показывают **только контур** (без повторного включения ИР в таблицу КП).
- В **пакете менеджера** при выборе ИР пакет инженерки **добавляется в цену** этого КП.

Пример (вариант «Базовый»):

| Опции | Итог сводной |
|-------|--------------|
| только контур | 3 350 000 |
| контур + АР | 3 530 000 |
| контур + ИР | 4 930 000 |
| контур + АР + ИР | 5 110 000 |

---

## 11. Безопасность

1. Не коммитьте `.env` и живые ключи.
2. Задайте `TELEGRAM_ALLOWED_IDS` перед публичным использованием бота.
3. Для Flask вне localhost задайте `FLASK_API_TOKEN`.
4. Не публикуйте `debug=True` и не биндите API на `0.0.0.0` без токена и сети.
5. LLM-текст в Telegram HTML экранируется (`html.escape`).
6. Скачивание image URL ограничено allowlist хостов OpenAI/Azure Blob.
7. Подробности исключений пишутся в лог; пользователю — нейтральное сообщение.

Подробный разбор рисков и правок: [`AUDIT.md`](../AUDIT.md).

---

## 12. Логи и артефакты

| Путь | Содержимое |
|------|------------|
| `logs/bot.log` | логи бота / utils / CLI / Flask (когда вызван `setup_logging`) |
| `reports/` | PDF/HTML/JSON отчётов (в git не попадают) |
| `reports/kp/` | КП, `bot_*`, `combined_*`, `batch_*` |
| `reports/engineering/` | проекты ИР |
| `reports/images/` | сгенерированные PNG |

Эталон для sufficiency: `sample_dialog.txt`.

---

## 13. Разработка и расширение

### Добавить позицию в смету КП

Правьте списки позиций в `utils/kp_generator.py` (`build_variants` → `raw1` / `raw2` / `raw3`) и при необходимости `FZ_PACKAGES` / `ENGINEERING_PACKAGE`.

### Добавить поле в PDF

1. Расширьте промпт и `_normalize_fields` в `ai_processor.py` (если данные от LLM).
2. Добавьте переменную в соответствующий шаблон `templates/*.html`.

### Тестовый прогон без Telegram

```bash
python main.py sample_dialog.txt --type engineering --no-open
python main.py --kp --no-open
```

### Roadmap (из README)

- актуальные прайсы из БД / 1С;
- реальная отправка e-mail;
- выгрузка в CRM;
- ТЗ для внешнего инженера.

---

## 14. Известные ограничения

| Ограничение | Комментарий |
|-------------|-------------|
| E-mail в Telegram-боте | В боте stub; **в CRM** отправка КП по SMTP реализована (`SMTP_*`) |
| FSM бота | `MemoryStorage` — сессия теряется при рестарте процесса |
| Demo-данные объекта | Площадь/участок по умолчанию шаблонные; имя берётся из LLM |
| Combine | 3 страницы КП пересобираются; АР/ИР переиспользуются из пакета |
| Стоимость API | АР с картинками заметно дороже текстовых вызовов |
| Сеть VPS РФ | OpenAI — через NL-прокси; Telegram — пин DC в `/etc/hosts` |

---

## 15. Связанные файлы

| Файл | Описание |
|------|----------|
| [`README.md`](../README.md) | краткий обзор и быстрый старт |
| [`requirements.txt`](../requirements.txt) | Python-зависимости |
| [`.env.example`](../.env.example) | шаблон окружения |
| [`AUDIT.md`](../AUDIT.md) | объединённый аудит кода |
| [`ABOUT.md`](../ABOUT.md) | short About для GitHub |
| [`docs/openapi.yaml`](openapi.yaml) | OpenAPI 3.1 — HTTP API (Go / Flask) |
| [`go_server/openapi.yaml`](../go_server/openapi.yaml) | копия OpenAPI рядом с Go-сервером |
| [`docs/РУКОВОДСТВО_МЕНЕДЖЕРА.md`](РУКОВОДСТВО_МЕНЕДЖЕРА.md) | UX для менеджеров ОП |
| [`docs/OPS_CRM.md`](OPS_CRM.md) | production: systemd, proxy, health, деплой |
| [`docs/ОТЧЁТ_ДЛЯ_КУРАТОРА_AI_автоматизация.md`](ОТЧЁТ_ДЛЯ_КУРАТОРА_AI_автоматизация.md) | отчёт для куратора |
| [`LICENSE`](../LICENSE) | MIT |

---

## 16. OfferDesk CRM и production

Веб-CRM OfferDesk (`web_app/`): сделки, эталон заполнения, генерация/утверждение/отправка КП, дашборд, справка `/help`.

| Что | Где |
|-----|-----|
| Entry | `web_app/app.py` (Waitress `:5001`) |
| Сделки | `web_app/routes_deals.py` |
| Эталон % | `web_app/etalon_score.py` |
| Systemd | `deploy/systemd/dommaster-*.service` |
| Деплой | `scripts/update_server.sh` |
| Health | `scripts/health_check.sh`, `GET /health?deep=1` |

Полное ops-описание (прокси NL, ufw, logrotate, troubleshooting): **[`OPS_CRM.md`](OPS_CRM.md)**.  
Инструкция для ОП: **[`РУКОВОДСТВО_МЕНЕДЖЕРА.md`](РУКОВОДСТВО_МЕНЕДЖЕРА.md)**.

Локальный запуск CRM:

```bash
cd web_app
PYTHONPATH=.. python3 app.py
# http://127.0.0.1:5001
```

На production управляйте только через systemd (`dommaster-crm` / `dommaster-bot`), не через `nohup`.

---

## Лицензия и автор

Проект распространяется под лицензией [MIT](../LICENSE).  
Автор: [PavelKoff2025](https://github.com/PavelKoff2025).
