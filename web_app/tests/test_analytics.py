"""Тесты аналитики дашборда."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from analytics import build_dashboard_stats, collect_deal_files


class DashboardStatsTests(unittest.TestCase):
    def test_funnel_and_avg(self):
        now = datetime(2026, 8, 10, 12, 0, 0)
        deals = [
            {
                "id": 1,
                "status": "incomplete",
                "tk_cost": 7_500_000,
                "created_at": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "kp_options": None,
            },
            {
                "id": 2,
                "status": "kp_ready",
                "tk_cost": 11_250_000,
                "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "kp_options": '{"pdf_path":"/tmp/a.pdf","total":11250000}',
            },
            {
                "id": 3,
                "status": "kp_sent",
                "tk_cost": 11_250_000,
                "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "delivery_status": "ok",
                "kp_options": '{"pdf_path":"/tmp/b.pdf"}',
            },
        ]
        stats = build_dashboard_stats(deals, chart_days=3, now=now)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["in_progress"], 3)
        self.assertEqual(stats["funnel"]["kp"], 2)
        self.assertEqual(stats["funnel"]["sent"], 1)
        self.assertEqual(stats["avg_check"], int(round((7500000 + 11250000 + 11250000) / 3)))
        self.assertEqual(sum(stats["chart"]["counts"]), 3)

    def test_files(self):
        files = collect_deal_files(
            {"id": 7, "transcript": "hello"},
            {"kp_number": "КП-1", "pdf_path": "/x.pdf", "total_fmt": "1 ₽"},
        )
        kinds = {f["kind"] for f in files}
        self.assertIn("kp", kinds)
        self.assertIn("transcript", kinds)


if __name__ == "__main__":
    unittest.main()
