"""Общие helpers для deals.db."""

from __future__ import annotations

import sqlite3

DEAL_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("budget", "TEXT"),
    ("area", "TEXT"),
    ("material", "TEXT"),
    ("timeline", "TEXT"),
    ("funding_source", "TEXT"),
    ("plot", "TEXT"),
)


def ensure_deal_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(deals)").fetchall()}
    for name, col_type in DEAL_EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {col_type}")
    conn.commit()


def connect_db(path: str = "deals.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_deal_columns(conn)
    return conn
