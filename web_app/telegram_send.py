"""Отправка КП в Telegram через Bot API."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib import error, request


def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def telegram_configured() -> bool:
    token = _bot_token()
    return bool(token and token != "your_telegram_bot_token_here")


def resolve_chat_id(raw: Any) -> str | None:
    """Числовой chat_id или строка вида '123456789'. @username без dial — нельзя."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d{5,20}", text):
        return text
    # иногда хранят tg://user?id=123
    m = re.search(r"id=(\d{5,20})", text)
    if m:
        return m.group(1)
    return None


def resolve_deal_chat_id(deal: dict) -> str | None:
    """Приоритет: telegram_chat_id → числовой client_telegram."""
    return resolve_chat_id(deal.get("telegram_chat_id")) or resolve_chat_id(
        deal.get("client_telegram")
    )


def send_kp_telegram(
    *,
    chat_id: str,
    pdf_path: str | Path,
    caption: str | None = None,
) -> dict[str, Any]:
    token = _bot_token()
    if not telegram_configured():
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF не найден: {path}")

    boundary = "----DomMasterKPBoundary7MA4YWxkTrZu0gW"
    url = f"https://api.telegram.org/bot{token}/sendDocument"

    file_bytes = path.read_bytes()
    filename = path.name
    cap = (caption or "Коммерческое предложение «Дом Мастер»")[:1024]

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{chat_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="caption"\r\n\r\n'
        f"{cap}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Нет связи с Telegram API: {exc}") from exc

    if '"ok":true' not in raw.replace(" ", "").lower() and '"ok": true' not in raw:
        # мягкая проверка
        if '"ok":false' in raw.replace(" ", "").lower() or '"ok": false' in raw:
            raise RuntimeError(f"Telegram отклонил отправку: {raw[:500]}")

    return {"ok": True, "chat_id": chat_id, "method": "telegram", "response": raw[:300]}
