"""Сборка сводного PDF: все 3 КП + полная стоимость проекта."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from utils.engineering_generator import ENGINEERING_PACKAGE_TOTAL
from utils.kp_generator import BOT_VARIANTS, KP_DIR, _fmt, build_variants, generate_single_kp
from utils.logging_setup import get_logger
from utils.pdf_generator import generate_pdf_report
from utils.report_service import create_ar_report

logger = get_logger("combined")

# Презентационный АР (визуализация + план помещений) — сверх рабочего АР/КР в КП
AR_DEVELOPMENT_PRICE = 180_000


def _contour_totals(include_fz: bool = False) -> dict[str, dict[str, Any]]:
    """Стоимость тёплого контура по вариантам (без пакета ИР)."""
    variants = build_variants(include_fz=include_fz, include_engineering=False)
    result = {}
    for key, meta in BOT_VARIANTS.items():
        v = variants[meta["index"]]
        result[key] = {
            "title": meta["title"],
            "description": meta["description"],
            "contour": int(v["total"]),
            "contour_fmt": v["total_fmt"],
        }
    return result


def build_cost_summary_context(
    *,
    with_ar: bool,
    with_engineering: bool,
    include_fz: bool = False,
    client_name: str = "Заказчик",
) -> dict[str, Any]:
    """Данные для титульной страницы со сводной сметой.

    В таблице всегда считается полная стоимость:
    тёплый контур + АР + ИР (чтобы менеджер видел итог проекта).
    Флаги with_ar / with_engineering влияют на состав PDF-приложений.
    """
    rows = []
    contours = _contour_totals(include_fz=include_fz)
    ar_price = AR_DEVELOPMENT_PRICE
    ir_price = ENGINEERING_PACKAGE_TOTAL

    for key in ("basic", "optimal", "plus"):
        c = contours[key]
        total = c["contour"] + ar_price + ir_price
        rows.append({
            "key": key,
            "title": c["title"],
            "description": c["description"],
            "contour": c["contour"],
            "contour_fmt": _fmt(c["contour"]),
            "ar": ar_price,
            "ar_fmt": _fmt(ar_price),
            "ir": ir_price,
            "ir_fmt": _fmt(ir_price),
            "total": total,
            "total_fmt": _fmt(total),
        })

    return {
        "client_name": client_name,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "with_ar": with_ar,
        "with_engineering": with_engineering,
        "ar_price": ar_price,
        "ar_price_fmt": _fmt(AR_DEVELOPMENT_PRICE),
        "ir_price": ir_price,
        "ir_price_fmt": _fmt(ENGINEERING_PACKAGE_TOTAL),
        "rows": rows,
        "accent": "#1a365d",
        "accent_soft": "#ebf0f7",
        "note": (
            "Полная стоимость проекта = строительство тёплого контура "
            f"+ разработка АР ({_fmt(AR_DEVELOPMENT_PRICE)} ₽) "
            f"+ инженерные системы ({_fmt(ENGINEERING_PACKAGE_TOTAL)} ₽). "
            "Ниже — сравнение всех трёх вариантов КП. "
            "Цены ориентировочные; финал — после выезда и спецификации."
        ),
    }


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> Path:
    """Объединяет несколько PDF в один файл."""
    writer = PdfWriter()
    for path in pdf_paths:
        if not path.exists():
            continue
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)
    return output_path.resolve()


def build_combined_document(
    dialog_text: str,
    *,
    with_ar: bool = False,
    with_engineering: bool = False,
    include_fz: bool = False,
    client_name: str = "Заказчик",
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Собирает один PDF:
    1) сводная стоимость по 3 вариантам
    2) КП «Базовый»
    3) КП «Средний (оптимальный)»
    4) КП «Средний +»
    5) АР (если выбран)
    6) ИР (если выбран)
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir) if output_dir else (KP_DIR / f"combined_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Старт сводного PDF: ar=%s ir=%s fz=%s → %s",
        with_ar,
        with_engineering,
        include_fz,
        out_dir.name,
    )

    try:
        logger.info("Сводная смета…")
        summary_ctx = build_cost_summary_context(
            with_ar=with_ar,
            with_engineering=with_engineering,
            include_fz=include_fz,
            client_name=client_name,
        )
        summary_pdf = generate_pdf_report(
            summary_ctx,
            output_path=out_dir / "00_summary_costs.pdf",
            template_name="combined_summary_template.html",
            save_html=True,
        )

        parts: list[Path] = [summary_pdf]

        for key in ("basic", "optimal", "plus"):
            logger.info("КП вариант %s…", key)
            kp_files = generate_single_kp(
                key,
                include_fz=include_fz,
                include_engineering=False,
                dialog_text=dialog_text,
                output_dir=out_dir,
            )
            parts.append(kp_files[0])

        ar_path: Path | None = None
        if with_ar:
            logger.info("АР для сводного документа…")
            ar_generated = create_ar_report(dialog_text, with_image=True, with_floor_plan=True)
            ar_path = out_dir / ar_generated.name
            ar_path.write_bytes(ar_generated.read_bytes())
            parts.append(ar_path)

        eng_path: Path | None = None
        if with_engineering:
            from utils.engineering_generator import generate_engineering_project

            logger.info("ИР для сводного документа…")
            eng_path = generate_engineering_project(
                dialog_text,
                use_ai=bool(dialog_text),
                output_path=out_dir / "attachment_IR_engineering.pdf",
            )
            parts.append(eng_path)

        combined_path = out_dir / f"KP_ALL_combined_{stamp}.pdf"
        logger.info("Merge PDF (%s частей)…", len(parts))
        merge_pdfs(parts, combined_path)
        logger.info("Сводный PDF готов: %s (%s bytes)", combined_path.name, combined_path.stat().st_size)
    except Exception:
        logger.exception("Сбой сборки сводного PDF")
        raise

    return {
        "combined_pdf": combined_path,
        "parts": parts,
        "summary": summary_ctx,
        "ar": ar_path,
        "engineering": eng_path,
        "output_dir": out_dir,
    }
