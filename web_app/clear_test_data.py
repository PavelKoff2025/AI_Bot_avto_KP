#!/usr/bin/env python3
"""Очистка тестовых сделок в deals.db (SQLite, без SQLAlchemy).

Usage:
  cd web_app && python3 clear_test_data.py
  python3 web_app/clear_test_data.py
  python3 web_app/clear_test_data.py --yes          # без подтверждения
  python3 web_app/clear_test_data.py --yes --db /path/to/deals.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

WEB_APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_APP_DIR.parent
DEFAULT_DB = WEB_APP_DIR / "deals.db"
UPLOAD_DIRS = (
    WEB_APP_DIR / "uploads",
    Path("/tmp/uploads"),
)


def connect(db_path: Path) -> sqlite3.Connection:
    if str(WEB_APP_DIR) not in sys.path:
        sys.path.insert(0, str(WEB_APP_DIR))
    from db_utils import connect_db

    return connect_db(str(db_path))


def clear_uploads() -> int:
    deleted = 0
    for upload_dir in UPLOAD_DIRS:
        if not upload_dir.is_dir():
            continue
        for path in upload_dir.iterdir():
            if path.name.startswith("."):
                continue
            try:
                if path.is_file():
                    path.unlink()
                    deleted += 1
            except OSError as exc:
                print(f"⚠️  Не удалось удалить {path}: {exc}")
    return deleted


def clear_test_data(db_path: Path, *, reset_users: bool = False) -> None:
    if not db_path.exists():
        print(f"ℹ️  База не найдена: {db_path}")
        print("   Нечего очищать.")
        return

    conn = connect(db_path)
    try:
        deal_count = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        user_count = 0
        try:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        except sqlite3.Error:
            pass

        if deal_count == 0 and not reset_users:
            print("ℹ️  Нет сделок для очистки")
        else:
            print(f"🗑️  Найдено сделок: {deal_count}")
            if reset_users:
                print(f"👤 Найдено пользователей: {user_count}")

        files_deleted = clear_uploads()
        if files_deleted:
            print(f"📁 Удалено файлов загрузок: {files_deleted}")

        if deal_count:
            conn.execute("DELETE FROM deals")
            # сброс автоинкремента id
            try:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'deals'")
            except sqlite3.Error:
                pass
            print(f"✅ Удалено сделок: {deal_count}")

        if reset_users and user_count:
            conn.execute("DELETE FROM users")
            try:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'users'")
            except sqlite3.Error:
                pass
            print(f"✅ Удалено пользователей: {user_count}")

        conn.commit()
        print(f"💾 База очищена: {db_path}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Очистка тестовых сделок CRM")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("DEALS_DB", DEFAULT_DB)),
        help=f"Путь к deals.db (по умолчанию {DEFAULT_DB})",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Не спрашивать подтверждение",
    )
    parser.add_argument(
        "--reset-users",
        action="store_true",
        help="Также удалить всех пользователей (осторожно)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("🧹 ОЧИСТКА ТЕСТОВЫХ ДАННЫХ")
    print("=" * 50)
    print(f"БД: {args.db.resolve()}")
    if args.reset_users:
        print("Режим: сделки + пользователи")
    else:
        print("Режим: только сделки (пользователи сохраняются)")

    if not args.yes:
        confirm = input("⚠️  Удалить ВСЕ сделки? (да/нет): ").strip().lower()
        if confirm not in {"да", "д", "yes", "y"}:
            print("❌ Очистка отменена")
            return 1

    clear_test_data(args.db, reset_users=args.reset_users)
    print("\n✅ Готово! Можно загружать новые демо-протоколы.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
