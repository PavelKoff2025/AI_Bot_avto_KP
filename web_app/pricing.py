"""Прайс «Дом-Мастер»: ориентировочная стоимость тёплого контура (ТК)."""

from __future__ import annotations

import json
import re
from typing import Any

# Синхронно с knowledge_base/company_standards.md и utils/stroika_kp.py
PRICE_PER_M2 = 75_000


def is_timber_material(raw: Any) -> bool:
    """Клееный / профилированный брус — не ставка газобетона."""
    text = str(raw or "").lower()
    return "клеен" in text or "брус" in text


def parse_area_m2(raw: Any) -> int | None:
    """Извлекает площадь в м² («150», «150 м2», «120-140 м²» → среднее)."""
    if raw is None:
        return None
    text = str(raw).strip().lower().replace(",", ".")
    if not text:
        return None

    range_match = re.search(
        r"(\d{2,4}(?:\.\d+)?)\s*[–\-—]\s*(\d{2,4}(?:\.\d+)?)",
        text,
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return int(round((low + high) / 2))

    single = re.search(r"(\d{2,4}(?:\.\d+)?)", text)
    if single:
        return int(round(float(single.group(1))))
    return None


def calc_tk_cost(area: Any, price_per_m2: int = PRICE_PER_M2) -> int | None:
    """Ориентировочная стоимость ТК = площадь × 75 000 ₽/м²."""
    area_m2 = parse_area_m2(area)
    if not area_m2:
        return None
    return int(area_m2) * int(price_per_m2)


def format_tk_cost(amount: int | None) -> str:
    if amount is None:
        return ""
    return f"{int(amount):,}".replace(",", " ") + " ₽"


def apply_tk_cost(deal: dict) -> dict:
    """Пишет tk_cost / tk_cost_fmt в dict сделки (из area или уже сохранённого значения)."""
    if is_timber_material(deal.get("material")) or is_timber_material(deal.get("transcript")):
        deal["price_per_m2"] = None
        deal["kp_kind"] = "timber"
        grand = None
        raw_kp = deal.get("kp_options")
        if raw_kp:
            try:
                meta = raw_kp if isinstance(raw_kp, dict) else json.loads(raw_kp)
                if isinstance(meta, dict):
                    grand = meta.get("grand_total") or meta.get("total")
            except (TypeError, ValueError, json.JSONDecodeError):
                grand = None
        if grand is not None:
            try:
                cost = int(grand)
            except (TypeError, ValueError):
                cost = None
            deal["tk_cost"] = cost
            deal["tk_cost_fmt"] = format_tk_cost(cost) if cost is not None else ""
        else:
            deal["tk_cost"] = None
            deal["tk_cost_fmt"] = ""
        return deal

    cost = calc_tk_cost(deal.get("area"))
    if cost is None:
        raw = deal.get("tk_cost")
        if raw is not None and str(raw).strip() not in {"", "None", "null"}:
            try:
                cost = int(raw)
            except (TypeError, ValueError):
                cost = None
    deal["tk_cost"] = cost
    deal["tk_cost_fmt"] = format_tk_cost(cost) if cost is not None else ""
    deal["price_per_m2"] = PRICE_PER_M2
    return deal
