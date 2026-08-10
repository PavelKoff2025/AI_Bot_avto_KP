"""Тесты CRM: статусы и ActionLog."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(ROOT))

from models import (  # noqa: E402
    ensure_action_log_table,
    list_actions,
    log_action,
    migrate_deal_statuses,
    normalize_status,
    status_after_etalon,
    status_after_kp_ready,
    status_after_kp_sent,
)


class StatusPipelineTests(unittest.TestCase):
    def test_legacy_map(self):
        self.assertEqual(normalize_status("sent"), "kp_sent")
        self.assertEqual(normalize_status("won"), "completed")
        self.assertEqual(normalize_status("approved"), "kp_ready")
        self.assertEqual(normalize_status("stalled"), "incomplete")

    def test_auto_etalon(self):
        self.assertEqual(status_after_etalon(can_generate_kp=False), "incomplete")
        self.assertEqual(status_after_etalon(can_generate_kp=True), "new")
        self.assertEqual(
            status_after_etalon(can_generate_kp=True, current="completed"),
            "completed",
        )

    def test_kp_flow(self):
        self.assertEqual(status_after_kp_ready("incomplete"), "kp_ready")
        self.assertEqual(status_after_kp_sent("kp_ready"), "kp_sent")
        self.assertEqual(status_after_kp_sent("lost"), "lost")


class ActionLogTests(unittest.TestCase):
    def test_log_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.db"
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE deals (id INTEGER PRIMARY KEY, status TEXT, created_at TEXT)"
            )
            conn.execute("INSERT INTO deals (id, status) VALUES (1, 'sent')")
            ensure_action_log_table(conn)
            migrate_deal_statuses(conn)
            row = conn.execute("SELECT status FROM deals WHERE id = 1").fetchone()
            self.assertEqual(row["status"], "kp_sent")

            log_action(conn, deal_id=1, action="created", detail="test", user_id=1)
            conn.commit()
            items = list_actions(conn, 1)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["action"], "created")
            self.assertIn("создана", items[0]["action_label"].lower())
            conn.close()


if __name__ == "__main__":
    unittest.main()
