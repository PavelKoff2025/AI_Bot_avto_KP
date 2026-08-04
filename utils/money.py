"""Форматирование денежных сумм для КП / смет / PDF."""

from __future__ import annotations


def format_money(amount: int | float) -> str:
    """1234567 → '1 234 567'."""
    return f"{int(amount):,}".replace(",", " ")
