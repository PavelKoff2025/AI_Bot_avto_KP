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
        self.assertEqual(calc_total(150), 11_250_000)
        self.assertEqual(PRICE_PER_M2, 75_000)

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
        self.assertEqual(ctx["total"], 11_250_000)
        self.assertEqual(ctx["watermark_label"], "ЧЕРНОВИК")
        self.assertIn("75 000", ctx["commercial"])
        self.assertNotIn("{", ctx["commercial"])
        names = [row["name"] for row in ctx["complectations_table"]]
        self.assertEqual(names, ["Тёплый контур", "White Box", "Под ключ"])
        self.assertIn("11 250 000", ctx["complectations_table"][0]["price"])
        self.assertIn("2 500 000", ctx["complectations_table"][1]["price"])
        self.assertIn("~", ctx["complectations_table"][1]["price"])
        self.assertEqual(ctx["complectations_table"][2]["price"], "индивидуально")
        self.assertNotIn("холодн", " ".join(ctx["complectations_notes"]).lower())
        self.assertIn("11 250 000", ctx["complectations_formula"])

    def test_commercial_rejects_dict_dump(self):
        from utils.stroika_kp import _validate_ai_texts

        long_ok = "Индивидуальный жилой дом площадью ориентировочно 150 м² в Московской области. Основной конструктив: газобетон."
        texts = _validate_ai_texts(
            {
                "architecture": long_ok,
                "engineering": long_ok,
                "specs": long_ok,
                "commercial": {
                    "price_per_sqm": "75 000 ₽/м²",
                    "total_price": "11 250 000 ₽",
                },
                "intro": long_ok,
            },
            area_m2=150,
            total=11_250_000,
        )
        self.assertNotIn("{", texts["commercial"])
        self.assertNotIn("price_per_sqm", texts["commercial"])
        self.assertIn("75 000", texts["commercial"])
        self.assertIn("11 250 000", texts["commercial"])

        texts2 = _validate_ai_texts(
            {
                "architecture": long_ok,
                "engineering": long_ok,
                "specs": long_ok,
                "commercial": "{'price_per_sqm': '75 000 ₽/м²', 'total_price': '11 250 000 ₽'}",
                "intro": long_ok,
            },
            area_m2=150,
            total=11_250_000,
        )
        self.assertNotIn("{", texts2["commercial"])
        self.assertIn("оплата поэтапная", texts2["commercial"].lower())


if __name__ == "__main__":
    unittest.main()
