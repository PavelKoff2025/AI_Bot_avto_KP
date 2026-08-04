"""Пайплайны генерации отчётов."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from utils.ai_processor import (
    process_ar_with_ai,
    process_design_order_with_ai,
    process_dialog_with_ai,
)
from utils.config import REPORT_TYPE_ALIASES
from utils.engineering_generator import generate_engineering_project
from utils.image_generator import generate_design_image
from utils.logging_setup import get_logger
from utils.pdf_generator import REPORTS_DIR, generate_pdf_report

logger = get_logger("report")

SUPPORTED_REPORT_TYPES = frozenset(
    {v for v in REPORT_TYPE_ALIASES.values()}
)


def create_design_report(dialog_text: str) -> Path:
    logger.info("Анализ заказа дизайна через ИИ…")
    data = process_design_order_with_ai(dialog_text)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    images_dir = REPORTS_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    image_path = images_dir / f"design_preview_{stamp}.png"

    logger.info("Генерация примера дизайна (изображение)…")
    generate_design_image(data["image_prompt"], image_path)
    data["preview_image"] = str(image_path)

    logger.info("Генерация PDF…")
    return generate_pdf_report(data, report_type="design")


def create_client_report(dialog_text: str) -> Path:
    logger.info("Анализ диалога через ИИ…")
    data = process_dialog_with_ai(dialog_text)
    logger.info("Генерация PDF…")
    return generate_pdf_report(data, report_type="client")


def create_ar_report(
    dialog_text: str,
    with_image: bool = True,
    with_floor_plan: bool = True,
) -> Path:
    logger.info("Формирование архитектурного решения (АР) через ИИ…")
    data = process_ar_with_ai(dialog_text)

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    images_dir = REPORTS_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    if with_image:
        image_path = images_dir / f"ar_preview_{stamp}.png"
        logger.info("Генерация визуализации экстерьера…")
        generate_design_image(data["image_prompt"], image_path)
        data["preview_image"] = str(image_path)

    if with_floor_plan:
        plan_path = images_dir / f"ar_floorplan_{stamp}.png"
        logger.info("Генерация плана дома (расстановка помещений)…")
        generate_design_image(data["floor_plan_prompt"], plan_path)
        data["floor_plan_image"] = str(plan_path)

    logger.info("Генерация PDF (АР)…")
    return generate_pdf_report(data, report_type="ar", template_name="ar_template.html")


def create_engineering_report(dialog_text: str | None = None) -> Path:
    logger.info("Формирование проекта инженерных решений (ИР)…")
    return generate_engineering_project(dialog_text, use_ai=bool(dialog_text))


def create_report(dialog_text: str, report_type: str) -> Path:
    if report_type not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            f"Неизвестный тип отчёта: {report_type!r}. "
            f"Допустимо: {', '.join(sorted(SUPPORTED_REPORT_TYPES))}"
        )
    if report_type == "design":
        return create_design_report(dialog_text)
    if report_type == "ar":
        return create_ar_report(dialog_text)
    if report_type == "engineering":
        return create_engineering_report(dialog_text)
    return create_client_report(dialog_text)
