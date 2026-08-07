"""Оценка соответствия сделки эталонному протоколу (knowledge_base)."""

from __future__ import annotations

from typing import Any, Mapping

# Обязательные / рекомендуемые поля эталона → колонки сделки
ETALON_FIELDS: tuple[tuple[str, str], ...] = (
    ("client_phone", "Телефон"),
    ("client_email", "Email"),
    ("client_telegram", "Telegram"),
    ("plot", "Участок"),
    ("budget", "Бюджет"),
    ("area", "Площадь"),
    ("material", "Материал стен"),
    ("timeline", "Сроки старта"),
    ("funding_source", "Финансирование"),
)

EMPTY_MARKERS = {"", "—", "-", "None", "null", "none"}


def _filled(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text not in EMPTY_MARKERS


def etalon_match_score(deal: Mapping[str, Any] | Any) -> dict[str, Any]:
    """
    Считает % соответствия эталону по заполненным полям парсинга.
    Возвращает score (0–100), grade (high|mid|low) и список missing.
    """
    get = deal.get if isinstance(deal, Mapping) else lambda k, d=None: deal[k] if k in deal.keys() else d

    present: list[str] = []
    missing: list[str] = []
    for key, label in ETALON_FIELDS:
        try:
            value = get(key)
        except (KeyError, IndexError, TypeError):
            value = None
        if _filled(value):
            present.append(label)
        else:
            missing.append(label)

    total = len(ETALON_FIELDS)
    filled = len(present)
    score = int(round(100 * filled / total)) if total else 0

    if score >= 80:
        grade = "high"
    elif score >= 50:
        grade = "mid"
    else:
        grade = "low"

    return {
        "score": score,
        "grade": grade,
        "filled": filled,
        "total": total,
        "present": present,
        "missing": missing,
    }
