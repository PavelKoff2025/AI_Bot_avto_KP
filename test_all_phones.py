# test_all_phones.py
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "web_app"))

from transcript_parser_local import TranscriptParser

parser = TranscriptParser()

test_cases = [
    ("+7 (916) 123-45-67", "+79161234567"),
    ("8-903-555-12-34", "+79035551234"),
    ("+7 926 777-88-99", "+79267778899"),
    ("89161234567", "+79161234567"),  # 🔥 ИСПРАВЛЕНО
    ("+79031234567", "+79031234567"),
    ("8(903)555-12-34", "+79035551234"),
    ("89035551234", "+79035551234"),
    ("79161234567", "+79161234567"),
    ("9035551234", "+79035551234"),
    ("+7 903 555 12 34", "+79035551234"),
    ("8 903 555-12-34", "+79035551234"),
]

print("🧪 ТЕСТИРОВАНИЕ ПАРСЕРА ТЕЛЕФОНОВ")
print("=" * 60)

passed = 0
failed = 0

for input_phone, expected in test_cases:
    result = parser.parse_text(f"Телефон: {input_phone}")
    output = result.get('phone', '')
    
    # Очищаем ожидаемый результат от лишних символов
    expected_clean = re.sub(r'[^\d+]', '', expected)
    
    if output == expected_clean:
        status = "✅ OK"
        passed += 1
    else:
        status = f"❌ FAIL (ожидал: {expected_clean}, получил: {output})"
        failed += 1
    
    print(f"{status} | Вход: {input_phone:20} → Выход: {output}")

print("=" * 60)
print(f"Результат: {passed} из {len(test_cases)} пройдено")
if failed > 0:
    print(f"❌ {failed} тестов не пройдены")
else:
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
