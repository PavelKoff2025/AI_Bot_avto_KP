import json
import openai
import os

# Загружаем ключ из .env
from dotenv import load_dotenv
load_dotenv()

openai.api_key = os.getenv('OPENAI_API_KEY')

PARSER_PROMPT = """
Ты — ассистент отдела продаж строительной компании. Твоя задача — проанализировать протокол телефонного разговора и извлечь структурированные данные.

Извлеки следующие поля из текста:
1. client_name — имя клиента
2. client_phone — телефон (если есть, иначе null)
3. client_email — email (если есть, иначе null)
4. client_telegram — Telegram (если есть, иначе null)
5. budget — бюджет (сумма, например "7-8 млн руб.")
6. area — площадь дома (например "120-140 м2")
7. material — материал стен (газобетон, кирпич, брус, если указан)
8. timeline — сроки старта (например "август 2026")
9. work_scope — объём работ (что нужно от компании)
10. funding_source — источник финансирования (свои/ипотека/маткапитал)
11. status — статус сделки ("new", если нет других данных)

Верни ТОЛЬКО JSON в формате:
{
  "client_name": "...",
  "client_phone": "...",
  "client_email": "...",
  "client_telegram": "...",
  "budget": "...",
  "area": "...",
  "material": "...",
  "timeline": "...",
  "work_scope": "...",
  "funding_source": "...",
  "status": "new"
}

Если поле не найдено, поставь null.
"""

def parse_transcript(text: str) -> dict:
    """
    Парсит транскрибацию через OpenAI и возвращает структурированные данные
    """
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from utils.ai_processor import get_openai_client

        client = get_openai_client()
        
        response = client.chat.completions.create(
            model=os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo'),
            messages=[
                {"role": "system", "content": PARSER_PROMPT},
                {"role": "user", "content": text[:4000]}  # ограничиваем длину
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        return {
            "client_name": None,
            "client_phone": None,
            "client_email": None,
            "client_telegram": None,
            "budget": None,
            "area": None,
            "material": None,
            "timeline": None,
            "work_scope": None,
            "funding_source": None,
            "status": "new"
        }
