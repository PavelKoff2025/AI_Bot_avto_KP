import re


def parse_transcript_local(text: str) -> dict:
    """
    Парсит транскрибацию с помощью регулярных выражений (без OpenAI)
    по полям эталонного протокола.
    """
    result = {
        "client_name": None,
        "client_phone": None,
        "client_email": None,
        "client_telegram": None,
        "plot": None,
        "budget": None,
        "area": None,
        "material": None,
        "timeline": None,
        "work_scope": None,
        "funding_source": None,
        "status": "new",
    }

    # Имя клиента
    name_match = re.search(
        r'(?:Потенциальный заказчик|Клиент|Заказчик)\s*[:—\-]\s*([А-ЯЁа-яёA-Za-z]+)',
        text,
        re.IGNORECASE,
    )
    if name_match:
        result["client_name"] = name_match.group(1).strip()

    # Телефон
    phone_match = re.search(
        r'(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        text,
    )
    if phone_match:
        result["client_phone"] = phone_match.group(0).strip()

    # Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        result["client_email"] = email_match.group(0).strip()

    # Telegram
    tg_match = re.search(
        r'(?:Telegram|Телеграм)\s*[:—\-]?\s*(@?[A-Za-z0-9_]{3,})',
        text,
        re.IGNORECASE,
    )
    if not tg_match:
        tg_match = re.search(r'(?<!\w)(@[A-Za-z0-9_]{3,})', text)
    if tg_match:
        handle = tg_match.group(1).strip()
        if not handle.startswith('@'):
            handle = '@' + handle
        result["client_telegram"] = handle

    # Участок
    plot_match = re.search(
        r'(?:Участок|Земельный участок)\s*[:—\-]?\s*([^\n]{5,80})',
        text,
        re.IGNORECASE,
    )
    if plot_match:
        result["plot"] = plot_match.group(1).strip(" .;")
    else:
        plot_match = re.search(
            r'(\d+[–\-]?\d*\s*соток[^\n.,;]{0,50})',
            text,
            re.IGNORECASE,
        )
        if plot_match:
            result["plot"] = plot_match.group(1).strip()

    # Бюджет
    budget_match = re.search(r'(\d+[–\-]?\d*\s*млн\s*руб\.?)', text, re.IGNORECASE)
    if budget_match:
        result["budget"] = budget_match.group(1).strip()

    # Площадь
    area_match = re.search(r'(\d{2,3}[–\-]\d{2,3}\s*м²?)', text)
    if not area_match:
        area_match = re.search(r'(\d{2,3}\s*м²?)', text)
    if area_match:
        result["area"] = area_match.group(1).strip()

    # Материал стен
    material_keywords = ['газобетон', 'кирпич', 'брус', 'пеноблок', 'керамоблок']
    for material in material_keywords:
        if material in text.lower():
            result["material"] = material
            break

    # Сроки
    months = [
        'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
        'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
    ]
    found_months = [m for m in months if m in text.lower()]
    if found_months:
        result["timeline"] = found_months[-1]
        year_match = re.search(r'(20\d{2})', text)
        if year_match:
            result["timeline"] = f"{result['timeline']} {year_match.group(1)}"
    else:
        for season in ['весна', 'лето', 'осень', 'зима']:
            if season in text.lower():
                result["timeline"] = season
                break

    # Финансирование
    if 'ипотек' in text.lower():
        result["funding_source"] = "ипотека"
    elif 'маткапитал' in text.lower():
        result["funding_source"] = "маткапитал"
    elif 'свои' in text.lower() or 'накопл' in text.lower():
        result["funding_source"] = "собственные средства"

    return result
