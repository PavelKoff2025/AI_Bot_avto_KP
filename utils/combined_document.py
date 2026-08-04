"""Сборка сводного PDF: все 3 КП + полная стоимость проекта."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from utils.config import DEFAULT_CLIENT_NAME, sanitize_client_name
from utils.engineering_generator import ENGINEERING_PACKAGE_TOTAL
from utils.kp_generator import BOT_VARIANTS, KP_DIR, build_variants, generate_single_kp
from utils.logging_setup import get_logger
from utils.money import format_money
from utils.pdf_generator import generate_pdf_report
from utils.report_service import create_ar_report

logger = get_logger("combined")

# Презентационный АР (визуализация + план) — сверх рабочего комплекта АР/КР в контуре КП
AR_DEVELOPMENT_PRICE = 180_000


def _contour_totals(include_fz: bool = False) -> dict[str, dict[str, Any]]:
    """Стоимость тёплого контура по вариантам (без пакета ИР и без презентационного АР)."""
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
    client_name: str = DEFAULT_CLIENT_NAME,
) -> dict[str, Any]:
    """Данные для титульной страницы со сводной сметой.

    Итог = тёплый контур + презентационный АР (если выбран) + ИР (если выбран).
    Флаги with_ar / with_engineering влияют и на цифры, и на состав PDF-приложений.
    Страницы КП ниже — только контур (без ИР в цене).
    """
    rows = []
    contours = _contour_totals(include_fz=include_fz)
    ar_price = AR_DEVELOPMENT_PRICE if with_ar else 0
    ir_price = ENGINEERING_PACKAGE_TOTAL if with_engineering else 0

    for key in ("basic", "optimal", "plus"):
        c = contours[key]
        total = c["contour"] + ar_price + ir_price
        rows.append({
            "key": key,
            "title": c["title"],
            "description": c["description"],
            "contour": c["contour"],
            "contour_fmt": format_money(c["contour"]),
            "ar": ar_price,
            "ar_fmt": format_money(ar_price) if ar_price else "—",
            "ir": ir_price,
            "ir_fmt": format_money(ir_price) if ir_price else "—",
            "total": total,
            "total_fmt": format_money(total),
        })

    parts_note = ["тёплый контур (уже включает рабочий комплект АР/КР)"]
    if with_ar:
        parts_note.append(
            f"презентационный АР ({format_money(AR_DEVELOPMENT_PRICE)} ₽)"
        )
    if with_engineering:
        parts_note.append(
            f"инженерные системы ({format_money(ENGINEERING_PACKAGE_TOTAL)} ₽)"
        )

    return {
        "client_name": sanitize_client_name(client_name),
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "with_ar": with_ar,
        "with_engineering": with_engineering,
        "ar_price": ar_price,
        "ar_price_fmt": format_money(AR_DEVELOPMENT_PRICE),
        "ir_price": ir_price,
        "ir_price_fmt": format_money(ENGINEERING_PACKAGE_TOTAL),
        "rows": rows,
        "accent": "#1a365d",
        "accent_soft": "#ebf0f7",
        "note": (
            "Стоимость в таблице = "
            + " + ".join(parts_note)
            + ". "
            "Страницы КП ниже показывают только тёплый контур. "
            "Цены ориентировочные; финал — после выезда и спецификации."
        ),
    }


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> Path:
    """Объединяет несколько PDF в один файл. Падает, если часть отсутствует."""
    if not pdf_paths:
        raise ValueError("merge_pdfs: список PDF пуст")

    missing = [str(p) for p in pdf_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Не удалось собрать сводный PDF — отсутствуют файлы:\n"
            + "\n".join(missing)
        )

    writer = PdfWriter()
    for path in pdf_paths:
        reader = PdfReader(str(path))
        if len(reader.pages) == 0:
            raise ValueError(f"PDF без страниц: {path}")
        for page in reader.pages:
            writer.add_page(page)

    if len(writer.pages) == 0:
        raise ValueError("merge_pdfs: итоговый PDF не содержит страниц")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)
    return output_path.resolve()


def _copy_into(src: Path, dest: Path) -> Path:
    dest.write_bytes(src.read_bytes())
    return dest.resolve()


def build_combined_document(
    dialog_text: str,
    *,
    with_ar: bool = False,
    with_engineering: bool = False,
    include_fz: bool = False,
    client_name: str = DEFAULT_CLIENT_NAME,
    output_dir: Path | None = None,
    existing_ar: Path | str | None = None,
    existing_engineering: Path | str | None = None,
) -> dict[str, Any]:
    """
    Собирает один PDF:
    1) сводная стоимость по 3 вариантам
    2–4) КП базовый / оптимальный / средний+
    5) АР (если выбран)
    6) ИР (если выбран)

    existing_ar / existing_engineering — переиспользовать уже собранные PDF
    из пакета менеджера (без повторной генерации изображений / ИИ).
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir) if output_dir else (KP_DIR / f"combined_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_client_name(client_name)
    logger.info(
        "Старт сводного PDF: ar=%s ir=%s fz=%s client=%s → %s",
        with_ar,
        with_engineering,
        include_fz,
        safe_name,
        out_dir.name,
    )

    try:
        logger.info("Сводная смета…")
        summary_ctx = build_cost_summary_context(
            with_ar=with_ar,
            with_engineering=with_engineering,
            include_fz=include_fz,
            client_name=safe_name,
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
                client_name=safe_name,
            )
            parts.append(kp_files[0])

        ar_path: Path | None = None
        if with_ar:
            reused = Path(existing_ar) if existing_ar else None
            if reused and reused.exists():
                logger.info("АР: переиспользуем %s", reused.name)
                ar_path = _copy_into(reused, out_dir / reused.name)
            else:
                logger.info("АР для сводного документа…")
                ar_generated = create_ar_report(
                    dialog_text, with_image=True, with_floor_plan=True
                )
                ar_path = _copy_into(ar_generated, out_dir / ar_generated.name)
            parts.append(ar_path)

        eng_path: Path | None = None
        if with_engineering:
            reused_eng = Path(existing_engineering) if existing_engineering else None
            if reused_eng and reused_eng.exists():
                logger.info("ИР: переиспользуем %s", reused_eng.name)
                eng_path = _copy_into(
                    reused_eng, out_dir / "attachment_IR_engineering.pdf"
                )
            else:
                from utils.engineering_generator import generate_engineering_project

                logger.info("ИР для сводного документа…")
                eng_path = generate_engineering_project(
                    dialog_text,
                    use_ai=bool(dialog_text),
                    output_path=out_dir / "attachment_IR_engineering.pdf",
                    client_name=safe_name,
                )
            parts.append(eng_path)

        combined_path = out_dir / f"KP_ALL_combined_{stamp}.pdf"
        logger.info("Merge PDF (%s частей)…", len(parts))
        merge_pdfs(parts, combined_path)
        logger.info(
            "Сводный PDF готов: %s (%s bytes)",
            combined_path.name,
            combined_path.stat().st_size,
        )
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
