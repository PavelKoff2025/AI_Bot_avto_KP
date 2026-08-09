"""Привязка Telegram chat_id к сделкам CRM (общая БД web_app/deals.db)."""

from __future__ import annotations

import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib import error, request

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "web_app" / ".env")

DEFAULT_DEALS_DB = PROJECT_ROOT / "web_app" / "deals.db"


def deals_db_path() -> Path:
    raw = os.getenv("DEALS_DB_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_DEALS_DB


def _connect() -> sqlite3.Connection:
    path = deals_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(deals)").fetchall()}
    if "telegram_chat_id" not in cols:
        conn.execute("ALTER TABLE deals ADD COLUMN telegram_chat_id TEXT")
        conn.commit()
    return conn


def bind_telegram_to_deal(
    deal_id: int,
    *,
    chat_id: int,
    username: str | None = None,
) -> dict[str, Any]:
    """Сохраняет chat_id клиента в сделку. Возвращает краткую карточку."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, client_name, client_telegram, telegram_chat_id FROM deals WHERE id = ?",
            (deal_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Сделка #{deal_id} не найдена")

        uname = (username or "").strip().lstrip("@") or None
        # Не затираем @username, если уже был; иначе сохраняем username рядом
        current_tg = (row["client_telegram"] or "").strip()
        new_client_tg = current_tg
        if uname and (not current_tg or current_tg.isdigit()):
            new_client_tg = f"@{uname}"

        conn.execute(
            """
            UPDATE deals
            SET telegram_chat_id = ?,
                client_telegram = COALESCE(NULLIF(?, ''), client_telegram)
            WHERE id = ?
            """,
            (str(chat_id), new_client_tg, deal_id),
        )
        conn.commit()
        return {
            "deal_id": deal_id,
            "client_name": row["client_name"] or "Клиент",
            "chat_id": str(chat_id),
            "username": uname,
        }
    finally:
        conn.close()


def bind_telegram_via_crm_api(
    deal_id: int,
    *,
    chat_id: int,
    username: str | None = None,
) -> dict[str, Any]:
    """
    Пишет chat_id в CRM по HTTP (для случая, когда бот крутится не на VPS).
    CRM_PUBLIC_URL=http://194.67.103.144:5001
    Auth: X-Bot-Token = TELEGRAM_BOT_TOKEN
    """
    base = os.getenv("CRM_PUBLIC_URL", "").strip().rstrip("/")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not base:
        raise RuntimeError("CRM_PUBLIC_URL не задан")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    url = f"{base}/deals/{deal_id}/telegram-bind"
    payload = json.dumps(
        {"chat_id": str(chat_id), "username": username or ""},
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Bot-Token": token,
        },
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CRM {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Нет связи с CRM ({base}): {exc}") from exc

    if not data.get("ok"):
        raise RuntimeError(data.get("message") or "CRM отклонил привязку")
    return data


def get_deal_telegram(deal_id: int) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, client_name, client_telegram, telegram_chat_id FROM deals WHERE id = ?",
            (deal_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def telegram_bot_username() -> str | None:
    """Username бота без @ (из TELEGRAM_BOT_USERNAME или getMe)."""
    # Всегда подхватываем .env заново (процесс CRM стартует из web_app/)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(PROJECT_ROOT / "web_app" / ".env", override=False)

    env_name = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if env_name:
        return env_name

    fetched = _fetch_bot_username_cached()
    return fetched or None


@lru_cache(maxsize=1)
def _fetch_bot_username_cached() -> str:
    """Кэшируем только успешный ответ; пустую строку не считаем успехом навечно."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "your_telegram_bot_token_here":
        return ""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ok"):
            return str((data.get("result") or {}).get("username") or "")
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return ""
    return ""


def clear_bot_username_cache() -> None:
    _fetch_bot_username_cached.cache_clear()


def client_bind_link(deal_id: int) -> str | None:
    username = telegram_bot_username()
    if not username:
        # Последний fallback для «Дом-Мастер» (если getMe с VPS недоступен)
        username = os.getenv("TELEGRAM_BOT_USERNAME_FALLBACK", "stroyka_KP_bot").strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}?start=deal_{deal_id}"
