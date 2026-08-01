"""Единая настройка логирования проекта."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOGS_DIR / "bot.log"

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Консоль + файл logs/bot.log.
    Формат: время | уровень | модуль | сообщение
    """
    global _CONFIGURED
    logger = logging.getLogger("dom_master")

    if _CONFIGURED:
        return logger

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Подключаем дочерние логгеры utils.* к тому же дереву
    for name in (
        "dom_master.bot",
        "dom_master.package",
        "dom_master.combined",
        "dom_master.sufficiency",
        "dom_master.report",
    ):
        child = logging.getLogger(name)
        child.setLevel(level)
        child.propagate = True

    _CONFIGURED = True
    logger.info("Логирование включено → %s", LOG_FILE)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Логгер вида dom_master.<name>."""
    if not name.startswith("dom_master"):
        name = f"dom_master.{name}"
    return logging.getLogger(name)
