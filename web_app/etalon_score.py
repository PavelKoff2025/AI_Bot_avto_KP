"""Оценка соответствия сделки эталонному протоколу (knowledge_base)."""

from __future__ import annotations

import os
from typing import Any, Mapping

# Порог заполнения для генерации КП (по умолчанию 80%)
KP_THRESHOLD = int(os.getenv("ETALON_KP_THRESHOLD", "80"))

# Обязательные / рекомендуемые поля эталона → колонки сделки
# Бюджет клиента — необязателен; ориентир цены — поле «Стоимость ТК» (считается из площади).
ETALON_FIELDS: tuple[tuple[str, str], ...] = (
    ("client_phone", "Телефон"),
    ("client_email", "Email"),
    ("client_telegram", "Telegram"),
    ("plot", "Участок"),
    ("area", "Площадь"),
    ("material", "Материал стен"),
    ("timeline", "Сроки старта"),
    ("funding_source", "Финансирование"),
)

# Подсказки менеджеру: какие вопросы задать клиенту по недостающему полю
FIELD_QUESTIONS: dict[str, str] = {
    "client_phone": "Подскажите, пожалуйста, удобный номер телефона для связи?",
    "client_email": "На какой email отправить коммерческое предложение?",
    "client_telegram": "Есть ли у вас Telegram для оперативной связи?",
    "plot": "Участок уже есть? Какой размер (сотки) и где расположен?",
    "area": "Какую площадь дома планируете (м²)?",
    "material": "Подтверждаем стены из газобетона (стандарт «Дом-Мастер»)?",
    "timeline": "Когда планируете стартовать строительство (месяц/сезон и год)?",
    "funding_source": "Как планируете финансировать: свои средства, ипотека, маткапитал?",
}

EMPTY_MARKERS = {"", "—", "-", "None", "null", "none"}


def _filled(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text not in EMPTY_MARKERS


def etalon_match_score(deal: Mapping[str, Any] | Any) -> dict[str, Any]:
    """
    Считает % соответствия эталону по заполненным полям парсинга.
    Возвращает score (0–100), grade (high|mid|low), missing и questions.
    """
    get = deal.get if isinstance(deal, Mapping) else lambda k, d=None: deal[k] if k in deal.keys() else d

    present: list[str] = []
    missing: list[str] = []
    missing_keys: list[str] = []
    questions: list[str] = []

    for key, label in ETALON_FIELDS:
        try:
            value = get(key)
        except (KeyError, IndexError, TypeError):
            value = None
        if _filled(value):
            present.append(label)
        else:
            missing.append(label)
            missing_keys.append(key)
            question = FIELD_QUESTIONS.get(key)
            if question:
                questions.append(question)

    total = len(ETALON_FIELDS)
    filled = len(present)
    score = int(round(100 * filled / total)) if total else 0

    if score >= KP_THRESHOLD:
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
        "missing_keys": missing_keys,
        "questions": questions,
        "can_generate_kp": score >= KP_THRESHOLD,
        "is_complete": score >= 100,
        "threshold": KP_THRESHOLD,
    }


def can_generate_kp(deal_or_score: Mapping[str, Any] | int | float) -> bool:
    """True, если заполнение ≥ порога генерации КП."""
    if isinstance(deal_or_score, (int, float)):
        return int(deal_or_score) >= KP_THRESHOLD
    match = etalon_match_score(deal_or_score)
    return bool(match["can_generate_kp"])
