"""Проект инженерных решений (ИР) + предварительная смета (базовый вариант)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.ai_processor import process_engineering_with_ai
from utils.pdf_generator import REPORTS_DIR, generate_pdf_report

ENGINEERING_DIR = REPORTS_DIR / "engineering"

# Базовая смета инженерки для дома ~130 м² (МО), материалы + монтаж + проект
BASIC_ESTIMATE_ITEMS: list[dict[str, Any]] = [
    {
        "code": "ВК-1",
        "name": "Система водоснабжения",
        "detail": "Ввод, разводка ХВС/ГВС, коллекторы, фильтр грубой очистки, бойлер косвенного нагрева (базовый)",
        "price": 245_000,
    },
    {
        "code": "ВК-2",
        "name": "Система канализации",
        "detail": "Внутренняя разводка, выпуски, вентиляция стояка, подготовка к септику/ЛОС (без самого септика)",
        "price": 215_000,
    },
    {
        "code": "ОВ-1",
        "name": "Система отопления (газ)",
        "detail": "Двухконтурный/одноконтурный котёл, группа безопасности, обвязка, радиаторы в жилых, дымоход",
        "price": 420_000,
    },
    {
        "code": "ОВ-2",
        "name": "Система тёплых полов",
        "detail": "Контуры в мокрых и жилых зонах ~80–100 м² активного контура, коллектор, стяжка-подготовка",
        "price": 340_000,
    },
    {
        "code": "ОВ-3",
        "name": "Система вентиляции",
        "detail": "Приток + вытяжка санузлов/кухни, каналы, анемостаты; базовая схема без рекуператора премиум-класса",
        "price": 265_000,
    },
    {
        "code": "ПД-1",
        "name": "Проектная документация ИР (базовый комплект)",
        "detail": "Схемы ВК/ОВ, спецификация оборудования, пояснительная записка",
        "price": 95_000,
    },
]

# Итого пакета для включения одной строкой в КП
ENGINEERING_PACKAGE_TOTAL = sum(i["price"] for i in BASIC_ESTIMATE_ITEMS)

ENGINEERING_PACKAGE = {
    "name": "ИР — инженерные системы (базовый пакет)",
    "detail": (
        "Водоснабжение, канализация, отопление (газ), тёплые полы, вентиляция + проект ИР. "
        "Подробная смета — в приложении «Проект инженерных решений»."
    ),
    "price": ENGINEERING_PACKAGE_TOTAL,
    "scope": [f"{i['name']}: {i['detail']}" for i in BASIC_ESTIMATE_ITEMS],
}


def _fmt(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def build_engineering_context(
    dialog_text: str | None = None,
    *,
    use_ai: bool = True,
) -> dict[str, Any]:
    """Собирает данные для PDF проекта инженерных решений."""
    today = datetime.now().strftime("%d.%m.%Y")

    brief: dict[str, str] = {
        "client_name": "Иван",
        "project_name": "ИЖД, Московская область (Дмитровское шоссе)",
        "area": "120–140 м² (расчёт на 130 м²)",
        "plot_notes": (
            "Участок 10 соток, электричество есть; магистрального газа нет — "
            "предусмотрен сценарий с газгольдером / последующим подключением."
        ),
        "water_supply": (
            "Централизованный ввод при наличии или скважина + накопительная ёмкость; "
            "коллекторная разводка ХВС/ГВС, ГВС от котла/бойлера."
        ),
        "sewerage": (
            "Внутренняя самотёчная канализация с выпуском к септику/ЛОС на участке "
            "(септик — отдельная позиция, не в базовой смете)."
        ),
        "heating_gas": (
            "Газовый котёл в котельной/техпомещении, радиаторный контур + совмещение с тёплыми полами; "
            "при отсутствии магистрали — газгольдер (отдельная смета)."
        ),
        "floor_heating": (
            "Водяные тёплые полы в санузлах, кухне-гостиной и жилых комнатах по зонам; "
            "отдельные петли, терморегуляция по комнатам."
        ),
        "ventilation": (
            "Вытяжка из санузлов и кухни, организованный приток в жилые; "
            "каналы в потолке/шахтах, возможность апгрейда до ПВУ с рекуперацией."
        ),
        "assumptions": (
            "Одноэтажный дом ~130 м²; черновая отделка ещё впереди; "
            "инженерка монтируется до чистовой отделки заказчика."
        ),
        "risks": (
            "Уточнить источник воды, место септика, возможность установки газгольдера "
            "и требования газовой службы."
        ),
        "next_steps": (
            "Выезд инженера, обмер, согласование точек мокрых зон по АР, "
            "выпуск рабочих схем и спецификации под выбранное оборудование."
        ),
    }

    if dialog_text and use_ai:
        try:
            brief.update(process_engineering_with_ai(dialog_text))
        except Exception as exc:  # noqa: BLE001
            brief["assumptions"] = (
                f"{brief['assumptions']} (AI-бриф недоступен: {exc}; использован шаблон.)"
            )

    items = []
    total = 0
    for raw in BASIC_ESTIMATE_ITEMS:
        row = deepcopy(raw)
        total += int(row["price"])
        row["price_fmt"] = _fmt(row["price"])
        items.append(row)

    return {
        **brief,
        "doc_number": f"ИР-{datetime.now().strftime('%y%m%d')}",
        "date": today,
        "variant_label": "Базовый вариант",
        "accent": "#0b6e4f",
        "accent_soft": "#e6f5ef",
        "items": items,
        "total": total,
        "total_fmt": f"{_fmt(total)} ₽",
        "total_note": (
            f"Предварительная смета базового пакета ИР на ~130 м²: {_fmt(total)} ₽ "
            f"(~{_fmt(round(total / 130))} ₽/м²). Без септика/ЛОС и газгольдера."
        ),
        "included": [
            "Проектирование базового комплекта ИР",
            "Водоснабжение (внутренняя сеть)",
            "Канализация (внутренняя сеть)",
            "Отопление на газе (котёл + обвязка + радиаторы)",
            "Тёплые полы (водяные контуры базовой площади)",
            "Вентиляция (приток/вытяжка базовой схемы)",
            "Пусконаладка базового уровня",
        ],
        "excluded": [
            "Септик / ЛОС и земляные работы под них",
            "Газгольдер, врезка в магистраль, согласования газа",
            "Скважина «под ключ» и кессон (если нет центрального водопровода)",
            "Кондиционирование и умный дом",
            "Чистовая отделка и сантехприборы премиум-класса",
        ],
        "intro": (
            "Проект инженерных решений обеспечивает водоснабжение, канализацию, "
            "газовое отопление, тёплые полы и вентиляцию для комфортной эксплуатации дома. "
            "Ниже — предварительная смета базового варианта для согласования с заказчиком."
        ),
    }


def generate_engineering_project(
    dialog_text: str | None = None,
    *,
    use_ai: bool = True,
    output_path: str | Path | None = None,
) -> Path:
    """Генерирует PDF (+HTML/JSON) проекта инженерных решений."""
    ENGINEERING_DIR.mkdir(parents=True, exist_ok=True)
    data = build_engineering_context(dialog_text, use_ai=use_ai)

    if output_path is None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        output_path = ENGINEERING_DIR / f"IR_engineering_{stamp}.pdf"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    path = generate_pdf_report(
        data,
        output_path=output_path,
        template_name="engineering_template.html",
        save_html=True,
    )

    serializable = {
        k: v for k, v in data.items() if k != "items"
    }
    serializable["items"] = [
        {"code": i["code"], "name": i["name"], "detail": i["detail"], "price": i["price"]}
        for i in data["items"]
    ]
    output_path.with_suffix(".json").write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    print(generate_engineering_project(use_ai=False))
