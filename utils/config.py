"""Общие константы и разбор env-конфигурации."""

from __future__ import annotations

import os
from functools import lru_cache

# Единый словарь типов отчётов для CLI / Flask / report_service
REPORT_TYPE_ALIASES: dict[str, str] = {
    "1": "client",
    "client": "client",
    "2": "design",
    "design": "design",
    "3": "ar",
    "ar": "ar",
    "4": "engineering",
    "engineering": "engineering",
    "ir": "engineering",
}

DEFAULT_CLIENT_NAME = "Заказчик"
MAX_DIALOG_CHARS = 200_000
MAX_UPLOAD_BYTES = 2_000_000


def resolve_report_type(raw: str | None) -> str:
    """Нормализует алиас типа отчёта → каноническое имя."""
    if not raw:
        raise ValueError("Тип отчёта не указан")
    key = raw.strip().lower()
    if key not in REPORT_TYPE_ALIASES:
        raise ValueError(
            "Тип: client | design | ar | engineering (или 1–4 / ir)"
        )
    return REPORT_TYPE_ALIASES[key]


@lru_cache(maxsize=1)
def telegram_allowed_ids() -> frozenset[int]:
    """TELEGRAM_ALLOWED_IDS=123,456 — пусто = без ограничения (с предупреждением в логе)."""
    raw = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return frozenset(ids)


def flask_api_token() -> str:
    return os.getenv("FLASK_API_TOKEN", "").strip()


def sanitize_client_name(name: str | None, fallback: str = DEFAULT_CLIENT_NAME) -> str:
    value = (name or "").strip()
    if not value or value.lower() in {"не указано", "none", "null", "-"}:
        return fallback
    # Ограничиваем длину для PDF/Telegram
    return value[:80]
