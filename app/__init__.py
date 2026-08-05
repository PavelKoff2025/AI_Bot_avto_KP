from flask import Flask
from .config import Config
from .models.ticket import Ticket
from .routes.triage import register_triage_routes

def create_app():
    """Фабрика приложения Flask"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Создаём таблицу в БД
    Ticket.create_table()
    
    # Регистрируем маршруты
    register_triage_routes(app)
    
    return app
