"""Пакет утилит генерации КП / отчётов / АР / ИР."""

from .ai_processor import (
    chat_json,
    get_openai_client,
    process_ar_with_ai,
    process_design_order_with_ai,
    process_dialog_with_ai,
)
from .image_generator import generate_design_image
from .kp_generator import generate_all_kp, generate_kp_from_json
from .money import format_money
from .pdf_generator import generate_pdf_report
from .report_service import create_report

__all__ = [
    "chat_json",
    "create_report",
    "format_money",
    "generate_all_kp",
    "generate_design_image",
    "generate_kp_from_json",
    "generate_pdf_report",
    "get_openai_client",
    "process_ar_with_ai",
    "process_design_order_with_ai",
    "process_dialog_with_ai",
]
