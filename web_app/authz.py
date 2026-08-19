"""Права CRM: удаление сделок только у администратора сервиса."""

from __future__ import annotations

import os

from flask import session

DENY_DELETE_MSG = (
    "Для удаления сделки обратитесь к администратору сервиса."
)

DENY_ADMIN_ACTION_MSG = (
    "Это действие доступно только администратору сервиса. "
    "Обратитесь к администратору."
)


def admin_usernames() -> set[str]:
    """Логины админов: всегда `admin` + CRM_ADMIN_USERS из .env (через запятую)."""
    names = {"admin"}
    extra = os.getenv("CRM_ADMIN_USERS", "")
    for part in extra.split(","):
        item = part.strip().lower()
        if item:
            names.add(item)
    return names


def is_service_admin() -> bool:
    username = (session.get("username") or "").strip().lower()
    return bool(username) and username in admin_usernames()
