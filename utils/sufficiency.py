"""Проверка достаточности транскрибации для формирования КП (эталон — sample_dialog)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from utils.ai_processor import chat_json
from utils.config import DEFAULT_CLIENT_NAME, sanitize_client_name
from utils.logging_setup import get_logger

logger = get_logger("sufficiency")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ETALON_PATH = PROJECT_ROOT / "sample_dialog.txt"

SUFFICIENCY_PROMPT = """
Ты — методист отдела продаж компании по строительству домов («Дом-Мастер»).
Тебе дан ЭТАЛОН полноценной транскрибации звонка (по нему можно собрать КП)
и НОВАЯ транскрибация от менеджера.

Сравни новую транскрибацию с эталоном по минимуму данных для коммерческого предложения
на тёплый контур / строительство ИЖД.

Критерии достаточности (все желательны; критичные отметь отдельно):
1. Имя / контакт заказчика (хотя бы имя)
2. Тип/стиль дома (этажность, современный и т.п.)
3. Площадь (м²) или состав семьи → оценка площади
4. Участок: есть ли, регион/локация
5. Бюджет (ориентир)
6. Сроки старта
7. Объём работ: что делает компания / что заказчик (коробка, инженерка, отделка)
8. Коммуникации на участке (электричество, газ) — желательно
9. Материал стен или готовность рассмотреть варианты — желательно

Верни ТОЛЬКО JSON:
{
  "can_form_kp": true/false,
  "score": 0-100,
  "client_name": "имя заказчика из транскрибации или пустая строка",
  "summary": "краткий вывод для менеджера на русском",
  "missing_critical": ["чего не хватает критично — конкретные формулировки"],
  "missing_optional": ["что желательно уточнить"],
  "present": ["что уже есть в транскрибации"],
  "questions_for_client": ["готовые вопросы менеджеру, что доспросить у клиента"]
}

can_form_kp = true, только если хватает минимум: тип дома/стиль, площадь или семья,
бюджет или явный запрос на расчёт, участок (есть/нет + локация хотя бы грубо),
и понятен объём (хотя бы коробка/тёплый контур vs под ключ).
Имя желательно, но отсутствие имени само по себе не блокирует КП (можно «Заказчик»).
""".strip()


def load_etalon() -> str:
    if ETALON_PATH.exists():
        return ETALON_PATH.read_text(encoding="utf-8")
    logger.warning("Эталон не найден: %s — проверка достаточности ослаблена", ETALON_PATH)
    return ""


def check_transcription_sufficiency(transcription: str) -> dict[str, Any]:
    """LLM-проверка: можно ли формировать КП по сравнению с эталоном."""
    if not transcription or not transcription.strip():
        return {
            "can_form_kp": False,
            "score": 0,
            "client_name": DEFAULT_CLIENT_NAME,
            "summary": "Транскрибация пуста.",
            "missing_critical": ["Пришлите текст или .txt файл с диалогом"],
            "missing_optional": [],
            "present": [],
            "questions_for_client": [],
        }

    etalon = load_etalon()
    data = chat_json(
        SUFFICIENCY_PROMPT,
        (
            "=== ЭТАЛОН ===\n"
            f"{etalon.strip()}\n\n"
            "=== НОВАЯ ТРАНСКРИБАЦИЯ ===\n"
            f"{transcription.strip()}\n"
        ),
    )

    def _list(key: str) -> list[str]:
        value = data.get(key, [])
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if value:
            return [str(value).strip()]
        return []

    can = data.get("can_form_kp", False)
    if isinstance(can, str):
        can = can.strip().lower() in {"true", "1", "yes", "да"}

    score = data.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0

    return {
        "can_form_kp": bool(can),
        "score": max(0, min(100, score)),
        "client_name": sanitize_client_name(data.get("client_name")),
        "summary": str(data.get("summary") or "").strip() or "Нет резюме",
        "missing_critical": _list("missing_critical"),
        "missing_optional": _list("missing_optional"),
        "present": _list("present"),
        "questions_for_client": _list("questions_for_client"),
    }


def _esc(value: Any) -> str:
    """Экранирование LLM/пользовательского текста для Telegram HTML."""
    return html.escape(str(value), quote=False)


def format_sufficiency_message(result: dict[str, Any]) -> str:
    """Текст ответа менеджеру в Telegram (parse_mode=HTML)."""
    lines = [
        f"Оценка готовности к КП: <b>{_esc(result['score'])}/100</b>",
        _esc(result["summary"]),
        "",
    ]
    if result["present"]:
        lines.append("<b>Уже есть:</b>")
        lines.extend(f"• {_esc(x)}" for x in result["present"])
        lines.append("")

    if result["can_form_kp"]:
        lines.append("✅ Информации <b>достаточно</b>, можно формировать КП.")
        if result["missing_optional"]:
            lines.append("")
            lines.append("<i>Желательно уточнить (не блокирует КП):</i>")
            lines.extend(f"• {_esc(x)}" for x in result["missing_optional"])
    else:
        lines.append("❌ Пока <b>недостаточно</b> данных для КП.")
        if result["missing_critical"]:
            lines.append("")
            lines.append("<b>Нужно добавить:</b>")
            lines.extend(f"• {_esc(x)}" for x in result["missing_critical"])
        if result["questions_for_client"]:
            lines.append("")
            lines.append("<b>Вопросы клиенту:</b>")
            lines.extend(f"• {_esc(x)}" for x in result["questions_for_client"])
        lines.append("")
        lines.append(
            "Дополните транскрибацию и пришлите новый .txt "
            "(или вставьте текст сообщением)."
        )
    return "\n".join(lines)
