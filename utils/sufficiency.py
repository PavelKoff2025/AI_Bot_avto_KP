"""Проверка достаточности транскрибации для КП (эталон — knowledge_base/etalon_protocol.md)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from utils.ai_processor import chat_json
from utils.config import DEFAULT_CLIENT_NAME, sanitize_client_name
from utils.logging_setup import get_logger

logger = get_logger("sufficiency")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ETALON_PATH = PROJECT_ROOT / "knowledge_base" / "etalon_protocol.md"
ETALON_FALLBACK_PATH = PROJECT_ROOT / "sample_dialog.txt"

SUFFICIENCY_PROMPT = """
Ты — методист отдела продаж компании по строительству домов («Дом-Мастер»).
Тебе дан ЭТАЛОННЫЙ ПРОТОКОЛ из базы знаний RAG (обязательные поля + пример)
и НОВАЯ транскрибация / протокол разговора от менеджера.

Сравни новую транскрибацию с эталоном: достаточно ли данных для формирования КП.

Обязательные поля эталона (критичные для can_form_kp):
1. Телефон (+7…) — ОБЯЗАТЕЛЬНО
2. Email — ОБЯЗАТЕЛЬНО (для отправки КП)
3. Участок — ОБЯЗАТЕЛЬНО (наличие, размер ≥ 6 соток, расположение)
4. Бюджет — ОБЯЗАТЕЛЬНО (сумма в рублях)
5. Площадь дома — ОБЯЗАТЕЛЬНО (м²)
6. Материал стен — ОБЯЗАТЕЛЬНО (газобетон/кирпич/брус/керамоблок)
7. Сроки старта — ОБЯЗАТЕЛЬНО (месяц/сезон, год)
8. Источник финансирования — ОБЯЗАТЕЛЬНО (свои/ипотека/маткапитал)

Рекомендуемые / апсейл (не блокируют КП, но отмечай в missing_optional):
9. Telegram — РЕКОМЕНДУЕТСЯ
10. Проектная документация АР/КР/ИР
11. Инженерные системы (вода/канализация/отопление/электрика)
12. Внутренняя отделка (черновая/чистовая)
Также желательны: имя клиента, тип/стиль/этажность дома.

Верни ТОЛЬКО JSON:
{
  "can_form_kp": true/false,
  "score": 0-100,
  "client_name": "имя заказчика из транскрибации или пустая строка",
  "summary": "краткий вывод для менеджера на русском",
  "missing_critical": ["чего не хватает критично — конкретные формулировки"],
  "missing_optional": ["что желательно уточнить (апсейл/рекомендуемое)"],
  "present": ["что уже есть в транскрибации"],
  "questions_for_client": ["готовые вопросы менеджеру, что доспросить у клиента"]
}

can_form_kp = true только если заполнены ВСЕ критичные поля эталона (1–8)
либо явно эквивалентная информация (например email+телефон в шапке протокола,
площадь как диапазон 120–140 м², участок «10 соток, Дмитровское шоссе»).
Имя желательно, но отсутствие имени само по себе не блокирует КП (можно «Заказчик»).
Оцени score относительно полноты эталона (0–100).
""".strip()


def load_etalon() -> str:
    if ETALON_PATH.exists():
        return ETALON_PATH.read_text(encoding="utf-8")
    if ETALON_FALLBACK_PATH.exists():
        logger.warning(
            "Эталон RAG не найден (%s), fallback: %s",
            ETALON_PATH,
            ETALON_FALLBACK_PATH,
        )
        return ETALON_FALLBACK_PATH.read_text(encoding="utf-8")
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
            "=== ЭТАЛОН (knowledge_base/etalon_protocol.md) ===\n"
            f"{etalon.strip()}\n\n"
            "=== НОВАЯ ТРАНСКРИБАЦИЯ / ПРОТОКОЛ ===\n"
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
