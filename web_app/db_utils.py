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
    ("tk_cost", "INTEGER"),  # ориентировочная стоимость тёплого контура, ₽
    ("delivery_status", "TEXT"),
    ("delivery_error", "TEXT"),
    ("telegram_chat_id", "TEXT"),  # числовой chat_id для отправки КП ботом
    ("telegram_outbox", "TEXT"),  # JSON очередь отправки КП (когда VPS не достучится до Telegram)
)


def ensure_deal_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(deals)").fetchall()}
    for name, col_type in DEAL_EXTRA_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {col_type}")
    conn.commit()

    # Пересчёт Стоимости ТК по площади (стандарт 41 000 ₽/м²)
    try:
        from pricing import calc_tk_cost

        rows = conn.execute("SELECT id, area, tk_cost FROM deals").fetchall()
        for row in rows:
            cost = calc_tk_cost(row[1] if not isinstance(row, sqlite3.Row) else row["area"])
            deal_id = row[0] if not isinstance(row, sqlite3.Row) else row["id"]
            current = row[2] if not isinstance(row, sqlite3.Row) else row["tk_cost"]
            if cost is not None and current != cost:
                conn.execute("UPDATE deals SET tk_cost = ? WHERE id = ?", (cost, deal_id))
        conn.commit()
    except Exception:
        pass


def connect_db(path: str = "deals.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_deal_columns(conn)
    return conn
