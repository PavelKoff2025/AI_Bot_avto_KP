#!/usr/bin/env python3
"""
AI Client Report Generator

Считывает транскрибацию диалога, анализирует её через OpenAI
и сохраняет PDF-отчёт в папку reports/.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from utils.config import REPORT_TYPE_ALIASES, resolve_report_type
from utils.logging_setup import get_logger, setup_logging
from utils.report_service import create_report

setup_logging()
logger = get_logger("cli")


def open_report(path: Path) -> None:
    """Открывает отчёт в системном просмотрщике (не в текстовом редакторе)."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=False)
        elif sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
    except OSError:
        pass


def read_dialog(source: str | None) -> str:
    """Читает диалог из файла или со стандартного ввода."""
    if source:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {path}")
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            raise ValueError(f"Файл пуст: {path}")
        return text

    print("Вставьте транскрибацию диалога. Завершите ввод пустой строкой:")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)

    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("Транскрибация не введена")
    return text


def choose_report_type(explicit: str | None) -> str:
    """Выбор типа отчёта: из аргумента или интерактивно."""
    if explicit:
        return resolve_report_type(explicit)

    print("Какой документ сгенерировать?")
    print("  1) Клиентский отчёт")
    print("  2) Отчёт по дизайну сайта")
    print("  3) АР — архитектурное решение дома")
    print("  4) ИР — проект инженерных решений (+ смета)")
    choice = input("Введите 1–4: ").strip().lower()
    return resolve_report_type(choice)


def _ask_yes(prompt: str, default: bool = False) -> bool:
    if not sys.stdin.isatty():
        return default
    hint = "Y/n" if default else "y/N"
    ans = input(f"{prompt} [{hint}]: ").strip().lower()
    if not ans:
        return default
    return ans in {"y", "yes", "д", "да"}


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AI Client Report Generator — PDF-отчёты, АР, ИР и КП",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Путь к текстовому файлу с транскрибацией",
    )
    parser.add_argument(
        "--type",
        "-t",
        dest="report_type",
        choices=sorted(REPORT_TYPE_ALIASES.keys()),
        help="Тип документа",
    )
    parser.add_argument("--serve", action="store_true", help="Запустить Flask API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument(
        "--kp",
        action="store_true",
        help="Сформировать 3 КП (тёплый контур)",
    )
    parser.add_argument(
        "--with-fz",
        action="store_true",
        help="С --kp: добавить ФЗ (фасад)",
    )
    parser.add_argument(
        "--with-engineering",
        action="store_true",
        help="С --kp: приложить проект ИР и включить пакет инженерки в смету",
    )
    parser.add_argument(
        "--ar",
        action="store_true",
        help="Сгенерировать АР по файлу диалога",
    )
    parser.add_argument(
        "--engineering",
        action="store_true",
        help="Сгенерировать проект инженерных решений (ИР) по файлу диалога",
    )
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    if args.serve:
        from flask_app import create_app

        app = create_app()
        logger.info("Flask API: http://%s:%s", args.host, args.port)
        print(f"Flask API: http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=False)
        return 0

    if args.kp:
        from utils.kp_generator import generate_all_kp

        include_fz = args.with_fz or _ask_yes("Добавить в КП фасадную отделку (ФЗ)?")
        include_eng = args.with_engineering or _ask_yes(
            "Приложить проект инженерных решений (ИР) к КП?"
        )
        dialog_text = None
        if include_eng:
            if not args.file:
                print(
                    "Для ИР с AI-брифом укажите файл транскрибации "
                    "(иначе будет шаблон).",
                    file=sys.stderr,
                )
            else:
                try:
                    dialog_text = read_dialog(args.file)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Не удалось прочитать диалог для ИР")
                    print(
                        f"Ошибка чтения файла для ИР: {exc}\n"
                        "Продолжаю со шаблонным брифом.",
                        file=sys.stderr,
                    )
                    dialog_text = None

        try:
            paths = generate_all_kp(
                include_fz=include_fz,
                include_engineering=include_eng,
                dialog_text=dialog_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка генерации КП")
            print(f"Ошибка: {exc}", file=sys.stderr)
            return 1

        tags = []
        if include_fz:
            tags.append("ФЗ")
        if include_eng:
            tags.append("ИР")
        label = " + ".join(tags) if tags else "базовые"
        print(f"Сформированы коммерческие предложения ({label}):")
        for path in paths:
            try:
                display = path.relative_to(Path.cwd())
            except ValueError:
                display = path
            print(f"  • {display}")
            if path.suffix == ".pdf" and path.with_suffix(".html").exists():
                print(f"    HTML: {display.with_suffix('.html')}")
        if not args.no_open:
            for path in paths:
                if path.suffix == ".pdf":
                    open_report(path)
        return 0

    try:
        if args.ar:
            report_type = "ar"
        elif args.engineering:
            report_type = "engineering"
        else:
            report_type = choose_report_type(args.report_type)
        dialog_text = read_dialog(args.file)
        pdf_path = create_report(dialog_text, report_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка генерации отчёта")
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    try:
        display_path = pdf_path.relative_to(Path.cwd())
    except ValueError:
        display_path = pdf_path

    print(f"Отчёт успешно создан: {display_path}")
    html_path = pdf_path.with_suffix(".html")
    if html_path.exists():
        try:
            print(f"HTML-версия: {html_path.relative_to(Path.cwd())}")
        except ValueError:
            print(f"HTML-версия: {html_path}")

    if not args.no_open:
        open_report(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
