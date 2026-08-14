# Changelog

Все значимые изменения проекта **OfferDesk** (рабочее место ОП «Дом-Мастер»).

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

## [1.0.0] — 2026-08-13

Первый продакшен-релиз: Telegram-бот + веб-CRM на VPS (BlueTerbium),
генерация КП тёплого контура, health-мониторинг.

### Добавлено

- Веб-CRM (`web_app/`): сделки, дашборд, эталон заполнения, генерация / утверждение / отправка КП.
- Проверка протокола по RAG-эталону (`knowledge_base/etalon_protocol.md`), порог КП (по умолчанию 80%).
- Страница недостающих данных со скриптом уточняющих вопросов.
- КП этапа «Стройка»: WeasyPrint, 41 000 ₽/м², водяной знак, стандарты и комплектации в RAG.
- Отправка КП по email (SMTP) и в Telegram; outbox, если API Telegram недоступен с VPS.
- Пайплайн статусов, таймлайн (`action_log`), напоминания по сделкам без действий > 3 дней.
- Вкладки карточки сделки (Основное / КП / История / Файлы) и аналитика на дашборде.
- Демо-протоколы, admin API, статистика над таблицей сделок.
- HTTP `/triage` — классификация обращений.
- Production: systemd (`dommaster-crm` / `dommaster-bot` / health timer), logrotate, NL-прокси OpenAI.
- Скрипты: `update_server.sh`, `health_check.sh`, `e2e_crm.sh`, `load_test_crm.sh`, `install_systemd.sh`.
- Документация: руководство менеджера, OPS, OpenAPI 3.1, Docker Hub.

### Исправлено

- Генерация КП через прокси: таймаут OpenAI / Waitress, повтор без AI при обрыве сети.
- Доступ VPS к Telegram API: pin рабочего DC в `/etc/hosts`.
- Стабильный pin Telegram в `update_server.sh` (без вложенного heredoc).
- График на дашборде: переменные передаются из view, а не из `{% set %}` внутри content.
- Парсер телефонов: `+7` / `8` / компактные номера.

### Безопасность и ops

- OpenAI только через NL-прокси (`OPENAI_PROXY`); Telegram — отдельным каналом.
- Health-check каждые 5 минут + алерт в Telegram при FAIL.
- Бэкап `web_app/deals.db` при каждом деплое.

## [Unreleased]

### Изменено

- Продукт закреплён под именем **OfferDesk**. «Дом-Мастер» — заказчик (бренд в КП и письмах). Telegram — канал, не название системы.

### Планируется

- Актуальные прайсы из БД / 1С.
- ТЗ для внешнего инженера.
- Выгрузка в внешнюю CRM.

[1.0.0]: https://github.com/PavelKoff2025/AI_Bot_avto_KP/releases/tag/v1.0.0
