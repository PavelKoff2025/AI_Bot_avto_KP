import sqlite3
import json
from datetime import datetime
from typing import Optional

class Ticket:
    """Модель для работы с таблицей tickets"""
    
    def __init__(self, id: int, text: str, channel: str, client_id: str,
                 category: str, draft_reply: str, confidence: str, 
                 escalate: bool, llm_response: str, created_at: str):
        self.id = id
        self.text = text
        self.channel = channel
        self.client_id = client_id
        self.category = category
        self.draft_reply = draft_reply
        self.confidence = confidence
        self.escalate = escalate
        self.llm_response = llm_response
        self.created_at = created_at
    
    @classmethod
    def create_table(cls):
        """Создание таблицы tickets"""
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                channel TEXT NOT NULL,
                client_id TEXT NOT NULL,
                category TEXT NOT NULL,
                draft_reply TEXT NOT NULL,
                confidence TEXT NOT NULL,
                escalate BOOLEAN NOT NULL,
                llm_response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    @classmethod
    def create(cls, text: str, channel: str, client_id: str,
               category: str, draft_reply: str, confidence: str,
               escalate: bool, llm_response: str):
        """Создание новой записи в БД"""
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tickets (text, channel, client_id, category, 
                                draft_reply, confidence, escalate, llm_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (text, channel, client_id, category, draft_reply, 
              confidence, escalate, llm_response))
        conn.commit()
        ticket_id = cursor.lastrowid
        conn.close()
        return cls.get_by_id(ticket_id)
    
    @classmethod
    def get_by_id(cls, ticket_id: int):
        """Получение тикета по ID"""
        conn = sqlite3.connect('tickets.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return cls(*row)
        return None
