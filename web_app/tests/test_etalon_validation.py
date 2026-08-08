"""Тесты сравнения транскрибации с эталоном (День 3)."""

from __future__ import annotations

import os
import sys
import unittest

WEB_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "web_app")
sys.path.insert(0, os.path.abspath(WEB_APP_DIR))

from etalon_score import KP_THRESHOLD, can_generate_kp, etalon_match_score  # noqa: E402
from transcript_parser_local import parse_transcript_local, validate_against_etalon  # noqa: E402


# Полный протокол ≈ 100% (все 9 полей эталона)
PROTOCOL_100 = """
ПРОТОКОЛ ТЕЛЕФОННОГО РАЗГОВОРА № 12/07
Потенциальный заказчик: Иван
Телефон: +7 999 123-45-67
Email: ivan.petrov@mail.ru
Telegram: @ivan_petrov

ХОД РАЗГОВОРА:
Участок: 10 соток, Дмитровское шоссе.
Бюджет: 7–8 млн руб.
Площадь дома 120–140 м².
Материал стен — газобетон.
Сроки: август 2026.
Финансирование: свои накопления и маткапитал.
"""

# ~50%: 4–5 из 9 полей (телефон, email, бюджет, площадь)
PROTOCOL_50 = """
Клиент: Пётр
Телефон: +7 900 111-22-33
Email: petr@mail.ru
Хочет дом 100 м².
Бюджет примерно 5 млн руб.
Про материал стен и место строительства ещё не решил, сроки не обсуждали.
"""

# ~70%: 6–7 из 9 (без telegram, без финансирования)
PROTOCOL_70 = """
Потенциальный заказчик: Анна
Телефон: +7 911 222-33-44
Email: anna@example.com
Участок: 8 соток рядом с Истрой.
Бюджет: 6 млн руб.
Площадь 110–120 м², материал кирпич.
Старт планирует на весна.
"""


class TestValidateAgainstEtalon(unittest.TestCase):
    def test_protocol_100_percent_can_generate_kp(self):
        result = validate_against_etalon(PROTOCOL_100)
        self.assertEqual(result["score"], 100, msg=f"missing={result['missing']}")
        self.assertTrue(result["is_complete"])
        self.assertTrue(result["can_generate_kp"])
        self.assertEqual(result["missing"], [])
        self.assertTrue(can_generate_kp(result["score"]))

    def test_protocol_50_percent_lists_missing(self):
        result = validate_against_etalon(PROTOCOL_50)
        # Ожидаем около 44–56% (4–5/9)
        self.assertGreaterEqual(result["score"], 40)
        self.assertLessEqual(result["score"], 60)
        self.assertFalse(result["is_complete"])
        self.assertFalse(result["can_generate_kp"])
        self.assertTrue(len(result["missing"]) >= 4)
        self.assertTrue(len(result["questions"]) >= 4)
        # Типичные пробелы для «половинного» протокола
        for label in ("Участок", "Материал стен", "Сроки старта"):
            self.assertIn(label, result["missing"])

    def test_protocol_70_percent_recommend_collect(self):
        result = validate_against_etalon(PROTOCOL_70)
        # 6–7 из 9 → ~67–78%
        self.assertGreaterEqual(result["score"], 60)
        self.assertLess(result["score"], KP_THRESHOLD)
        self.assertEqual(result["grade"], "mid")
        self.assertFalse(result["can_generate_kp"])
        self.assertFalse(result["is_complete"])
        self.assertIn("Telegram", result["missing"])
        self.assertIn("Финансирование", result["missing"])
        # Рекомендация: есть вопросы клиенту
        self.assertTrue(result["questions"])

    def test_overrides_fill_missing_fields(self):
        result = validate_against_etalon(
            PROTOCOL_70,
            overrides={
                "client_telegram": "@anna",
                "funding_source": "ипотека",
            },
        )
        self.assertGreaterEqual(result["score"], KP_THRESHOLD)
        self.assertTrue(result["can_generate_kp"])
        self.assertNotIn("Telegram", result["missing"])
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
        self.assertEqual(len(result["missing"]), 9)


if __name__ == "__main__":
    unittest.main()
