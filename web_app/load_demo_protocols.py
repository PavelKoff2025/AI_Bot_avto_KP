#!/usr/bin/env python3
"""Массовая загрузка демо-протоколов в deals.db (SQLite).

Usage:
  cd web_app && python3 load_demo_protocols.py
  python3 web_app/load_demo_protocols.py --yes --clear
  python3 web_app/load_demo_protocols.py --db /root/AI_Bot_avto_KP/web_app/deals.db --yes --clear
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

WEB_APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_APP_DIR.parent
DEFAULT_DB = WEB_APP_DIR / "deals.db"
UPLOAD_DIR = WEB_APP_DIR / "uploads"

if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

from db_utils import connect_db  # noqa: E402
from etalon_score import etalon_match_score  # noqa: E402
from transcript_parser_local import TranscriptParser  # noqa: E402

DEMO_FILES: list[tuple[str, str]] = [
    ("knowledge_base/demo_protocol_1.md", "Демо №1 — полный (100%)"),
    ("knowledge_base/demo_protocol_2.md", "Демо №2 — частичный (44%)"),
    ("knowledge_base/demo_protocol_3.md", "Демо №3 — почти готов (78%)"),
    ("knowledge_base/demo_protocol_4.md", "Демо №4 — мало данных (0%)"),
]


def _default_user_id(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        return int(row[0]) if row else None
    except sqlite3.Error:
        return None


def clear_deals(conn: sqlite3.Connection) -> int:
    count = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    conn.execute("DELETE FROM deals")
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'deals'")
    except sqlite3.Error:
        pass
    conn.commit()
    return int(count)


def insert_deal(
    conn: sqlite3.Connection,
    *,
    title: str,
    content: str,
    parsed: dict,
    user_id: int | None,
) -> int:
    notes = f"[demo] {title}"
    cursor = conn.execute(
        """
        INSERT INTO deals (
            client_name, client_phone, client_email, client_telegram,
            transcript, notes, user_id, status,
            plot, budget, area, material, timeline, funding_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            parsed.get("client_name") or parsed.get("name") or "Тестовый клиент",
            parsed.get("client_phone") or parsed.get("phone") or None,
            parsed.get("client_email") or parsed.get("email") or None,
            parsed.get("client_telegram") or None,
            content,
            notes,
            user_id,
            "new",
            parsed.get("plot") or parsed.get("plot_size") or None,
            parsed.get("budget") or None,
            parsed.get("area") or None,
            parsed.get("material") or None,
            parsed.get("timeline") or parsed.get("deadline") or None,
            parsed.get("funding_source") or parsed.get("financing") or None,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    from db_utils import ensure_deal_columns

    ensure_deal_columns(conn)


def load_demo_protocols(db_path: Path, *, clear_first: bool = False) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    parser = TranscriptParser()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if clear_first:
        removed = clear_deals(conn)
        print(f"🗑️  Удалено существующих сделок: {removed}")

    user_id = _default_user_id(conn)
    if user_id:
        print(f"👤 Сделки привязаны к user_id={user_id}")
    else:
        print("👤 Пользователей нет — сделки без user_id")

    loaded = 0
    errors = 0

    for rel_path, title in DEMO_FILES:
        full_path = PROJECT_ROOT / rel_path
        if not full_path.exists():
            print(f"❌ Файл не найден: {rel_path}")
            errors += 1
            continue

        try:
            content = full_path.read_text(encoding="utf-8")
            parsed = parser.parse_text(content)
            deal_id = insert_deal(
                conn,
                title=title,
                content=content,
                parsed=parsed,
                user_id=user_id,
            )

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            upload_name = f"{deal_id}_{stamp}_demo_{loaded + 1}.txt"
            upload_path = UPLOAD_DIR / upload_name
            upload_path.write_text(content, encoding="utf-8")

            # Оценка как в CRM (etalon_score, 9 полей)
            match = etalon_match_score(parsed)
            percent = match["score"]
            ready = match["can_generate_kp"]
            status = "✅ ГОТОВ К КП" if ready else "⚠️ НЕПОЛНЫЙ"
            print(f"📄 {title} → сделка #{deal_id}")
            print(f"   📊 Заполнение: {percent}% · {status}")
            if match["missing"]:
                print(f"   ❌ Пропущено: {', '.join(match['missing'])}")
            print()
            loaded += 1
        except Exception as exc:
            print(f"❌ Ошибка при загрузке {title}: {exc}")
            errors += 1

    conn.close()
    print("=" * 50)
    print(f"📊 Загружено: {loaded}")
    print(f"❌ Ошибок: {errors}")
    print("=" * 50)
    return 0 if errors == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Загрузка демо-протоколов в CRM")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("DEALS_DB", DEFAULT_DB)),
        help=f"Путь к deals.db (по умолчанию {DEFAULT_DB})",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Без вопросов")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить сделки перед загрузкой",
    )
    args = parser.parse_args()

    print("📥 ЗАГРУЗКА ДЕМО-ПРОТОКОЛОВ")
    print("=" * 50)
    print(f"БД: {args.db.resolve()}")

    conn = connect_db(str(args.db)) if args.db.exists() else None
    existing = 0
    if conn is not None:
        try:
            existing = int(conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0])
        except sqlite3.Error:
            existing = 0
        conn.close()

    clear_first = args.clear
    if existing > 0 and not args.clear:
        print(f"⚠️  В базе уже есть {existing} сделок")
        if args.yes:
            print("Подсказка: добавьте --clear, чтобы заменить их")
        else:
            answer = input("Очистить существующие сделки перед загрузкой? (да/нет): ").strip().lower()
            if answer in {"да", "д", "yes", "y"}:
                clear_first = True
            else:
                add = input("Добавить демо поверх существующих? (да/нет): ").strip().lower()
                if add not in {"да", "д", "yes", "y"}:
                    print("❌ Загрузка отменена")
                    return 1

    rc = load_demo_protocols(args.db, clear_first=clear_first)
    print("\n✅ Готово! Откройте список сделок: /deals/")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
