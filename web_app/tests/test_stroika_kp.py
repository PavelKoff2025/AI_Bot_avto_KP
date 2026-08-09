"""Тесты расчёта КП этапа «Стройка» (тёплый контур)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.stroika_kp import (  # noqa: E402
    PRICE_PER_M2,
    build_stroika_kp_context,
    calc_total,
    parse_area_m2,
    parse_budget_rub,
)


class StroikaKpTests(unittest.TestCase):
    def test_parse_area(self):
        self.assertEqual(parse_area_m2("150"), 150)
        self.assertEqual(parse_area_m2("150 м²"), 150)
        self.assertEqual(parse_area_m2("120-140 м2"), 130)

    def test_calc_total(self):
        self.assertEqual(calc_total(150), 6_150_000)
        self.assertEqual(PRICE_PER_M2, 41_000)

    def test_budget_parse(self):
        self.assertEqual(parse_budget_rub("7 млн"), 7_000_000)
        self.assertEqual(parse_budget_rub("7-8 млн"), 7_500_000)

    def test_context_requires_area(self):
        with self.assertRaises(ValueError):
            build_stroika_kp_context({"client_name": "Тест", "area": ""}, use_ai=False)

    def test_context_math(self):
        ctx = build_stroika_kp_context(
            {
                "id": 1,
                "client_name": "Пётр",
                "area": "150 м²",
                "plot": "МО",
                "budget": "7 млн",
            },
            use_ai=False,
            watermark="draft",
        )
        self.assertEqual(ctx["area_m2"], 150)
        self.assertEqual(ctx["total"], 6_150_000)
        self.assertEqual(ctx["watermark_label"], "ЧЕРНОВИК")
        self.assertIn("41 000", ctx["commercial"])


if __name__ == "__main__":
    unittest.main()
