"""КП этапа «Стройка»: тёплый контур по фиксированной цене ₽/м² («Дом Мастер»)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from pathlib import Path as _PathForEnv

from dotenv import load_dotenv

# .env из корня репозитория (на VPS процесс стартует из web_app/)
_REPO_ROOT = _PathForEnv(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_REPO_ROOT / "web_app" / ".env")

from utils.config import DEFAULT_CLIENT_NAME, sanitize_client_name
from utils.logging_setup import get_logger
from utils.money import format_money
from utils.pdf_generator import REPORTS_DIR, generate_pdf_report

logger = get_logger("stroika_kp")

# Компания и прайс этапа «Стройка»
COMPANY_NAME = "Дом Мастер"
COMPANY_REGION = "Московская область"
MIN_AREA_M2 = 100
STANDARD_AREA_MIN = 120
STANDARD_AREA_MAX = 200
PRICE_PER_M2 = 75_000  # тёплый контур из газобетона (коробка)
DEFAULT_MATERIAL = "газобетон (автоклавный D400–D500, стены 400 мм)"

KP_DIR = REPORTS_DIR / "kp" / "stroika"

WARM_CONTOUR_SCOPE = [
    "Фундамент: монолитная плита или ленточный, гидроизоляция, утепление отмостки",
    "Стены из автоклавного газобетона D400–D500, толщина 400 мм, армирование каждого 3-го ряда",
    "Кладка на специальный клей для газобетона",
    "Перекрытия: монолитное или сборное ж/б",
    "Кровля: стропильная система, обрешётка, металлочерепица/гибкая черепица, водосток",
    "Окна ПВХ с двухкамерным стеклопакетом",
    "Входная металлическая дверь",
    "Инженерные вводы: водоснабжение, канализация, электричество",
]

EXCLUDED_SCOPE = [
    "Внутренняя и наружная отделка",
    "Инженерные системы (отопление, вентиляция, кондиционирование)",
    "Ландшафтный дизайн и благоустройство территории",
    "Заборы и ворота",
    "Мебель и бытовая техника",
]

DEFAULT_TERMS = [
    "КП действительно 14 дней с даты формирования.",
    f"Цена указана за тёплый контур из газобетона из расчёта {format_money(PRICE_PER_M2)} ₽/м².",
    "Итоговая смета уточняется после выезда на участок и выбора проекта.",
    "Оплата поэтапная по актам готовности разделов работ.",
    "Срок возведения тёплого контура ориентировочно 3,5–5 месяцев после старта фундаментного цикла.",
]

DEFAULT_WARRANTY = [
    "5 лет — на все виды работ по договору подряда (стандарт «Дом-Мастер»)",
    "Гарантия фиксируется в договоре подряда",
]

WATERMARK_LABELS = {
    "draft": "ЧЕРНОВИК",
    "approved": "УТВЕРЖДЕНО",
}


def parse_area_m2(raw: Any) -> int | None:
    """Извлекает площадь в м² из строки сделки («150», «150 м2», «120-140 м²»)."""
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


def parse_budget_rub(raw: Any) -> int | None:
    """Грубая оценка бюджета в рублях из строки («7-8 млн», «11250000»)."""
    if raw is None:
        return None
    text = str(raw).strip().lower().replace("\xa0", " ").replace(",", ".")
    if not text:
        return None

    mln = re.search(
        r"(\d+(?:\.\d+)?)\s*[–\-—]?\s*(\d+(?:\.\d+)?)?\s*(млн|миллион)",
        text,
    )
    if mln:
        a = float(mln.group(1))
        b = float(mln.group(2)) if mln.group(2) else a
        return int(round(((a + b) / 2) * 1_000_000))

    digits = re.sub(r"[^\d]", "", text)
    if digits and len(digits) >= 5:
        return int(digits)
    return None


def calc_total(area_m2: int, price_per_m2: int = PRICE_PER_M2) -> int:
    return int(area_m2) * int(price_per_m2)


def _fallback_texts(area_m2: int, total: int, *, material: str | None = None) -> dict[str, str]:
    mat = (material or DEFAULT_MATERIAL).strip()
    total_fmt = format_money(total)
    return {
        "architecture": (
            f"Индивидуальный жилой дом площадью ориентировочно {area_m2} м² "
            f"в {COMPANY_REGION}. Основной конструктив: {mat}. "
            f"Планировочное решение уточняется на этапе проекта АР."
        ),
        "engineering": (
            "На этапе тёплого контура выполняются инженерные вводы "
            "(водоснабжение, канализация, электричество). "
            "Полные системы отопления, вентиляции и кондиционирования "
            "в данное КП не входят и рассчитываются отдельно."
        ),
        "specs": (
            f"Тёплый контур из газобетона для дома {area_m2} м²: фундамент, "
            f"стены D400–D500 толщиной 400 мм, перекрытия, кровля, окна, "
            f"входная дверь и инженерные вводы по стандарту «{COMPANY_NAME}»."
        ),
        "commercial": (
            f"Стоимость тёплого контура — {total_fmt} ₽ "
            f"({area_m2} м² × {format_money(PRICE_PER_M2)} ₽/м²). "
            f"Цена фиксированная по стандарту компании для {COMPANY_REGION}. "
            "КП действует 14 дней. Итоговая смета уточняется после выезда на участок. "
            "Оплата поэтапная по актам готовности работ."
        ),
        "intro": (
            f"Коммерческое предложение на строительство тёплого контура "
            f"дома из газобетона {area_m2} м². Расчёт по корпоративной ставке "
            f"{format_money(PRICE_PER_M2)} ₽/м²."
        ),
    }


def _looks_like_code_dump(value: Any) -> bool:
    """True, если модель вернула JSON/словарь вместо связного текста."""
    if isinstance(value, (dict, list)):
        return True
    text = str(value or "").strip()
    if not text:
        return False
    if text[0] in "{[" or text.endswith("}") or text.endswith("]"):
        return True
    compact = text.replace(" ", "")
    return any(
        token in compact
        for token in ("'price_", '"price_', "price_per_sqm", "total_price")
    )


def _as_plain_text(value: Any) -> str:
    if isinstance(value, dict):
        return ""
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _validate_ai_texts(data: Mapping[str, Any], *, area_m2: int, total: int) -> dict[str, str]:
    """Проверяет ответ модели; при сбое — fallback."""
    required = ("architecture", "engineering", "specs", "commercial", "intro")
    fallback = _fallback_texts(area_m2, total)
    result: dict[str, str] = {}

    for key in required:
        raw = data.get(key)
        if _looks_like_code_dump(raw):
            result[key] = fallback[key]
            continue
        value = _as_plain_text(raw)
        if len(value) < 40 or len(value) > 1200:
            value = fallback[key]
        # Не даём модели подменить корпоративную цену другой цифрой в ключевом блоке
        if key == "commercial":
            compact = value.replace(" ", "").replace("\xa0", "")
            if str(PRICE_PER_M2) not in compact:
                value = fallback[key]
            elif format_money(total) not in value and str(total) not in compact:
                value = fallback[key]
        result[key] = value
    return result


def generate_kp_texts_with_ai(
    *,
    area_m2: int,
    total: int,
    client_name: str,
    material: str | None = None,
    plot: str | None = None,
    budget: str | None = None,
    transcript: str | None = None,
) -> tuple[dict[str, str], bool]:
    """
    Генерирует текстовые блоки КП через OpenAI.
    Returns: (texts, ai_used).
    """
    fallback = _fallback_texts(area_m2, total, material=material)
    try:
        from utils.ai_processor import chat_json
        from utils.knowledge_base import (
            company_complectations_excerpt,
            company_standards_excerpt,
            complectations_short_excerpt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI/knowledge_base недоступны для КП: %s", exc)
        return fallback, False

    try:
        standards = company_standards_excerpt(4000)
    except FileNotFoundError as exc:
        logger.warning("%s", exc)
        standards = ""
    try:
        short = complectations_short_excerpt(1500)
    except FileNotFoundError as exc:
        logger.warning("%s", exc)
        short = ""
    try:
        complectations = company_complectations_excerpt(2500)
    except FileNotFoundError as exc:
        logger.warning("%s", exc)
        complectations = ""

    system = (
        f"Ты — коммерческий копирайтер компании «{COMPANY_NAME}», "
        f"специализация — частные дома из газобетона в {COMPANY_REGION} "
        f"от {MIN_AREA_M2} м² (стандарт {STANDARD_AREA_MIN}–{STANDARD_AREA_MAX} м²). "
        f"Этап КП — «Стройка»: тёплый контур из газобетона. "
        f"Корпоративная база цены строго {PRICE_PER_M2} ₽/м². "
        "Не меняй цену и итог в коммерческом блоке. "
        "Не упоминай «холодный контур» — такого уровня в оферте нет. "
        "Поля architecture, engineering, specs, commercial, intro — "
        "связные абзацы на русском, не JSON, не словари и не формулы в фигурных скобках. "
        "Можно кратко сослаться на White Box и «под ключ», "
        "но предмет этого КП — тёплый контур. "
        "Опирайся ТОЛЬКО на базу знаний ниже. Пиши по-русски, деловым стилем.\n\n"
        f"=== БЫСТРАЯ СПРАВКА: complectations_short.md ===\n{short}\n\n"
        f"=== БАЗА ЗНАНИЙ: company_standards.md ===\n{standards}\n\n"
        f"=== БАЗА ЗНАНИЙ: company_complectations.md ===\n{complectations}\n"
        "=== КОНЕЦ БАЗЫ ЗНАНИЙ ==="
    )
    user = (
        "Сформируй JSON со строковыми полями:\n"
        "architecture — архитектурное описание объекта (2–4 предложения),\n"
        "engineering — инженерные решения на этапе тёплого контура (2–4 предложения),\n"
        "specs — технические характеристики состава тёплого контура (2–5 предложений),\n"
        "commercial — коммерческие условия связным текстом (2–4 предложения) "
        f"с обязательным указанием цены {PRICE_PER_M2} ₽/м² и итога {format_money(total)} ₽; "
        "не возвращай объект/словарь,\n"
        "intro — краткое введение к КП (1–2 предложения).\n\n"
        f"Клиент: {client_name}\n"
        f"Площадь: {area_m2} м²\n"
        f"Итого: {format_money(total)} ₽\n"
        f"Материал: {material or 'не указан'}\n"
        f"Участок: {plot or 'не указан'}\n"
        f"Бюджет клиента: {budget or 'не указан'}\n"
    )
    if transcript:
        snippet = transcript.strip()[:2500]
        user += f"\nФрагмент протокола разговора:\n{snippet}\n"

    try:
        raw = chat_json(system, user)
        texts = _validate_ai_texts(raw, area_m2=area_m2, total=total)
        ai_used = any(texts[k] != fallback[k] for k in texts)
        return texts, ai_used
    except Exception as exc:  # noqa: BLE001
        logger.warning("Генерация текстов КП через AI не удалась: %s", exc)
        return fallback, False


def build_stroika_kp_context(
    deal: Mapping[str, Any],
    *,
    watermark: str = "draft",
    use_ai: bool = True,
    manager_name: str | None = None,
) -> dict[str, Any]:
    """Собирает контекст Jinja2 для одного КП тёплого контура."""
    area_m2 = parse_area_m2(deal.get("area"))
    if not area_m2:
        raise ValueError(
            "Для генерации КП нужна площадь дома (м²). "
            "Укажите площадь в карточке сделки."
        )
    if area_m2 < MIN_AREA_M2:
        raise ValueError(
            f"Минимальная площадь для «{COMPANY_NAME}» — {MIN_AREA_M2} м² "
            f"(сейчас {area_m2} м²)."
        )

    total = calc_total(area_m2)
    client_name = sanitize_client_name(deal.get("client_name"))
    material = (deal.get("material") or "").strip() or DEFAULT_MATERIAL
    # Стандарт компании v1.1 — основной материал только газобетон
    if "газобетон" not in material.lower() and "газо" not in material.lower():
        material = DEFAULT_MATERIAL
    plot = (deal.get("plot") or COMPANY_REGION).strip()
    budget = (deal.get("budget") or "").strip() or None
    transcript = (deal.get("transcript") or "").strip() or None

    if use_ai:
        texts, ai_used = generate_kp_texts_with_ai(
            area_m2=area_m2,
            total=total,
            client_name=client_name,
            material=material,
            plot=plot,
            budget=budget,
            transcript=transcript,
        )
    else:
        texts = _fallback_texts(area_m2, total, material=material)
        ai_used = False

    today = datetime.now()
    deal_id = deal.get("id")
    kp_number = f"КП-СК-{deal_id or 'X'}-{today.strftime('%y%m%d')}"
    wm_key = watermark if watermark in WATERMARK_LABELS else "draft"

    budget_note = None
    budget_rub = parse_budget_rub(budget)
    if budget_rub:
        delta = budget_rub - total
        if delta >= 0:
            budget_note = (
                f"Бюджет клиента (~{format_money(budget_rub)} ₽) покрывает "
                f"тёплый контур; запас ~{format_money(delta)} ₽."
            )
        else:
            budget_note = (
                f"Бюджет клиента (~{format_money(budget_rub)} ₽) ниже расчёта "
                f"на ~{format_money(abs(delta))} ₽ — обсудить площадь или этапность."
            )

    area_note = ""
    if STANDARD_AREA_MIN <= area_m2 <= STANDARD_AREA_MAX:
        area_note = f"Площадь в стандарте компании ({STANDARD_AREA_MIN}–{STANDARD_AREA_MAX} м²)."
    elif area_m2 > STANDARD_AREA_MAX:
        area_note = f"Площадь выше типового диапазона {STANDARD_AREA_MIN}–{STANDARD_AREA_MAX} м²."

    items = [
        {
            "name": "Тёплый контур из газобетона (коробка)",
            "detail": (
                f"{area_m2} м² × {format_money(PRICE_PER_M2)} ₽/м² — "
                "фундамент, стены D400–D500 400 мм, перекрытия, кровля, окна, "
                "входная дверь, инженерные вводы"
            ),
            "price": total,
            "price_fmt": format_money(total),
        }
    ]

    manager = manager_name or "Отдел продаж «Дом Мастер»"

    total_fmt = format_money(total)
    complectations_table = [
        {
            "name": "Тёплый контур",
            "price": f"{total_fmt} ₽",
        },
        {
            "name": "White Box",
            "price": "~ + 2 500 000 ₽",
        },
        {
            "name": "Под ключ",
            "price": "индивидуально",
        },
    ]
    complectations_formula = (
        f"Стоимость тёплого контура в этом КП: {area_m2} м² × "
        f"{format_money(PRICE_PER_M2)} ₽/м² = {total_fmt} ₽."
    )
    complectations_notes = [
        (
            "Тёплый контур — состав этого КП: фундамент, стены из газобетона, "
            "перекрытия, кровля, окна, входная дверь, инженерные вводы."
        ),
        (
            "White Box — черновая отделка и инженерия (отопление, электрика, водоснабжение). "
            "Ориентир ~ + 2 500 000 ₽; цена уточняется у менеджера вашего проекта "
            "после завершения работ по тёплому контуру."
        ),
        "Под ключ — полная готовая отделка, мебель, техника; расчёт индивидуальный.",
    ]

    return {
        "company_name": COMPANY_NAME,
        "kp_number": kp_number,
        "date": today.strftime("%d.%m.%Y"),
        "valid_until": (today + timedelta(days=14)).strftime("%d.%m.%Y"),
        "client_name": client_name,
        "object_desc": (
            f"Индивидуальный жилой дом из газобетона, тёплый контур, "
            f"ориентир {area_m2} м² ({material})"
        ),
        "area": f"{area_m2} м²",
        "area_m2": area_m2,
        "area_note": area_note,
        "plot": plot,
        "manager": manager,
        "title": f"Тёплый контур из газобетона — дом {area_m2} м²",
        "variant_label": "Этап «Стройка» · Газобетон · Тёплый контур",
        "accent": "#2c3e50",
        "accent_soft": "#e8f5e9",
        "intro": texts["intro"],
        "architecture": texts["architecture"],
        "engineering": texts["engineering"],
        "specs": texts["specs"],
        "commercial": texts["commercial"],
        "items": items,
        "price_per_m2": PRICE_PER_M2,
        "price_per_m2_fmt": format_money(PRICE_PER_M2),
        "total": total,
        "total_fmt": f"{format_money(total)} ₽",
        "total_label": "Итого: тёплый контур из газобетона",
        "total_note": (
            f"{area_m2} м² × {format_money(PRICE_PER_M2)} ₽/м² (газобетон). "
            f"{area_note} Цена для {COMPANY_REGION}."
        ).strip(),
        "budget_note": budget_note,
        "complectations_table": complectations_table,
        "complectations_formula": complectations_formula,
        "complectations_notes": complectations_notes,
        "complectations_base_area": area_m2,
        "included": list(WARM_CONTOUR_SCOPE),
        "excluded": list(EXCLUDED_SCOPE),
        "terms": list(DEFAULT_TERMS),
        "warranty": list(DEFAULT_WARRANTY),
        "next_step": (
            "Подтвердите площадь и участок — организуем выезд инженера "
            "и подготовим договор подряда на тёплый контур из газобетона."
        ),
        "watermark": wm_key,
        "watermark_label": WATERMARK_LABELS[wm_key],
        "ai_used": ai_used,
        "deal_id": deal_id,
        "include_fz": False,
        "include_engineering": False,
    }


def generate_stroika_kp_pdf(
    deal: Mapping[str, Any],
    *,
    watermark: str = "draft",
    use_ai: bool = True,
    manager_name: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Генерирует одно КП (HTML+PDF) для сделки этапа «Стройка».

    Returns:
        dict с путями и расчётными полями для сохранения в deals.kp_options.
    """
    context = build_stroika_kp_context(
        deal,
        watermark=watermark,
        use_ai=use_ai,
        manager_name=manager_name,
    )

    deal_id = deal.get("id") or "x"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir) if output_dir else KP_DIR / f"deal_{deal_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"KP_stroika_deal{deal_id}_{stamp}.pdf"

    path = generate_pdf_report(
        context,
        output_path=pdf_path,
        template_name="kp_stroika_template.html",
        save_html=True,
    )

    meta = {
        "pdf_path": str(path),
        "html_path": str(path.with_suffix(".html")),
        "area_m2": context["area_m2"],
        "price_per_m2": context["price_per_m2"],
        "total": context["total"],
        "total_fmt": context["total_fmt"],
        "watermark": context["watermark"],
        "kp_number": context["kp_number"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ai_used": context["ai_used"],
        "client_name": context["client_name"],
    }
    path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta
