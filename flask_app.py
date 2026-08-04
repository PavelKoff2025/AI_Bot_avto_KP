"""Опциональный Flask API для генерации отчётов."""

from __future__ import annotations

import os
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

from utils.config import (
    MAX_UPLOAD_BYTES,
    flask_api_token,
    resolve_report_type,
)
from utils.kp_generator import generate_all_kp
from utils.logging_setup import get_logger, setup_logging
from utils.report_service import create_report

load_dotenv()
setup_logging()
logger = get_logger("flask")


def _client_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _public_error(exc: Exception, status: int = 500):
    logger.exception("API error: %s", exc)
    return jsonify({"error": "Внутренняя ошибка сервера"}), status


def _require_api_auth(view):
    """Если FLASK_API_TOKEN задан — требуем заголовок X-API-Token или Bearer."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = flask_api_token()
        if not expected:
            # Dev-режим без токена: только loopback
            remote = (request.remote_addr or "").strip()
            if remote not in {"127.0.0.1", "::1", "localhost"}:
                logger.warning("Отклонён запрос без токена с %s", remote)
                return _client_error(
                    "Задайте FLASK_API_TOKEN в .env для доступа не с localhost",
                    401,
                )
            return view(*args, **kwargs)

        header = request.headers.get("X-API-Token", "").strip()
        auth = request.headers.get("Authorization", "").strip()
        bearer = ""
        if auth.lower().startswith("bearer "):
            bearer = auth[7:].strip()
        provided = header or bearer
        if provided != expected:
            return _client_error("Неверный или отсутствующий API-токен", 401)
        return view(*args, **kwargs)

    return wrapper


def _read_dialog_payload() -> tuple[str, str]:
    """Возвращает (dialog_text, report_type_raw)."""
    report_type = "client"
    dialog_text = ""

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        dialog_text = (payload.get("text") or "").strip()
        report_type = (payload.get("type") or "client").strip().lower()
    elif "file" in request.files:
        uploaded = request.files["file"]
        raw = uploaded.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError(f"Файл слишком большой (лимит {MAX_UPLOAD_BYTES} байт)")
        dialog_text = raw.decode("utf-8", errors="replace").strip()
        report_type = (request.form.get("type") or "client").strip().lower()
    else:
        dialog_text = (request.form.get("text") or "").strip()
        report_type = (request.form.get("type") or "client").strip().lower()

    return dialog_text, report_type


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/report")
    @_require_api_auth
    def api_create_report():
        try:
            dialog_text, report_type_raw = _read_dialog_payload()
            report_type = resolve_report_type(report_type_raw)
        except ValueError as exc:
            return _client_error(str(exc))

        if not dialog_text:
            return _client_error("Передайте text или file")

        try:
            pdf_path = create_report(dialog_text, report_type)
        except Exception as exc:  # noqa: BLE001
            return _public_error(exc)

        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=Path(pdf_path).name,
        )

    @app.post("/api/kp")
    @_require_api_auth
    def api_create_kp():
        payload = request.get_json(silent=True) or {}
        include_fz = bool(payload.get("with_fz", False))
        include_eng = bool(payload.get("with_engineering", False))
        dialog_text = (payload.get("text") or "").strip() or None
        client_name = (payload.get("client_name") or "").strip() or None
        try:
            paths = generate_all_kp(
                include_fz=include_fz,
                include_engineering=include_eng,
                dialog_text=dialog_text,
                client_name=client_name or "Заказчик",
            )
        except Exception as exc:  # noqa: BLE001
            return _public_error(exc)

        # Не отдаём абсолютные пути наружу — только имена файлов + относительный каталог
        files = []
        for p in paths:
            try:
                rel = str(p.relative_to(Path.cwd()))
            except ValueError:
                rel = p.name
            files.append(rel)

        return jsonify({
            "with_fz": include_fz,
            "with_engineering": include_eng,
            "files": files,
        })

    return app


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("FLASK_PORT", "5000"))
    create_app().run(host=host, port=port, debug=False)
