"""Аналитика CRM для дашборда."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Mapping


def _parse_day(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if len(text) < 10:
        return None
    return text[:10]


def _has_kp(deal: Mapping[str, Any]) -> bool:
    status = str(deal.get("status") or "")
    if status in {"kp_ready", "kp_sent", "completed"}:
        return True
    raw = deal.get("kp_options")
    if not raw:
        return False
    if isinstance(raw, dict):
        return bool(raw.get("pdf_path") or raw.get("total"))
    try:
        data = json.loads(raw)
        return isinstance(data, dict) and bool(data.get("pdf_path") or data.get("total"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def _is_sent(deal: Mapping[str, Any]) -> bool:
    status = str(deal.get("status") or "")
    if status in {"kp_sent", "completed"}:
        return True
    delivery = str(deal.get("delivery_status") or "")
    return delivery in {"ok", "queued", "partial"}


def _is_in_progress(deal: Mapping[str, Any]) -> bool:
    return str(deal.get("status") or "new") not in {"completed", "lost"}


def build_dashboard_stats(
    deals: list[Mapping[str, Any]],
    *,
    chart_days: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Конверсия, средний чек, сделки в работе, график по дням."""
    now = now or datetime.now()
    total = len(deals)
    with_kp = sum(1 for d in deals if _has_kp(d))
    sent = sum(1 for d in deals if _is_sent(d))
    completed = sum(1 for d in deals if str(d.get("status") or "") == "completed")
    in_progress = sum(1 for d in deals if _is_in_progress(d))

    costs = []
    for d in deals:
        raw = d.get("tk_cost")
        if raw is None:
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            costs.append(val)
    avg_check = int(round(sum(costs) / len(costs))) if costs else 0

    def pct(part: int, whole: int) -> float:
        return round(100.0 * part / whole, 1) if whole else 0.0

    funnel = {
        "calls": total,
        "kp": with_kp,
        "sent": sent,
        "completed": completed,
        "call_to_kp_pct": pct(with_kp, total),
        "kp_to_sent_pct": pct(sent, with_kp),
        "call_to_sent_pct": pct(sent, total),
        "sent_to_done_pct": pct(completed, sent),
    }

    day_keys: list[str] = []
    for i in range(chart_days - 1, -1, -1):
        day_keys.append((now - timedelta(days=i)).strftime("%Y-%m-%d"))
    counter: Counter[str] = Counter()
    for d in deals:
        day = _parse_day(d.get("created_at"))
        if day and day in day_keys:
            counter[day] += 1

    chart = {
        "labels": [k[5:] for k in day_keys],  # MM-DD
        "full_labels": day_keys,
        "counts": [counter.get(k, 0) for k in day_keys],
    }

    return {
        "total": total,
        "in_progress": in_progress,
        "avg_check": avg_check,
        "avg_check_fmt": f"{avg_check:,}".replace(",", " ") + " ₽" if avg_check else "—",
        "funnel": funnel,
        "chart": chart,
        "status_counts": {
            "new": sum(1 for d in deals if d.get("status") == "new"),
            "incomplete": sum(1 for d in deals if d.get("status") == "incomplete"),
            "kp_ready": sum(1 for d in deals if d.get("status") == "kp_ready"),
            "kp_sent": sum(1 for d in deals if d.get("status") == "kp_sent"),
            "completed": completed,
            "lost": sum(1 for d in deals if d.get("status") == "lost"),
        },
    }


def collect_deal_files(deal: Mapping[str, Any], kp_meta: dict | None) -> list[dict[str, Any]]:
    """Список файлов сделки для вкладки «Файлы»."""
    files: list[dict[str, Any]] = []
    if kp_meta and kp_meta.get("pdf_path"):
        files.append(
            {
                "kind": "kp",
                "title": f"КП {kp_meta.get('kp_number') or ''}".strip(),
                "name": f"KP_DomMaster_deal{deal.get('id')}.pdf",
                "meta": kp_meta.get("total_fmt") or "",
                "download": True,
            }
        )
    if deal.get("transcript"):
        files.append(
            {
                "kind": "transcript",
                "title": "Транскрибация",
                "name": f"deal{deal.get('id')}_transcript.txt",
                "meta": f"{len(str(deal.get('transcript') or ''))} символов",
                "download": False,
            }
        )
    for key, title in (("ar_pdf", "Архитектурные решения"), ("ir_pdf", "Инженерные решения")):
        path = deal.get(key)
        if path:
            files.append(
                {
                    "kind": key,
                    "title": title,
                    "name": str(path).split("/")[-1],
                    "meta": "",
                    "download": False,
                }
            )
    return files
