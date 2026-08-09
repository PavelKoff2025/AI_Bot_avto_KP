"""Фоновая доставка КП из CRM-очереди (когда VPS не достучится до Telegram API)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib import error, request

from aiogram import Bot
from aiogram.types import FSInputFile

from utils.logging_setup import get_logger

logger = get_logger("tg_outbox")


def _crm_base() -> str:
    return os.getenv("CRM_PUBLIC_URL", "").strip().rstrip("/")


def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _headers() -> dict[str, str]:
    return {"X-Bot-Token": _bot_token(), "Content-Type": "application/json"}


def _get_outbox() -> list[dict]:
    base = _crm_base()
    if not base or not _bot_token():
        return []
    url = f"{base}/deals/telegram-outbox"
    req = request.Request(url, headers=_headers(), method="GET")
    try:
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return list(data.get("items") or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("outbox fetch failed: %s", exc)
        return []


def _ack(deal_id: int, *, ok: bool, error: str | None = None) -> None:
    base = _crm_base()
    url = f"{base}/deals/telegram-outbox/{deal_id}"
    body = json.dumps({"ok": ok, "error": error or ""}).encode("utf-8")
    req = request.Request(url, data=body, headers=_headers(), method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("outbox ack failed deal=%s: %s", deal_id, exc)


async def process_outbox_once(bot: Bot) -> int:
    """Отправляет все задания из очереди. Возвращает число успешных."""
    items = await asyncio.to_thread(_get_outbox)
    sent = 0
    for item in items:
        deal_id = int(item.get("deal_id") or 0)
        chat_id = item.get("chat_id")
        pdf_path = item.get("pdf_path")
        caption = item.get("caption") or "КП «Дом Мастер»"
        if not deal_id or not chat_id or not pdf_path:
            continue
        path = Path(str(pdf_path))
        local_pdf = path if path.is_file() else None
        try:
            if local_pdf is None:
                pdf_url = (item.get("pdf_url") or "").strip()
                if pdf_url.startswith("/"):
                    pdf_url = f"{_crm_base()}{pdf_url}"
                if not pdf_url:
                    pdf_url = f"{_crm_base()}/deals/{deal_id}/kp.pdf/bot"
                req = request.Request(pdf_url, headers=_headers(), method="GET")
                with request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                tmp = Path(f"/tmp/kp_deal_{deal_id}.pdf")
                tmp.write_bytes(data)
                local_pdf = tmp
            await bot.send_document(
                chat_id=int(chat_id),
                document=FSInputFile(str(local_pdf)),
                caption=caption[:1024],
            )
            await asyncio.to_thread(lambda: _ack(deal_id, ok=True))
            sent += 1
            logger.info("outbox delivered deal=%s chat=%s", deal_id, chat_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("outbox send failed deal=%s", deal_id)
            err = str(exc)
            await asyncio.to_thread(lambda e=err: _ack(deal_id, ok=False, error=e))
    return sent


async def outbox_loop(bot: Bot, interval_sec: float = 8.0) -> None:
    if not _crm_base():
        logger.warning("CRM_PUBLIC_URL не задан — outbox-воркер выключен")
        return
    logger.info("Telegram outbox worker started → %s", _crm_base())
    while True:
        try:
            await process_outbox_once(bot)
        except Exception:  # noqa: BLE001
            logger.exception("outbox loop error")
        await asyncio.sleep(interval_sec)
