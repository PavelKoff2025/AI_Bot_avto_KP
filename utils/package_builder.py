"""Сборка пакета документов для менеджера ОП (КП + опционально АР/ИР)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from utils.kp_generator import BOT_VARIANTS, KP_DIR, generate_single_kp
from utils.logging_setup import get_logger
from utils.report_service import create_ar_report

logger = get_logger("package")


def build_manager_package(
    dialog_text: str,
    variant_key: str,
    *,
    with_ar: bool = False,
    with_engineering: bool = False,
    include_fz: bool = False,
) -> dict[str, Any]:
    if variant_key not in BOT_VARIANTS:
        raise ValueError(f"Неизвестный вариант: {variant_key}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = KP_DIR / f"bot_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = BOT_VARIANTS[variant_key]
    logger.info(
        "Старт пакета: variant=%s ar=%s ir=%s fz=%s → %s",
        variant_key,
        with_ar,
        with_engineering,
        include_fz,
        out_dir.name,
    )

    files: list[Path] = []
    kp_path: Path
    eng_path: Path | None = None
    ar_path: Path | None = None

    try:
        logger.info("Генерация КП…")
        kp_files = generate_single_kp(
            variant_key,
            include_fz=include_fz,
            include_engineering=with_engineering,
            dialog_text=dialog_text,
            output_dir=out_dir,
        )
        files.extend(kp_files)
        kp_path = kp_files[0]
        eng_path = next(
            (p for p in kp_files if "IR_engineering" in p.name or "attachment_IR" in p.name),
            None,
        )
        logger.info("КП готов: %s", kp_path.name)
        if eng_path:
            logger.info("ИР-приложение: %s", eng_path.name)

        if with_ar:
            logger.info("Генерация АР (экстерьер + план)…")
            ar_generated = create_ar_report(dialog_text, with_image=True, with_floor_plan=True)
            ar_path = out_dir / ar_generated.name
            ar_path.write_bytes(ar_generated.read_bytes())
            html_src = ar_generated.with_suffix(".html")
            if html_src.exists():
                (out_dir / html_src.name).write_text(
                    html_src.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            files.append(ar_path)
            logger.info("АР готов: %s", ar_path.name)
    except Exception:
        logger.exception("Сбой при сборке пакета variant=%s", variant_key)
        raise

    logger.info("Пакет собран, файлов: %s", len(files))
    return {
        "variant_key": variant_key,
        "variant_title": meta["title"],
        "variant_description": meta["description"],
        "files": files,
        "kp": kp_path,
        "ar": ar_path,
        "engineering": eng_path,
        "output_dir": out_dir,
    }
