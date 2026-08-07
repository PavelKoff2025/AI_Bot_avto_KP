import os
import json
import sqlite3
import logging
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
from datetime import datetime
import hashlib
from werkzeug.utils import secure_filename
from file_parser import extract_text_from_file
from transcript_parser_local import parse_transcript_local as parse_transcript
from etalon_score import etalon_match_score
from db_utils import connect_db

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

deals_bp = Blueprint('deals', __name__, url_prefix='/deals')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    return connect_db('deals.db')

def _deal_with_etalon(row: sqlite3.Row) -> dict:
    deal = dict(row)
    match = etalon_match_score(deal)
    deal["etalon_score"] = match["score"]
    deal["etalon_grade"] = match["grade"]
    deal["etalon_missing"] = match["missing"]
    return deal

@deals_bp.route('/')
@login_required
def list_deals():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM deals WHERE user_id = ? OR user_id IS NULL ORDER BY created_at DESC',
        (session['user_id'],),
    ).fetchall()
    conn.close()
    deals = [_deal_with_etalon(row) for row in rows]
    return render_template('deals_list.html', deals=deals)

@deals_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_deal():
    if request.method == 'POST':
        file = request.files.get('file')
        transcript = request.form.get('transcript', '').strip()
        parsed_data = {}

        if file and file.filename:
            filename = secure_filename(file.filename)
            upload_dir = '/tmp/uploads'
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)
            transcript = extract_text_from_file(file_path) or transcript

        if not transcript:
            flash('Введите текст транскрибации или загрузите файл', 'error')
            return redirect(request.url)

        try:
            parsed_data = parse_transcript(transcript)
            logger.info(f"=== PARSED DATA ===\n{json.dumps(parsed_data, indent=2, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            parsed_data = {}

        client_name = request.form.get('client_name', '').strip() or parsed_data.get('client_name')
        client_phone = request.form.get('client_phone', '').strip() or parsed_data.get('client_phone')
        client_email = request.form.get('client_email', '').strip() or parsed_data.get('client_email')
        client_telegram = request.form.get('client_telegram', '').strip() or parsed_data.get('client_telegram')
        notes = request.form.get('notes', '').strip()

        plot = parsed_data.get('plot')
        budget = parsed_data.get('budget')
        area = parsed_data.get('area')
        material = parsed_data.get('material')
        timeline = parsed_data.get('timeline')
        funding_source = parsed_data.get('funding_source')

        logger.info(
            "Сохраняем: client_name=%s, plot=%s, budget=%s, area=%s, material=%s",
            client_name, plot, budget, area, material,
        )

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO deals (
                client_name, client_phone, client_email, client_telegram,
                transcript, notes, user_id, status,
                plot, budget, area, material, timeline, funding_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            client_name, client_phone, client_email, client_telegram,
            transcript, notes, session['user_id'], 'new',
            plot, budget, area, material, timeline, funding_source
        ))
        deal_id = cursor.lastrowid
        conn.commit()
        conn.close()

        flash('Сделка создана!', 'success')
        return redirect(url_for('deals.deal_detail', deal_id=deal_id))

    return render_template('deal_form.html')

@deals_bp.route('/<int:deal_id>')
@login_required
def deal_detail(deal_id):
    conn = get_db()
    deal = conn.execute('SELECT * FROM deals WHERE id = ?', (deal_id,)).fetchone()
    conn.close()
    if not deal:
        flash('Сделка не найдена', 'error')
        return redirect(url_for('deals.list_deals'))
    return render_template('deal_detail.html', deal=deal)

@deals_bp.route('/<int:deal_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_deal(deal_id):
    conn = get_db()
    deal = conn.execute('SELECT * FROM deals WHERE id = ?', (deal_id,)).fetchone()
    conn.close()
    if not deal:
        flash('Сделка не найдена', 'error')
        return redirect(url_for('deals.list_deals'))
    if request.method == 'POST':
        client_name = request.form.get('client_name', '').strip()
        client_phone = request.form.get('client_phone', '').strip()
        client_email = request.form.get('client_email', '').strip()
        client_telegram = request.form.get('client_telegram', '').strip()
        transcript = request.form.get('transcript', '').strip()
        notes = request.form.get('notes', '').strip()
        status = request.form.get('status', 'new')
        budget = request.form.get('budget', '').strip()
        area = request.form.get('area', '').strip()
        material = request.form.get('material', '').strip()
        timeline = request.form.get('timeline', '').strip()
        funding_source = request.form.get('funding_source', '').strip()
        plot = request.form.get('plot', '').strip()
        conn = get_db()
        conn.execute('''
            UPDATE deals SET
                client_name = ?, client_phone = ?, client_email = ?, client_telegram = ?,
                transcript = ?, notes = ?, status = ?,
                plot = ?, budget = ?, area = ?, material = ?, timeline = ?, funding_source = ?
            WHERE id = ?
        ''', (
            client_name, client_phone, client_email, client_telegram,
            transcript, notes, status,
            plot, budget, area, material, timeline, funding_source,
            deal_id
        ))
        conn.commit()
        conn.close()
        flash('Сделка обновлена!', 'success')
        return redirect(url_for('deals.deal_detail', deal_id=deal_id))
    return render_template('deal_form.html', deal=deal, edit=True)

@deals_bp.route('/<int:deal_id>/generate-kp', methods=['POST'])
@login_required
def generate_kp(deal_id):
    return jsonify({'status': 'success', 'message': 'Генерация КП запущена', 'deal_id': deal_id})

@deals_bp.route('/<int:deal_id>/status', methods=['POST'])
@login_required
def update_status(deal_id):
    status = request.json.get('status')
    if not status:
        return jsonify({'error': 'Статус не указан'}), 400
    conn = get_db()
    conn.execute('UPDATE deals SET status = ? WHERE id = ?', (status, deal_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})
