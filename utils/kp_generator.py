"""Данные и генерация коммерческих предложений (КП) по тёплому контуру."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from utils.config import DEFAULT_CLIENT_NAME, sanitize_client_name
from utils.engineering_generator import (
    ENGINEERING_PACKAGE,
    ENGINEERING_PACKAGE_TOTAL,
    generate_engineering_project,
)
from utils.logging_setup import get_logger
from utils.money import format_money
from utils.pdf_generator import REPORTS_DIR, generate_pdf_report

logger = get_logger("kp")
KP_DIR = REPORTS_DIR / "kp"

# Варианты для ТГ-бота / менеджера ОП
BOT_VARIANTS = {
    "basic": {
        "index": 0,
        "title": "Базовый",
        "description": "Газобетон · базовый тёплый контур",
    },
    "optimal": {
        "index": 2,
        "title": "Средний (оптимальный)",
        "description": "Клееный брус · средний",
    },
    "plus": {
        "index": 1,
        "title": "Средний +",
        "description": "Газобетон · средний +",
    },
}

FZ_PACKAGES = {
    "base": {
        "name": "ФЗ — фасадная отделка (базовая)",
        "detail": "Штукатурный фасад, грунт, покраска, откосы, простые узлы",
        "price": 450_000,
        "scope": [
            "Подготовка поверхностей наружных стен",
            "Штукатурный слой + декоративное покрытие",
            "Оформление оконных/дверных откосов снаружи",
            "Базовые примыкания к цоколю и кровле",
        ],
    },
    "plus": {
        "name": "ФЗ — фасадная отделка (средний+)",
        "detail": "Комбинированный фасад: штукатурка + фиброцемент/клинкерные акценты",
        "price": 780_000,
        "scope": [
            "Усиленная подготовка и армирующий слой",
            "Декоративная штукатурка + акцентные панели",
            "Тёплые наружные откосы",
            "Расширенные узлы примыканий и цокольная отделка",
        ],
    },
    "timber": {
        "name": "ФЗ — фасадная отделка бруса (средняя)",
        "detail": "Шлифовка, масло/лазурь в 2 слоя, герметизация швов, наличники",
        "price": 520_000,
        "scope": [
            "Механическая подготовка поверхности бруса",
            "Защитно-декоративное покрытие (масло/лазурь)",
            "Герметизация межвенцовых/торцевых узлов",
            "Наличники и оформление проёмов снаружи",
        ],
    },
}


def _fmt(amount: int) -> str:
    """Совместимость; предпочтительно format_money."""
    return format_money(amount)


def _with_prices(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    total = 0
    result = []
    for item in items:
        price = int(item["price"])
        total += price
        row = deepcopy(item)
        row["price_fmt"] = _fmt(price)
        result.append(row)
    return result, total


def _base_context(*, client_name: str = DEFAULT_CLIENT_NAME) -> dict[str, Any]:
    today = datetime.now()
    return {
        "date": today.strftime("%d.%m.%Y"),
        "valid_until": (today + timedelta(days=14)).strftime("%d.%m.%Y"),
        "client_name": sanitize_client_name(client_name),
        "object_desc": (
            "Индивидуальный жилой дом, 1 этаж, современный стиль, "
            "ориентир 120–140 м² (расчёт выполнен на 130 м²)"
        ),
        "area": "130 м²",
        "plot": "Московская область, р-н Дмитровского шоссе, 10 соток, электричество есть",
        "manager": "Светлана, отдел продаж «Дом-Мастер»",
        "included": [
            "Фундамент заливной (бетонные работы + арматура)",
            "Наружные стены выбранного материала",
            "Межкомнатные перегородки",
            "Окна ПВХ с монтажом",
            "Кровля: стропильная система + гибкая черепица",
            "Дверь входная металлическая с монтажом",
            "Гидроизоляция, утепление по составу варианта",
            "Доставка основных материалов на участок (в пределах 50 км от склада)",
        ],
        "excluded": [
            "Чистовая внутренняя отделка (силами заказчика)",
            "Инженерные сети «под ключ» — опция --with-engineering",
            "Газгольдер / подключение газа (вне базовой ИР)",
            "Ландшафт, забор, отмостка премиум-класса",
            "Мебель, техника, внутренние двери",
            "Госпошлины и согласования сверх стандартного комплекта АР/КР",
            "Фасадная отделка (ФЗ) — опция --with-fz",
        ],
        "warranty": [
            "5 лет — на конструктив (фундамент, стены, несущие элементы)",
            "2 года — на кровельные и монтажные работы тёплого контура",
            "2 года — на монтаж инженерных систем (если ИР включена в КП)",
            "Гарантия фиксируется в договоре подряда",
        ],
        "next_step": (
            "Выберите вариант КП. При необходимости приложим проект ИР и/или ФЗ. "
            "После выезда на участок подготовим договор и календарный план."
        ),
        "include_fz": False,
        "include_engineering": False,
        "fz_section": None,
        "engineering_section": None,
        "engineering_attachment": None,
    }


def _assemble(
    raw: list[dict[str, Any]],
    *,
    include_fz: bool,
    fz_key: str,
    include_engineering: bool,
) -> tuple[list[dict[str, Any]], int, dict[str, Any] | None, dict[str, Any] | None]:
    rows = list(raw)
    fz_info = None
    eng_info = None

    if include_fz:
        pkg = FZ_PACKAGES[fz_key]
        rows.append({
            "name": pkg["name"],
            "detail": pkg["detail"],
            "price": pkg["price"],
        })
        fz_info = {**pkg, "price_fmt": _fmt(pkg["price"])}

    if include_engineering:
        rows.append({
            "name": ENGINEERING_PACKAGE["name"],
            "detail": ENGINEERING_PACKAGE["detail"],
            "price": ENGINEERING_PACKAGE["price"],
        })
        eng_info = {
            **ENGINEERING_PACKAGE,
            "price_fmt": _fmt(ENGINEERING_PACKAGE_TOTAL),
        }

    items, total = _with_prices(rows)
    return items, total, fz_info, eng_info


def _filename_suffix(include_fz: bool, include_engineering: bool) -> str:
    parts = []
    if include_fz:
        parts.append("fz")
    if include_engineering:
        parts.append("ir")
    return ("_with_" + "_".join(parts)) if parts else ""


def _badge(include_fz: bool, include_engineering: bool) -> str:
    tags = []
    if include_fz:
        tags.append("ФЗ")
    if include_engineering:
        tags.append("ИР")
    return (" · + " + " + ".join(tags)) if tags else ""


def build_variants(
    include_fz: bool = False,
    include_engineering: bool = False,
    *,
    client_name: str = DEFAULT_CLIENT_NAME,
) -> list[dict[str, Any]]:
    """Три варианта КП с опциональными ФЗ и/или инженеркой (ИР)."""
    base = _base_context(client_name=client_name)

    raw1 = [
        {"name": "Фундамент заливной ленточный", "detail": "Лента 400 мм, глубина 1,5 м, бетон B25, гидроизоляция", "price": 780_000},
        {"name": "Стены из газобетонных блоков", "detail": "D400–D500, толщина 375 мм, клей, армопояс", "price": 1_150_000},
        {"name": "Перегородки межкомнатные", "detail": "Газобетон 100 мм, ~45 м.п.", "price": 210_000},
        {"name": "Окна пластиковые", "detail": "ПВХ 70 мм, 2-камерный стеклопакет, 8–9 изделий", "price": 320_000},
        {"name": "Кровля — гибкая черепица", "detail": "Стропила, ОСП, подкладка, черепица эконом-сегмента", "price": 690_000},
        {"name": "Дверь входная железная", "detail": "Стальная дверь стандарт, утепление, монтаж", "price": 55_000},
        {"name": "Проект АР/КР (базовый комплект)", "detail": "Рабочая документация под выбранный конструктив", "price": 145_000},
    ]
    raw2 = [
        {"name": "Фундамент заливной утеплённый", "detail": "Лента усиленная / УШП-лайт, бетон B25–B30, ЭППС, гидроизоляция", "price": 1_050_000},
        {"name": "Стены из газобетонных блоков", "detail": "D400 премиум, 400 мм, клей, армопояс, перемычки", "price": 1_420_000},
        {"name": "Перегородки межкомнатные", "detail": "Газобетон 100–150 мм + усиление проёмов", "price": 280_000},
        {"name": "Окна пластиковые энергосберегающие", "detail": "ПВХ 76–80 мм, мультифункциональный стеклопакет, 8–9 изделий", "price": 480_000},
        {"name": "Кровля — гибкая черепица (средний+)", "detail": "Усиленная стропилка, мембрана, черепица бренд-сегмента", "price": 920_000},
        {"name": "Дверь входная железная с терморазрывом", "detail": "Терморазрыв, 2 контура уплотнения, монтаж", "price": 95_000},
        {"name": "Проект АР/КР расширенный", "detail": "АР + КР + узлы примыканий кровли/проёмов", "price": 195_000},
    ]
    raw3 = [
        {"name": "Фундамент заливной под брусовой дом", "detail": "Лента/ростверк под сруб, бетон B25, гидроизоляция, закладные", "price": 920_000},
        {"name": "Стены из клееного бруса", "detail": "Клееный брус 200×200 мм, камерная сушка, сборка сруба", "price": 2_150_000},
        {"name": "Перегородки межкомнатные", "detail": "Каркас/брус 100–150 мм под чистовую отделку заказчика", "price": 260_000},
        {"name": "Окна пластиковые", "detail": "ПВХ 70–76 мм, 2–3 камеры, тёплый монтаж в брус", "price": 410_000},
        {"name": "Кровля — гибкая черепица", "detail": "Стропильная система, ОСП, подкладка, черепица средний сегмент", "price": 780_000},
        {"name": "Дверь входная железная", "detail": "Утеплённая стальная дверь, монтаж в брусовой проём", "price": 75_000},
        {"name": "Проект АР/КР под клееный брус", "detail": "Конструктив с учётом усадки и узлов бруса", "price": 185_000},
    ]

    items1, total1, fz1, eng1 = _assemble(
        raw1, include_fz=include_fz, fz_key="base", include_engineering=include_engineering
    )
    items2, total2, fz2, eng2 = _assemble(
        raw2, include_fz=include_fz, fz_key="plus", include_engineering=include_engineering
    )
    items3, total3, fz3, eng3 = _assemble(
        raw3, include_fz=include_fz, fz_key="timber", include_engineering=include_engineering
    )

    suffix = _filename_suffix(include_fz, include_engineering)
    badge = _badge(include_fz, include_engineering)
    num_sfx = ""
    if include_fz:
        num_sfx += "-ФЗ"
    if include_engineering:
        num_sfx += "-ИР"

    def _notes(total: int) -> str:
        bits = [f"Ориентир на 130 м²: ~{_fmt(round(total / 130))} ₽/м²."]
        if include_fz:
            bits.append("В итого включена ФЗ.")
        if include_engineering:
            bits.append("В итого включён пакет ИР (см. приложение).")
        bits.append("Запас на непредвиденные 7–10%.")
        return " ".join(bits)

    def _included() -> list[str]:
        items = list(base["included"])
        if include_fz:
            items.append("ФЗ — фасадная отделка")
        if include_engineering:
            items.append("ИР — инженерные системы (базовый пакет) + приложение PDF")
        return items

    def _excluded() -> list[str]:
        result = []
        for x in base["excluded"]:
            if include_fz and "фасад" in x.lower():
                continue
            if include_engineering and "инженер" in x.lower():
                continue
            result.append(x)
        return result

    def _total_label() -> str:
        parts = ["тёплый контур"]
        if include_fz:
            parts.append("ФЗ")
        if include_engineering:
            parts.append("ИР")
        return "Итого: " + " + ".join(parts)

    common = {
        "include_fz": include_fz,
        "include_engineering": include_engineering,
        "included": _included(),
        "excluded": _excluded(),
        "total_label": _total_label(),
    }

    return [
        {
            **base,
            **common,
            "filename": f"KP_01_gazobeton_bazovyy{suffix}",
            "kp_number": f"КП-12/07-01{num_sfx}",
            "variant_label": f"Вариант 1 · Базовый{badge}",
            "title": "Дом из газобетонных блоков — тёплый контур (базовый)",
            "accent": "#0f4c5c",
            "accent_soft": "#e8f2f4",
            "intro": "Оптимальный старт в рамках бюджета ~7–8 млн ₽. Газобетон D400–D500.",
            "items": items1,
            "total": total1,
            "total_fmt": f"{_fmt(total1)} ₽",
            "total_note": _notes(total1),
            "fz_section": fz1,
            "engineering_section": eng1,
            "terms": [
                "Срок тёплого контура: 3,5–4,5 месяца после старта фундаментного цикла.",
                "Старт: ~через 1 месяц после договора и аванса.",
                "Оплата поэтапная по актам готовности разделов сметы.",
                "Цена действительна 14 дней.",
            ],
        },
        {
            **base,
            **common,
            "filename": f"KP_02_gazobeton_sredniy_plus{suffix}",
            "kp_number": f"КП-12/07-02{num_sfx}",
            "variant_label": f"Вариант 2 · Средний +{badge}",
            "title": "Дом из газобетонных блоков — тёплый контур (средний +)",
            "accent": "#1f4b99",
            "accent_soft": "#eaf0fa",
            "intro": "Усиленный конструктив и энергоэффективные окна/кровля.",
            "items": items2,
            "total": total2,
            "total_fmt": f"{_fmt(total2)} ₽",
            "total_note": _notes(total2),
            "fz_section": fz2,
            "engineering_section": eng2,
            "terms": [
                "Срок: 4–5 месяцев.",
                "Старт возможен в августе 2026 при быстром согласовании.",
                "Оплата поэтапная по актам.",
                "Включена расширенная документация АР/КР.",
            ],
        },
        {
            **base,
            **common,
            "filename": f"KP_03_kleenyy_brus_sredniy{suffix}",
            "kp_number": f"КП-12/07-03{num_sfx}",
            "variant_label": f"Вариант 3 · Средний{badge}",
            "title": "Дом из клееного бруса — тёплый контур (средний)",
            "accent": "#7a4e2d",
            "accent_soft": "#f6efe8",
            "intro": "Клееный брус 200×200 мм: тёплая эстетика и заводская геометрия.",
            "items": items3,
            "total": total3,
            "total_fmt": f"{_fmt(total3)} ₽",
            "total_note": _notes(total3),
            "fz_section": fz3,
            "engineering_section": eng3,
            "terms": [
                "Срок: 3–4 месяца после поставки домокомплекта (+4–6 недель на брус).",
                "Учесть технологическую паузу на усадку.",
                "Оплата поэтапная по актам.",
                "Согласовать инженерные закладные заранее.",
            ],
        },
    ]


def _save_variant_json(variant: dict[str, Any], pdf_path: Path) -> None:
    serializable = {
        k: v
        for k, v in variant.items()
        if k not in ("items", "fz_section", "engineering_section")
    }
    serializable["items"] = [
        {"name": i["name"], "detail": i["detail"], "price": i["price"]}
        for i in variant["items"]
    ]
    if variant.get("fz_section"):
        serializable["fz_section"] = {
            "name": variant["fz_section"]["name"],
            "detail": variant["fz_section"]["detail"],
            "price": variant["fz_section"]["price"],
            "scope": variant["fz_section"]["scope"],
        }
    if variant.get("engineering_section"):
        serializable["engineering_section"] = {
            "name": variant["engineering_section"]["name"],
            "detail": variant["engineering_section"]["detail"],
            "price": variant["engineering_section"]["price"],
            "scope": variant["engineering_section"]["scope"],
        }
    pdf_path.with_suffix(".json").write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_single_kp(
    variant_key: str,
    *,
    include_fz: bool = False,
    include_engineering: bool = False,
    dialog_text: str | None = None,
    output_dir: Path | None = None,
    client_name: str = DEFAULT_CLIENT_NAME,
) -> list[Path]:
    """
    Формирует один выбранный вариант КП (+ опционально приложение ИР).

    variant_key: basic | optimal | plus
    Returns: список путей к PDF (КП, и при необходимости ИР).
    """
    if variant_key not in BOT_VARIANTS:
        raise ValueError(f"Неизвестный вариант КП: {variant_key}")

    out_dir = Path(output_dir) if output_dir else KP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_client_name(client_name)

    engineering_attachment: Path | None = None
    if include_engineering:
        engineering_attachment = generate_engineering_project(
            dialog_text,
            use_ai=bool(dialog_text),
            output_path=out_dir / "attachment_IR_engineering.pdf",
            client_name=safe_name,
        )

    idx = BOT_VARIANTS[variant_key]["index"]
    variants = build_variants(
        include_fz=include_fz,
        include_engineering=include_engineering,
        client_name=safe_name,
    )
    variant = variants[idx]
    if engineering_attachment:
        variant["engineering_attachment"] = engineering_attachment.name

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"{variant['filename']}_{stamp}.pdf"
    path = generate_pdf_report(
        variant,
        output_path=out,
        template_name="kp_template.html",
        save_html=True,
    )
    _save_variant_json(variant, path)

    paths = [path]
    if engineering_attachment:
        paths.append(engineering_attachment)
    return paths


def generate_all_kp(
    include_fz: bool = False,
    include_engineering: bool = False,
    dialog_text: str | None = None,
    *,
    client_name: str = DEFAULT_CLIENT_NAME,
) -> list[Path]:
    """Создаёт PDF + HTML + JSON для всех вариантов КП в уникальной подпапке."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = KP_DIR / f"batch_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_client_name(client_name)

    engineering_attachment: Path | None = None
    if include_engineering:
        logger.info("Формирование приложения: проект инженерных решений (ИР)…")
        eng_path = generate_engineering_project(
            dialog_text,
            use_ai=bool(dialog_text),
            output_path=out_dir / "attachment_IR_engineering.pdf",
            client_name=safe_name,
        )
        engineering_attachment = eng_path
        logger.info("Приложение ИР: %s", eng_path)

    paths: list[Path] = []
    for variant in build_variants(
        include_fz=include_fz,
        include_engineering=include_engineering,
        client_name=safe_name,
    ):
        if engineering_attachment:
            variant["engineering_attachment"] = engineering_attachment.name
        out = out_dir / f"{variant['filename']}.pdf"
        path = generate_pdf_report(
            variant,
            output_path=out,
            template_name="kp_template.html",
            save_html=True,
        )
        _save_variant_json(variant, path)
        paths.append(path)

    if engineering_attachment:
        paths.append(engineering_attachment)
    return paths


def generate_kp_from_json(json_path: str | Path) -> Path:
    """Пересобирает одно КП из отредактированного JSON."""
    json_path = Path(json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items, total = _with_prices(data["items"])
    data["items"] = items
    data["total"] = total
    data["total_fmt"] = f"{_fmt(total)} ₽"
    data.setdefault("include_fz", any("ФЗ" in i["name"] for i in items))
    data.setdefault("include_engineering", any("ИР" in i["name"] for i in items))
    data.setdefault("total_label", "Итого")
    if "total_note" not in data or not data.get("total_note"):
        data["total_note"] = f"Ориентир на 130 м²: ~{_fmt(round(total / 130))} ₽/м²."

    return generate_pdf_report(
        data,
        output_path=json_path.with_suffix(".pdf"),
        template_name="kp_template.html",
        save_html=True,
    )


if __name__ == "__main__":
    for p in generate_all_kp():
        print(p)
