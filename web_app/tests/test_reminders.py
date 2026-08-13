"""Напоминания по зависшим сделкам (нет действий > N дней)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(ROOT))

from models import ensure_action_log_table, log_action  # noqa: E402
from utils.reminders import (  # noqa: E402
    _cooldown_ok,
    find_stale_deals,
    format_reminder_message,
    last_activity_at,
    process_reminders,
)


NOW = datetime(2026, 8, 13, 21, 0, 0)


def _conn() -> sqlite3.Connection:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE deals (
            id INTEGER PRIMARY KEY,
            client_name TEXT,
            status TEXT,
            created_at TEXT,
            delivery_date TEXT,
            last_reminder TEXT,
            user_id INTEGER
        )
        """
    )
    ensure_action_log_table(conn)
    return conn


def _insert(
    conn: sqlite3.Connection,
    *,
    deal_id: int,
    name: str,
    status: str,
    created_at: datetime,
    last_reminder: datetime | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO deals (id, client_name, status, created_at, last_reminder)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            deal_id,
            name,
            status,
            created_at.strftime("%Y-%m-%d %H:%M:%S"),
            last_reminder.strftime("%Y-%m-%d %H:%M:%S") if last_reminder else None,
        ),
    )


class ReminderLogicTests(unittest.TestCase):
    def test_stale_after_three_days(self):
        conn = _conn()
        _insert(conn, deal_id=1, name="Старая", status="new", created_at=NOW - timedelta(days=4))
        _insert(conn, deal_id=2, name="Свежая", status="new", created_at=NOW - timedelta(days=1))
        conn.commit()
        stale = find_stale_deals(conn, stale_days=3, now=NOW)
        ids = [d["id"] for d in stale]
        self.assertEqual(ids, [1])
        self.assertEqual(stale[0]["idle_days"], 4)
        conn.close()

    def test_terminal_statuses_skipped(self):
        conn = _conn()
        _insert(conn, deal_id=1, name="Win", status="completed", created_at=NOW - timedelta(days=10))
        _insert(conn, deal_id=2, name="Lose", status="lost", created_at=NOW - timedelta(days=10))
        _insert(conn, deal_id=3, name="Won legacy", status="won", created_at=NOW - timedelta(days=10))
        conn.commit()
        self.assertEqual(find_stale_deals(conn, stale_days=3, now=NOW), [])
        conn.close()

    def test_kp_sent_still_reminded(self):
        conn = _conn()
        _insert(conn, deal_id=1, name="Ждём ответ", status="kp_sent", created_at=NOW - timedelta(days=5))
        conn.commit()
        stale = find_stale_deals(conn, stale_days=3, now=NOW)
        self.assertEqual([d["id"] for d in stale], [1])
        conn.close()

    def test_recent_action_log_clears_stale(self):
        conn = _conn()
        _insert(conn, deal_id=1, name="Живая", status="incomplete", created_at=NOW - timedelta(days=10))
        log_action(conn, deal_id=1, action="updated", detail="позвонили")
        conn.execute(
            "UPDATE action_log SET created_at = ? WHERE deal_id = 1",
            ((NOW - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),),
        )
        conn.commit()
        self.assertEqual(find_stale_deals(conn, stale_days=3, now=NOW), [])
        conn.close()

    def test_reminder_sent_does_not_reset_idle(self):
        """Повтор через cooldown 24ч: сам факт напоминания — не активность по сделке."""
        conn = _conn()
        created = NOW - timedelta(days=6)
        _insert(conn, deal_id=1, name="Завис", status="incomplete", created_at=created)
        log_action(conn, deal_id=1, action="reminder_sent", detail="Простой 6 дн.")
        conn.execute(
            "UPDATE action_log SET created_at = ? WHERE deal_id = 1",
            ((NOW - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),),
        )
        conn.commit()
        stale = find_stale_deals(conn, stale_days=3, now=NOW)
        self.assertEqual([d["id"] for d in stale], [1])
        self.assertGreaterEqual(stale[0]["idle_days"], 6)
        conn.close()

    def test_cooldown_blocks_due(self):
        deal = {"last_reminder": (NOW - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")}
        self.assertFalse(_cooldown_ok(deal, now=NOW))
        deal2 = {"last_reminder": (NOW - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")}
        self.assertTrue(_cooldown_ok(deal2, now=NOW))
        self.assertTrue(_cooldown_ok({}, now=NOW))

    def test_process_dry_does_not_notify(self):
        conn = _conn()
        _insert(conn, deal_id=1, name="А", status="new", created_at=NOW - timedelta(days=4))
        conn.commit()
        info = process_reminders(conn, notify=False, stale_days=3, now=NOW)
        self.assertEqual(info["stale_total"], 1)
        self.assertEqual(info["due"], 1)
        self.assertEqual(info["notified"], 0)
        row = conn.execute("SELECT last_reminder FROM deals WHERE id = 1").fetchone()
        self.assertIsNotNone(row["last_reminder"])
        conn.close()

    def test_message_lists_deals(self):
        text = format_reminder_message(
            [{"id": 7, "client_name": "Иван", "idle_days": 5, "status": "incomplete"}]
        )
        self.assertIn("#7 Иван", text)
        self.assertIn("5 дн.", text)
        self.assertIn("/deals/7", text)


class LastActivityTests(unittest.TestCase):
    def test_falls_back_to_created_at(self):
        conn = _conn()
        created = NOW - timedelta(days=4)
        _insert(conn, deal_id=1, name="X", status="new", created_at=created)
        conn.commit()
        ts = last_activity_at(conn, dict(conn.execute("SELECT * FROM deals").fetchone()))
        self.assertEqual(ts, created)
        conn.close()


if __name__ == "__main__":
    unittest.main()
