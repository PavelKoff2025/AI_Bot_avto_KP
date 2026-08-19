"""Админ-API: очистка сделок и загрузка демо-протоколов."""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Blueprint, jsonify, redirect, session, url_for

from clear_test_data import clear_test_data
from db_utils import connect_db
from load_demo_protocols import load_demo_protocols
from authz import DENY_ADMIN_ACTION_MSG, is_service_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

WEB_APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = WEB_APP_DIR / "deals.db"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def deals_db_path() -> Path:
    return Path(os.environ.get("DEALS_DB", DEFAULT_DB))


@admin_bp.route("/clear-deals", methods=["POST"])
@login_required
def clear_deals():
    """Очистка всех сделок + uploads."""
    if not is_service_admin():
        return jsonify({"success": False, "message": DENY_ADMIN_ACTION_MSG}), 403
    try:
        db_path = deals_db_path()
        count = 0
        if db_path.exists():
            conn = connect_db(str(db_path))
            try:
                count = int(conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0])
            finally:
                conn.close()

        clear_test_data(db_path, reset_users=False)
        return jsonify({
            "success": True,
            "message": f"Удалено {count} сделок",
            "deleted": count,
        })
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@admin_bp.route("/load-demo", methods=["POST"])
@login_required
def load_demo():
    """Бэкап БД → очистка → загрузка 4 демо-протоколов."""
    if not is_service_admin():
        return jsonify({"success": False, "message": DENY_ADMIN_ACTION_MSG}), 403
    try:
        db_path = deals_db_path()

        if db_path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = db_path.with_name(f"deals.db.backup_{stamp}")
            shutil.copy2(db_path, backup)

        rc = load_demo_protocols(db_path, clear_first=True)
        if rc != 0:
            return jsonify({
                "success": False,
                "message": "Загрузка завершилась с ошибками",
            }), 500

        loaded = 0
        if db_path.exists():
            conn = connect_db(str(db_path))
            try:
                loaded = int(conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0])
            finally:
                conn.close()

        return jsonify({
            "success": True,
            "message": f"Загружено {loaded} демо-протоколов",
            "loaded": loaded,
        })
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
