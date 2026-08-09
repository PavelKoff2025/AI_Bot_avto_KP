"""Загрузка документов knowledge_base для RAG / промптов КП."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge_base"

# Канонические документы для этапа «Стройка» / КП
COMPANY_STANDARDS_PATH = KNOWLEDGE_DIR / "company_standards.md"
ETALON_PROTOCOL_PATH = KNOWLEDGE_DIR / "etalon_protocol.md"


@lru_cache(maxsize=8)
def load_knowledge_doc(name: str) -> str:
    """Читает markdown из knowledge_base по имени файла."""
    path = KNOWLEDGE_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Документ базы знаний не найден: {path}")
    return path.read_text(encoding="utf-8")


def load_company_standards() -> str:
    """Стандарты «Дом-Мастер» (цена м², газобетон, состав тёплого контура)."""
    return load_knowledge_doc("company_standards.md")


def company_standards_excerpt(max_chars: int = 6000) -> str:
    """Укороченный фрагмент стандартов для системного промпта."""
    text = load_company_standards().strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n\n[…обрезано…]"


def list_knowledge_docs() -> list[str]:
    if not KNOWLEDGE_DIR.is_dir():
        return []
    return sorted(p.name for p in KNOWLEDGE_DIR.glob("*.md"))
