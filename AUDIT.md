# Аудит проекта OfferDesk (историческое имя папки: AI_Auogeneration)

**Дата:** 2026-08-04  
**Объём:** пакет `utils/` + весь проект (`bot.py`, `main.py`, `flask_app.py`, шаблоны, конфиг)  
**Цель:** найти баги, риски безопасности и точки рефакторинга; часть правок уже внесена в код.

---

## Краткий вердикт

Прототип связный: транскрибация → проверка достаточности → пакет КП (±АР/ИР) → сводный PDF → ZIP.

Главные блокеры продакшена:

1. открытый доступ (Telegram-бот без allowlist, Flask API без auth);
2. hardcoded имя заказчика «Иван»;
3. расхождение семантики цен (пакет vs сводный PDF);
4. дорогая повторная генерация АР/ИР при «Собрать все»;
5. утечки текста exception в UX / API.

Большая часть этого **исправлена** в коде. Открытыми остаются: stub e-mail, `MemoryStorage` FSM (теряется при рестарте), персонализация объекта (площадь/участок по-прежнему шаблонные).

Отдельного файла `utils.py` нет — это пакет `utils/` (~12–13 модулей).

---

## 1. Архитектура

```text
.txt / текст ──▶ bot.py (Telegram FSM, prod UX)
                    │
                    ├─ sufficiency (LLM)
                    ├─ package_builder (1 КП ± АР/ИР)
                    └─ combined_document (смета + 3 КП ± АР/ИР) → ZIP

файл / stdin ──▶ main.py (CLI)
                    │
                    └─ --serve ──▶ flask_app.py (/api/report, /api/kp)

utils/: AI (OpenAI) → Jinja2 templates → WeasyPrint PDF (+ pypdf merge)
```

| Слой | Роль | Статус после аудита |
|------|------|---------------------|
| `bot.py` | Прод UX: sufficiency → package → combine/ZIP | hardened |
| `main.py` | CLI отчёты / `--kp` / `--serve` | logging + fail louder |
| `flask_app.py` | HTTP API | auth + limits + `debug=False` |
| `utils/` | AI → Jinja → WeasyPrint / merge | hardening + рефакторинг |
| `templates/` | PDF layouts | legend sync |

### Модули `utils/`

| Файл | Назначение |
|------|------------|
| `ai_processor.py` | OpenAI chat → JSON-брифы |
| `image_generator.py` | OpenAI Images → PNG |
| `pdf_generator.py` | Jinja2 → WeasyPrint PDF |
| `report_service.py` | Пайплайны отчётов |
| `kp_generator.py` | Варианты КП, цены, PDF |
| `engineering_generator.py` | ИР + смета |
| `package_builder.py` | Пакет менеджера (1 вариант) |
| `combined_document.py` | Сводный PDF |
| `sufficiency.py` | Достаточность транскрибации |
| `logging_setup.py` | Логи |
| `money.py` | `format_money` |
| `config.py` | Env, типы отчётов, allowlist |

---

## 2. Модель цен (вариант basic)

После правок итог **сводной сметы** зависит от выбранных опций АР/ИР:

| Путь / опции | Контур | Презент. АР | ИР | Итого |
|--------------|--------|-------------|-----|-------|
| Страницы КП в сводном PDF | 3 350 000 | — | не в цене | **3 350 000** |
| Пакет менеджера (КП + ИР) | 3 350 000 | — | в цене КП | **4 930 000** |
| Сводная: только контур | 3 350 000 | — | — | **3 350 000** |
| Сводная: контур + АР | 3 350 000 | +180 000 | — | **3 530 000** |
| Сводная: контур + ИР | 3 350 000 | — | +1 580 000 | **4 930 000** |
| Сводная: контур + АР + ИР | 3 350 000 | +180 000 | +1 580 000 | **5 110 000** |

**Важно:** презентационный АР (180 000 ₽) — отдельно от рабочего комплекта АР/КР, который уже входит в тёплый контур. Это две разные услуги, не двойной счёт.

Семантика:

- **страницы КП** в сводном документе — только тёплый контур (без ИР в таблице);
- **пакет менеджера** при `with_engineering=True` — ИР входит в цену одного КП;
- **сводная смета** — контур + выбранные опции АР/ИР.

---

## 3. Находки: пакет `utils/`

### P0

| Файл | Проблема | Статус | Фикс |
|------|----------|--------|------|
| `combined_document.py` | Три разных итога для одного варианта (пакет / КП-страницы / сводная) без явной семантики | **fixed** | Зафиксирована и задокументирована модель цен; обновлены note/legend/docstrings |
| `sufficiency.py` | LLM-текст в Telegram HTML без escape → injection / ломаный `parse_mode` | **fixed** | `html.escape` на пользовательских/LLM полях |
| `flask_app.py` | API без auth (на момент аудита utils — вне scope) | **fixed** позже | См. раздел «весь проект» |

### P1

| Файл | Проблема | Статус | Фикс |
|------|----------|--------|------|
| `engineering_generator.py` | Текст `Exception` попадал в PDF заказчику | **fixed** | Лог + нейтральный fallback |
| `report_service.py` | `create_report` молча отдавал client при опечатке типа | **fixed** | `ValueError` + whitelist типов |
| `combined_document.py` | `merge_pdfs` пропускал отсутствующие файлы | **fixed** | `FileNotFoundError` / `ValueError` |
| `kp_generator.py` | `generate_all_kp` писал фиксированные имена в общий `KP_DIR` (гонки) | **fixed** | Подпапка `batch_YYYYMMDD_HHMMSS` |
| `ai_processor.py` | Импорт приватных `_chat_json` / `_get_client` | **fixed** | Публичные `chat_json` / `get_openai_client` |

### P2 / рефакторинг

| Тема | Статус | Фикс |
|------|--------|------|
| Дубли `_fmt`, `print` вместо logging | **fixed** | `utils/money.format_money`; logging в report/kp/engineering |
| Хрупкий JSON extract | **fixed** | Устойчивый `_extract_json` |
| SSRF при скачивании image URL | **fixed** | Allowlist HTTPS-хостов |
| Пустой эталон без предупреждения | **fixed** | Warning в лог при отсутствии `sample_dialog.txt` |
| Image fallback без лога | **fixed** | `logger.exception` перед fallback на dall-e-3 |

### Что уже было хорошо в utils

- Bot offload через `asyncio.to_thread`
- Jinja2 autoescape для PDF HTML
- `.env` в `.gitignore`
- Проверка placeholder API-ключа

---

## 4. Находки: весь проект

### P0

| Файл | Проблема | Статус | Фикс |
|------|----------|--------|------|
| `bot.py` | Бот открыт любому → burn OpenAI | **fixed** | `TELEGRAM_ALLOWED_IDS`; warning если пусто |
| `flask_app.py` | Без auth, `debug=True`, утечка `str(exc)`, без лимита тела | **fixed** | Токен / loopback-only; `MAX_CONTENT_LENGTH`; `debug=False`; generic 500 |
| `bot` + KP/IR | `client_name="Иван"` всегда | **fixed** | Имя из sufficiency LLM → FSM → package/combine/KP/IR |

### P1

| Файл | Проблема | Статус | Фикс |
|------|----------|--------|------|
| `combined_document.py` | Смета всегда +АР+ИР даже при «Нет» | **fixed** | Итог зависит от `with_ar` / `with_engineering` |
| combine в боте | Повторная генерация АР/ИР (деньги + время) | **fixed** | `existing_ar` / `existing_engineering` reuse |
| `bot.py` | `KeyError` на `variant_key`; double-tap jobs; stale buttons; exc в чат | **fixed** | Defensive FSM; per-user lock; catch-all callback; sanitized errors |
| Типы отчётов | Дубли map в CLI / Flask / report_service | **fixed** | `utils/config.REPORT_TYPE_ALIASES` |
| `main.py` | `--kp --with-engineering` молча глотал ошибку чтения файла | **fixed** | Сообщение в stderr + лог |

### P2 / открыто

| Тема | Статус | Комментарий |
|------|--------|-------------|
| E-mail кнопка | **open** | Stub; нужен SMTP или скрыть кнопку |
| `MemoryStorage` FSM | **open** | Теряется при рестарте; нужен Redis/persistent storage |
| Demo-данные объекта | **open** | Площадь/участок/менеджер всё ещё шаблонные |
| Клиентский report branding | **open** | «AI Client Report» vs бренд «Дом-Мастер» в КП |
| Зависимости | **open** | Majors не закреплены жёстко; нет тестов в CI |
| `docs/*.pdf` | **open** | Крупные демо-бинарники в репозитории |

---

## 5. Безопасность (сводка)

| Риск | Было | Стало |
|------|------|-------|
| Telegram без allowlist | Любой мог жечь API | `TELEGRAM_ALLOWED_IDS` |
| Flask без токена | Открытый burn OpenAI | `FLASK_API_TOKEN` или только localhost |
| Flask `debug=True` | Риск Werkzeug debugger | `debug=False` |
| HTML injection в sufficiency | LLM → Telegram HTML | `html.escape` |
| SSRF image URL | Любой URL от API | Allowlist хостов |
| Exception в PDF / чат / API | Утечка внутренних деталей | Лог серверно; нейтральный UX |
| `.env` с живыми ключами | Локально (в git не коммитится) | Не коммитить; ротировать при утечке |

### Рекомендуемые ключи в `.env`

```env
TELEGRAM_ALLOWED_IDS=123456789
FLASK_API_TOKEN=секретный_токен
FLASK_PORT=5000
```

Без allowlist бот пишет warning и остаётся открытым.  
Без Flask-токена API доступен только с `127.0.0.1` / `::1`.

---

## 6. Надёжность и UX

| Тема | Статус |
|------|--------|
| Per-user asyncio lock на package/combine | **fixed** |
| Catch-all для устаревших inline-кнопок | **fixed** |
| Sanitize user-facing errors | **fixed** |
| Reuse АР/ИР при combine | **fixed** |
| E-mail — stub | **open** |
| FSM не переживает рестарт | **open** |
| Нет rate-limit / токен-бюджета на длинные тексты | **open** (есть лимит файла 2 МБ) |

---

## 7. Рефакторинг, сделанный по итогам

- `utils/money.py` — единый `format_money`
- `utils/config.py` — типы отчётов, allowlist, sanitize имени, лимиты upload
- Публичные `chat_json` / `get_openai_client`
- Logging вместо `print` в report/kp; logging в CLI/Flask
- Уникальные пути PDF (секунды / `batch_*`)
- Прокидка `client_name` через KP / IR / package / combined
- Обновлён `.env.example`

---

## 8. Рекомендации дальше (бэклог)

### Высокий приоритет

1. Заполнить `TELEGRAM_ALLOWED_IDS` и `FLASK_API_TOKEN` в рабочем `.env`.
2. Реализовать e-mail или убрать/скрыть кнопку до готовности.
3. Persistent FSM (Redis), если важны рестарты без потери сессий.

### Средний

4. Доставать из транскрибации не только имя, но и площадь/участок/бюджет в КП.
5. Unit-тесты на `BOT_VARIANTS` index mapping и паритет цен.
6. Закрепить версии зависимостей; короткий smoke-test в CI.
7. Не коммитить крупные PDF в `docs/` (или `.gitignore`).

### Низкий

8. Единый брендинг клиентского отчёта под «Дом-Мастер».
9. Очистка orphan-копий AR в `reports/`.
10. Кэш/reuse уже собранных страниц КП при combine (сейчас пересобираются 3 КП; АР/ИР уже reuse).

---

## 9. Изменённые файлы (по итогам двух аудитов)

```
.env.example
bot.py
flask_app.py
main.py
templates/combined_summary_template.html
utils/__init__.py
utils/ai_processor.py
utils/combined_document.py
utils/config.py          (новый)
utils/engineering_generator.py
utils/image_generator.py
utils/kp_generator.py
utils/logging_setup.py
utils/money.py           (новый)
utils/package_builder.py
utils/pdf_generator.py
utils/report_service.py
utils/sufficiency.py
```

---

## 10. Источники

Аудит выполнен в два прохода в одной сессии Cursor:

1. **Аудит `utils/`** — debug + рефакторинг пакета утилит.
2. **Аудит всего проекта** — entry points, безопасность, UX, сквозные баги.

Интерактивные сводки (Canvas):

- `utils-audit.canvas.tsx`
- `project-audit.canvas.tsx`

Этот файл — объединённая текстовая версия обоих аудитов для хранения в репозитории.
