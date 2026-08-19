"""Тесты сравнения транскрибации с эталоном (День 3)."""

from __future__ import annotations

import os
import sys
import unittest

WEB_APP_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(WEB_APP_DIR))

from etalon_score import (  # noqa: E402
    ETALON_FIELDS,
    KP_THRESHOLD,
    can_generate_kp,
    etalon_match_score,
)
from pricing import calc_tk_cost  # noqa: E402
from transcript_parser_local import parse_transcript_local, validate_against_etalon  # noqa: E402


# Полный протокол ≈ 100% (все 7 обязательных полей эталона; бюджет и Telegram не обязательны)
PROTOCOL_100 = """
ПРОТОКОЛ ТЕЛЕФОННОГО РАЗГОВОРА № 12/07
Потенциальный заказчик: Иван
Телефон: +7 999 123-45-67
Email: ivan.petrov@mail.ru
Telegram: @ivan_petrov

ХОД РАЗГОВОРА:
Участок: 10 соток, Дмитровское шоссе.
Площадь дома 120–140 м².
Материал стен — газобетон.
Сроки: август 2026.
Финансирование: свои накопления и маткапитал.
"""

# ~43%: 3 из 7 (телефон, email, площадь)
PROTOCOL_50 = """
Клиент: Пётр
Телефон: +7 900 111-22-33
Email: petr@mail.ru
Хочет дом 100 м².
Бюджет примерно 5 млн руб.
Про материал стен и место строительства ещё не решил, сроки не обсуждали.
"""

# ~86%: 6 из 7 (без финансирования); Telegram не обязателен
PROTOCOL_70 = """
Потенциальный заказчик: Анна
Телефон: +7 911 222-33-44
Email: anna@example.com
Участок: 8 соток рядом с Истрой.
Площадь 110–120 м², материал кирпич.
Старт планирует на весна.
"""


class TestValidateAgainstEtalon(unittest.TestCase):
    def test_etalon_has_seven_fields_without_budget_and_telegram(self):
        keys = [k for k, _ in ETALON_FIELDS]
        self.assertEqual(len(keys), 7)
        self.assertNotIn("budget", keys)
        self.assertNotIn("client_telegram", keys)
        self.assertIn("client_phone", keys)
        self.assertIn("client_email", keys)

    def test_timber_requires_catalog_project(self):
        base = {
            "client_phone": "+79164443322",
            "client_email": "dmitry_b@inbox.ru",
            "plot": "8 соток",
            "area": "200 м²",
            "material": "клееный брус",
            "timeline": "август 2026",
            "funding_source": "собственные средства",
        }
        without = etalon_match_score(base)
        self.assertIn("Проект каталога", without["missing"])
        self.assertFalse(without["can_generate_kp"])
        with_proj = etalon_match_score({**base, "catalog_project": "Сириус 2.0"})
        self.assertEqual(with_proj["score"], 100)
        self.assertTrue(with_proj["can_generate_kp"])
        self.assertEqual(with_proj["total"], 8)

    def test_tk_cost_from_area(self):
        self.assertEqual(calc_tk_cost("150 м²"), 11_250_000)
        self.assertEqual(calc_tk_cost("120-140"), 9_750_000)  # 130 × 75000

    def test_protocol_100_percent_can_generate_kp(self):
        result = validate_against_etalon(PROTOCOL_100)
        self.assertEqual(result["score"], 100, msg=f"missing={result['missing']}")
        self.assertTrue(result["is_complete"])
        self.assertTrue(result["can_generate_kp"])
        self.assertEqual(result["missing"], [])
        self.assertTrue(can_generate_kp(result["score"]))

    def test_protocol_partial_lists_missing(self):
        result = validate_against_etalon(PROTOCOL_50)
        # 3/7 ≈ 43%
        self.assertGreaterEqual(result["score"], 30)
        self.assertLessEqual(result["score"], 50)
        self.assertFalse(result["is_complete"])
        self.assertFalse(result["can_generate_kp"])
        self.assertTrue(len(result["missing"]) >= 4)
        for label in ("Участок", "Материал стен", "Сроки старта"):
            self.assertIn(label, result["missing"])
        self.assertNotIn("Бюджет", result["missing"])
        self.assertNotIn("Telegram", result["missing"])

    def test_protocol_missing_funding_only(self):
        result = validate_against_etalon(PROTOCOL_70)
        # 6/7 ≈ 86% → уже можно КП
        self.assertGreaterEqual(result["score"], KP_THRESHOLD)
        self.assertEqual(result["grade"], "high")
        self.assertTrue(result["can_generate_kp"])
        self.assertFalse(result["is_complete"])
        self.assertNotIn("Telegram", result["missing"])
        self.assertIn("Финансирование", result["missing"])
        self.assertTrue(result["questions"])

    def test_overrides_fill_missing_fields(self):
        result = validate_against_etalon(
            PROTOCOL_70,
            overrides={
                "funding_source": "ипотека",
            },
        )
        self.assertEqual(result["score"], 100)
        self.assertTrue(result["can_generate_kp"])
        self.assertNotIn("Финансирование", result["missing"])

    def test_parse_then_score_consistency(self):
        parsed = parse_transcript_local(PROTOCOL_100)
        scored = etalon_match_score(parsed)
        validated = validate_against_etalon(PROTOCOL_100)
        self.assertEqual(scored["score"], validated["score"])
        self.assertEqual(scored["missing"], validated["missing"])

    def test_empty_transcript(self):
        result = validate_against_etalon("")
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["can_generate_kp"])
        self.assertEqual(len(result["missing"]), 7)


if __name__ == "__main__":
    unittest.main()
