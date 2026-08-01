"""Опциональный Flask API для генерации отчётов."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_file

from utils.kp_generator import generate_all_kp
from utils.report_service import create_report


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/report")
    def api_create_report():
        dialog_text = ""
        report_type = "client"

        if request.is_json:
            payload = request.get_json(silent=True) or {}
            dialog_text = (payload.get("text") or "").strip()
            report_type = (payload.get("type") or "client").strip().lower()
        elif "file" in request.files:
            uploaded = request.files["file"]
            dialog_text = uploaded.read().decode("utf-8").strip()
            report_type = (request.form.get("type") or "client").strip().lower()
        else:
            dialog_text = (request.form.get("text") or "").strip()
            report_type = (request.form.get("type") or "client").strip().lower()

        mapping = {
            "1": "client",
            "client": "client",
            "2": "design",
            "design": "design",
            "3": "ar",
            "ar": "ar",
            "4": "engineering",
            "engineering": "engineering",
            "ir": "engineering",
        }
        if report_type not in mapping:
            return jsonify({"error": "type: client | design | ar | engineering"}), 400
        report_type = mapping[report_type]

        if not dialog_text:
            return jsonify({"error": "Передайте text или file"}), 400

        try:
            pdf_path = create_report(dialog_text, report_type)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500

        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=Path(pdf_path).name,
        )

    @app.post("/api/kp")
    def api_create_kp():
        payload = request.get_json(silent=True) or {}
        include_fz = bool(payload.get("with_fz", False))
        include_eng = bool(payload.get("with_engineering", False))
        dialog_text = (payload.get("text") or "").strip() or None
        try:
            paths = generate_all_kp(
                include_fz=include_fz,
                include_engineering=include_eng,
                dialog_text=dialog_text,
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500
        return jsonify({
            "with_fz": include_fz,
            "with_engineering": include_eng,
            "files": [str(p) for p in paths],
        })

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
