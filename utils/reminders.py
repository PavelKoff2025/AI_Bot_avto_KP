"""Напоминания по «зависшим» сделкам (нет действий > N дней)."""

from __future__ import annotations

import logging
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error, parse, request

_WEB_APP = Path(__file__).resolve().parent.parent / "web_app"
if str(_WEB_APP) not in sys.path:
    sys.path.insert(0, str(_WEB_APP))

logger = logging.getLogger(__name__)

STALE_DAYS = int(os.getenv("CRM_STALE_DAYS", "3"))
# Не спамить: повторное напоминание по сделке не чаще чем раз в N часов
REMINDER_COOLDOWN_HOURS = int(os.getenv("CRM_REMINDER_COOLDOWN_HOURS", "24"))


def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _manager_chat_ids() -> list[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip().isdigit()]


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def last_activity_at(conn: sqlite3.Connection, deal: sqlite3.Row | dict) -> datetime | None:
    """Последнее действие: action_log → delivery_date → created_at."""
    deal_id = deal["id"] if not isinstance(deal, dict) else deal.get("id")
    get = deal.get if isinstance(deal, dict) else deal.__getitem__

    try:
        from models import ensure_action_log_table

        ensure_action_log_table(conn)
        row = conn.execute(
            "SELECT created_at FROM action_log WHERE deal_id = ? ORDER BY id DESC LIMIT 1",
            (deal_id,),
        ).fetchone()
        if row:
            ts = _parse_ts(row[0] if not isinstance(row, sqlite3.Row) else row["created_at"])
            if ts:
                return ts
    except Exception:  # noqa: BLE001
        pass

    for key in ("delivery_date", "created_at"):
        try:
            ts = _parse_ts(get(key))
        except (KeyError, IndexError, TypeError):
            ts = None
        if ts:
            return ts
    return None


def find_stale_deals(
    conn: sqlite3.Connection,
    *,
    stale_days: int = STALE_DAYS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Сделки без активности > stale_days, не в completed/lost."""
    from models import normalize_status

    now = now or datetime.now()
    cutoff = now - timedelta(days=stale_days)
    rows = conn.execute(
        """
        SELECT id, client_name, status, created_at, delivery_date, last_reminder, user_id
        FROM deals
        WHERE COALESCE(status, 'new') NOT IN ('completed', 'lost', 'won')
        """
    ).fetchall()

    stale: list[dict[str, Any]] = []
    for row in rows:
        deal = dict(row)
        status = normalize_status(deal.get("status"))
        if status in {"completed", "lost"}:
            continue
        activity = last_activity_at(conn, deal)
        if activity is None or activity > cutoff:
            continue
        idle_days = (now - activity).days
        deal["status"] = status
        deal["last_activity"] = activity.strftime("%Y-%m-%d %H:%M")
        deal["idle_days"] = idle_days
        stale.append(deal)
    return stale


def _cooldown_ok(deal: dict[str, Any], *, now: datetime) -> bool:
    last = _parse_ts(deal.get("last_reminder"))
    if last is None:
        return True
    return now - last >= timedelta(hours=REMINDER_COOLDOWN_HOURS)


def send_telegram_text(chat_id: str, text: str) -> None:
    token = _bot_token()
    if not token or token == "your_telegram_bot_token_here":
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = parse.urlencode(
        {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": "1"}
    ).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Нет связи с Telegram API: {exc}") from exc
    if '"ok":false' in raw.replace(" ", "").lower():
        raise RuntimeError(f"Telegram отклонил сообщение: {raw[:400]}")


def _crm_base_url() -> str:
    return (
        os.getenv("CRM_PUBLIC_URL", "").strip().rstrip("/")
        or f"http://{os.getenv('BLUETERBIUM_SSH_HOST', '127.0.0.1').strip()}:5001"
    )


def format_reminder_message(deals: list[dict[str, Any]]) -> str:
    base = _crm_base_url()
    lines = [
        f"⏰ Напоминание CRM «Дом-Мастер»",
        f"Сделки без действий > {STALE_DAYS} дн.: {len(deals)}",
        "",
    ]
    for deal in deals[:15]:
        name = (deal.get("client_name") or "без имени").strip()
        lines.append(
            f"• #{deal['id']} {name} — {deal.get('idle_days', '?')} дн. "
            f"({deal.get('status')}) {base}/deals/{deal['id']}"
        )
    if len(deals) > 15:
        lines.append(f"… и ещё {len(deals) - 15}")
    return "\n".join(lines)


def process_reminders(
    conn: sqlite3.Connection,
    *,
    notify: bool = True,
    stale_days: int = STALE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Находит зависшие сделки, шлёт сводку менеджерам в Telegram,
    пишет last_reminder + action_log.
    """
    from models import log_action

    now = now or datetime.now()
    stale = find_stale_deals(conn, stale_days=stale_days, now=now)
    due = [d for d in stale if _cooldown_ok(d, now=now)]

    result: dict[str, Any] = {
        "stale_total": len(stale),
        "due": len(due),
        "notified": 0,
        "errors": [],
        "deals": stale,
    }
    if not due:
        return result

    managers = _manager_chat_ids()
    if notify and managers:
        text = format_reminder_message(due)
        for chat_id in managers:
            try:
                send_telegram_text(chat_id, text)
                result["notified"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("reminder notify failed chat=%s: %s", chat_id, exc)
                result["errors"].append(str(exc))
    elif notify and not managers:
        result["errors"].append("TELEGRAM_ALLOWED_IDS пуст — уведомление не отправлено")

    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    for deal in due:
        conn.execute(
            "UPDATE deals SET last_reminder = ? WHERE id = ?",
            (stamp, deal["id"]),
        )
        log_action(
            conn,
            deal_id=int(deal["id"]),
            action="reminder_sent",
            detail=f"Простой {deal.get('idle_days')} дн. (порог {stale_days})",
            user_id=None,
        )
    conn.commit()
    return result
