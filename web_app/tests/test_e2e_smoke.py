"""E2E smoke CRM: login → deals → create → generate KP (без AI) → PDF → approve."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
sys.path.insert(0, str(WEB))
sys.path.insert(0, str(ROOT))

FULL_TRANSCRIPT = """
ПРОТОКОЛ ТЕЛЕФОННОГО РАЗГОВОРА
Клиент: Тест E2E
Телефон: +7 900 111-22-33
Email: e2e@example.com
Участок: 10 соток, Дмитровское шоссе
Площадь: 150 м²
Материал: газобетон
Сроки: август 2026
Финансирование: ипотека
"""


def _load_crm_app():
    """Загружает web_app/app.py, не пакет app/ из корня репо."""
    path = WEB / "app.py"
    spec = importlib.util.spec_from_file_location("crm_web_app", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["crm_web_app"] = mod
    spec.loader.exec_module(mod)
    return mod


class CrmE2ESmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.cwd = Path(cls._tmpdir.name)
        (cls.cwd / "reports" / "kp" / "stroika").mkdir(parents=True)
        cls._old_cwd = os.getcwd()
        os.chdir(cls.cwd)

        cls._env = mock.patch.dict(
            os.environ,
            {
                "ETALON_KP_THRESHOLD": "80",
                "SECRET_KEY": "e2e-test-secret",
                "OPENAI_API_KEY": "sk-test-not-used",
            },
            clear=False,
        )
        cls._env.start()

        cls.crm = _load_crm_app()
        # чистая БД: init_db создаст полную схему
        if Path("deals.db").exists():
            Path("deals.db").unlink()
        # обходим chicken-egg ensure_deal_columns на пустом файле
        bootstrap = sqlite3.connect("deals.db")
        bootstrap.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                client_phone TEXT,
                client_email TEXT,
                client_telegram TEXT,
                transcript TEXT,
                kp_options TEXT,
                ar_pdf TEXT,
                ir_pdf TEXT,
                delivery_method TEXT,
                delivery_date TIMESTAMP,
                status TEXT DEFAULT 'new',
                last_reminder TIMESTAMP,
                next_action_date TIMESTAMP,
                notes TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )
        bootstrap.commit()
        bootstrap.close()
        cls.crm.init_db()
        cls.app = cls.crm.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        os.chdir(cls._old_cwd)
        cls._tmpdir.cleanup()

    def test_01_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json().get("status"), "ok")
        r2 = self.client.get("/health?deep=1")
        self.assertEqual(r2.status_code, 200)
        body = r2.get_json()
        self.assertEqual(body.get("service"), "dommaster-crm")
        self.assertEqual((body.get("checks") or {}).get("db"), "ok")

    def test_02_login_and_pages(self):
        r = self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (302, 303))
        r = self.client.get("/deals/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Список сделок".encode("utf-8"), r.data)
        r = self.client.get("/help")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Справка".encode("utf-8"), r.data)
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)

    def test_03_create_deal_generate_approve_pdf(self):
        # логин
        self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )
        # создать сделку
        r = self.client.post(
            "/deals/new",
            data={
                "client_name": "Тест E2E",
                "client_phone": "+7 900 111-22-33",
                "client_email": "e2e@example.com",
                "plot": "10 соток, Дмитровское",
                "area": "150",
                "material": "газобетон",
                "timeline": "август 2026",
                "funding_source": "ипотека",
                "transcript": FULL_TRANSCRIPT,
            },
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (302, 303))
        # id из БД
        conn = sqlite3.connect("deals.db")
        deal_id = conn.execute("SELECT id FROM deals ORDER BY id DESC LIMIT 1").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(deal_id, 1)

        # карточка
        r = self.client.get(f"/deals/{deal_id}")
        self.assertEqual(r.status_code, 200)

        # генерация КП без AI
        r = self.client.post(
            f"/deals/{deal_id}/generate-kp",
            json={"watermark": "draft", "use_ai": False},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:500])
        data = r.get_json()
        self.assertIn(data.get("status"), ("ok", "success"))

        # PDF
        r = self.client.get(f"/deals/{deal_id}/kp.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data[:4] == b"%PDF" or r.mimetype == "application/pdf")

        # утверждение
        r = self.client.post(f"/deals/{deal_id}/approve-kp", json={})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:500])
        self.assertIn(r.get_json().get("status"), ("ok", "success"))

        # смена статуса
        r = self.client.post(f"/deals/{deal_id}/status", json={"status": "kp_sent"})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
