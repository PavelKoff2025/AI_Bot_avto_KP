from flask import request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
from ..services.openai_service import classify_ticket
from ..models.ticket import Ticket

def register_triage_routes(app):
    """Регистрация эндпоинта /triage"""
    
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    
    @app.route('/triage', methods=['POST'])
    @limiter.limit("5 per minute", 
                   key_func=lambda: request.json.get('client_id', 'default') if request.json else 'default')
    def triage():
        """Эндпоинт для классификации обращений"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({'error': 'Invalid JSON'}), 400
            
            if 'text' not in data or not data['text']:
                return jsonify({'error': 'Missing required field: text'}), 400
            
            if 'client_id' not in data or not data['client_id']:
                return jsonify({'error': 'Missing required field: client_id'}), 400
            
            result = classify_ticket(data['text'])
            
            ticket = Ticket.create(
                text=data['text'],
                channel=data.get('channel', 'unknown'),
                client_id=data['client_id'],
                category=result['category'],
                draft_reply=result['draft_reply'],
                confidence=result['confidence'],
                escalate=result['escalate'],
                llm_response=json.dumps(result)
            )
            
            return jsonify({
                'ticket_id': ticket.id,
                'category': result['category'],
                'draft_reply': result['draft_reply'],
                'confidence': result['confidence'],
                'escalate': result['escalate']
            }), 200
            
        except Exception as e:
            print(f"Error in /triage: {e}")
            return jsonify({
                'error': 'Internal server error',
                'category': 'other',
                'draft_reply': 'Ваше обращение принято. Менеджер свяжется с вами в ближайшее время.',
                'confidence': 'low',
                'escalate': True
            }), 500
