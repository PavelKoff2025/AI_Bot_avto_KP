"""Генерация PDF-отчётов из HTML-шаблонов через Jinja2 и WeasyPrint."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
REPORTS_DIR = PROJECT_ROOT / "reports"
FONTS_DIR = PROJECT_ROOT / "fonts"

REPORT_TEMPLATES = {
    "client": "report_template.html",
    "design": "design_report_template.html",
    "ar": "ar_template.html",
    "engineering": "engineering_template.html",
}


def _font_url(filename: str) -> str:
    """Абсолютный file:// URL шрифта для WeasyPrint и браузера."""
    path = (FONTS_DIR / filename).resolve()
    return path.as_uri()


def _ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def _as_file_uri(path_or_url: Any) -> Any:
    if not path_or_url:
        return path_or_url
    value = str(path_or_url)
    if value.startswith(("data:", "http://", "https://", "file:")):
        return value
    return Path(value).resolve().as_uri()


def render_html(data: dict[str, Any], template_name: str = "report_template.html") -> str:
    """Подставляет данные в HTML-шаблон через Jinja2."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(template_name)

    context = {
        **data,
        "preview_image": _as_file_uri(data.get("preview_image")),
        "floor_plan_image": _as_file_uri(data.get("floor_plan_image")),
        "generated_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "font_regular": _font_url("DejaVuSans.ttf"),
        "font_bold": _font_url("DejaVuSans-Bold.ttf"),
    }
    return template.render(**context)


def generate_pdf_report(
    data: dict[str, Any],
    output_path: str | Path | None = None,
    template_name: str | None = None,
    report_type: str = "client",
    save_html: bool = True,
) -> Path:
    """
    Рендерит HTML-шаблон и конвертирует его в PDF.

    Args:
        data: структурированные данные отчёта от ИИ
        output_path: путь для сохранения PDF (опционально)
        template_name: имя Jinja2-шаблона (приоритетнее report_type)
        report_type: client | design
        save_html: также сохранить читаемый HTML рядом с PDF

    Returns:
        Path к созданному PDF-файлу
    """
    reports_dir = _ensure_reports_dir()

    if template_name is None:
        template_name = REPORT_TEMPLATES.get(report_type, REPORT_TEMPLATES["client"])

    if output_path is None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = {
            "design": "design",
            "ar": "ar",
            "engineering": "IR_engineering",
        }.get(report_type, "report")
        output_path = reports_dir / f"{prefix}_{stamp}.pdf"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    html_content = render_html(data, template_name=template_name)

    if save_html:
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html_content, encoding="utf-8")

    HTML(string=html_content, base_url=str(PROJECT_ROOT)).write_pdf(str(output_path))

    return output_path.resolve()
