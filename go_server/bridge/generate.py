# JSON stdin/stdout bridge: Go HTTP-сервер → Python utils (PDF).
#
# Request:
#   {"action":"report","text":"...","type":"ar"}
#   {"action":"kp","with_fz":false,"with_engineering":true,"text":"...","client_name":"Иван"}
#
# Response:
#   {"ok":true,"path":"reports/..."} / {"ok":true,"files":["..."]}
#   {"ok":false,"error":"..."}

from __future__ import annotations

import json
import sys
from pathlib import Path

# Корень Python-проекта (родитель go_server/)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return path.name


def handle_report(payload: dict) -> dict:
    from utils.config import resolve_report_type
    from utils.report_service import create_report

    text = (payload.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "Передайте text или file"}
    report_type = resolve_report_type(payload.get("type") or "client")
    pdf_path = create_report(text, report_type)
    return {"ok": True, "path": _rel(Path(pdf_path)), "name": Path(pdf_path).name}


def handle_kp(payload: dict) -> dict:
    from utils.kp_generator import generate_all_kp

    include_fz = bool(payload.get("with_fz", False))
    include_eng = bool(payload.get("with_engineering", False))
    dialog_text = (payload.get("text") or "").strip() or None
    client_name = (payload.get("client_name") or "").strip() or "Заказчик"
    paths = generate_all_kp(
        include_fz=include_fz,
        include_engineering=include_eng,
        dialog_text=dialog_text,
        client_name=client_name,
    )
    return {
        "ok": True,
        "with_fz": include_fz,
        "with_engineering": include_eng,
        "files": [_rel(Path(p)) for p in paths],
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"Некорректный JSON: {exc}"}, ensure_ascii=False))
        return 1

    action = (payload.get("action") or "").strip().lower()
    try:
        if action == "report":
            result = handle_report(payload)
        elif action == "kp":
            result = handle_kp(payload)
        else:
            result = {"ok": False, "error": f"Неизвестное action: {action!r} (report|kp)"}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
