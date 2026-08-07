import os
import re
import PyPDF2
import docx

def extract_text_from_file(file_path):
    """
    Извлекает текст из файла .txt, .doc, .docx, .pdf
    """
    if not os.path.exists(file_path):
        return None
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    elif ext == '.docx':
        doc = docx.Document(file_path)
        return '\n'.join([para.text for para in doc.paragraphs])
    
    elif ext == '.pdf':
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ''
            for page in reader.pages:
                text += page.extract_text() or ''
            return text
    
    elif ext == '.doc':
        # .doc — сложный формат, можно попробовать через анти-ворд или конвертацию
        # Пока заглушка
        return None
    
    else:
        return None
