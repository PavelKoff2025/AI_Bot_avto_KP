import os
import json
import sqlite3
import logging
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
from werkzeug.utils import secure_filename
from file_parser import extract_text_from_file
from transcript_parser_local import parse_transcript_local as parse_transcript
from transcript_parser_local import validate_against_etalon
from etalon_score import etalon_match_score, KP_THRESHOLD, ETALON_FIELDS, FIELD_QUESTIONS
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
    deal["etalon_questions"] = match["questions"]
    deal["can_generate_kp"] = match["can_generate_kp"]
    deal["is_complete"] = match["is_complete"]
    deal["etalon_threshold"] = match["threshold"]
    return deal

@deals_bp.route('/')
@login_required
def list_deals():
    completion_status = request.args.get('completion_status', '').strip()
    status_filter = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    per_page = 20

    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM deals WHERE user_id = ? OR user_id IS NULL ORDER BY created_at DESC',
        (session['user_id'],),
    ).fetchall()
    conn.close()

    deals = [_deal_with_etalon(row) for row in rows]

    if status_filter:
        deals = [d for d in deals if (d.get('status') or '') == status_filter]

    if completion_status == 'high':
        deals = [d for d in deals if d.get('etalon_score', 0) >= KP_THRESHOLD]
    elif completion_status == 'medium':
        deals = [
            d for d in deals
            if 50 <= d.get('etalon_score', 0) < KP_THRESHOLD
        ]
    elif completion_status == 'low':
        deals = [d for d in deals if d.get('etalon_score', 0) < 50]

    if search:
        q = search.lower()
        def _match(deal: dict) -> bool:
            hay = ' '.join(
                str(deal.get(k) or '')
                for k in (
                    'client_name', 'client_phone', 'client_email',
                    'client_telegram', 'plot', 'notes',
                )
            ).lower()
            return q in hay
        deals = [d for d in deals if _match(d)]

    total = len(deals)
    ready = sum(1 for d in deals if d.get('can_generate_kp'))
    incomplete = total - ready
    avg_score = int(round(sum(d.get('etalon_score', 0) for d in deals) / total)) if total else 0
    stats = {
        'total': total,
        'ready': ready,
        'incomplete': incomplete,
        'avg_score': avg_score,
    }

    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start = (page - 1) * per_page
    page_deals = deals[start:start + per_page]

    def _page_url(p: int) -> str:
        return url_for(
            'deals.list_deals',
            completion_status=completion_status or None,
            status=status_filter or None,
            search=search or None,
            page=p,
        )

    pagination = {
        'current_page': page,
        'pages': pages,
        'has_prev': page > 1,
        'has_next': page < pages,
        'prev_url': _page_url(page - 1) if page > 1 else None,
        'next_url': _page_url(page + 1) if page < pages else None,
        'pages_range': list(range(1, pages + 1)),
        'url_for_page': _page_url,
    }

    return render_template(
        'deals/list.html',
        deals=page_deals,
        kp_threshold=KP_THRESHOLD,
        completion_status=completion_status,
        status_filter=status_filter,
        search=search,
        stats=stats,
        pagination=pagination,
    )

@deals_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_deal():
    if request.method == 'POST':
        file = request.files.get('file')
        transcript = request.form.get('transcript', '').strip()

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

        overrides = {
            'client_name': request.form.get('client_name', '').strip(),
            'client_phone': request.form.get('client_phone', '').strip(),
            'client_email': request.form.get('client_email', '').strip(),
            'client_telegram': request.form.get('client_telegram', '').strip(),
            'plot': request.form.get('plot', '').strip(),
            'budget': request.form.get('budget', '').strip(),
            'area': request.form.get('area', '').strip(),
            'material': request.form.get('material', '').strip(),
            'timeline': request.form.get('timeline', '').strip(),
            'funding_source': request.form.get('funding_source', '').strip(),
        }
        notes = request.form.get('notes', '').strip()

        try:
            validation = validate_against_etalon(transcript, overrides=overrides)
            parsed_data = validation['parsed']
            logger.info(
                "=== PARSED DATA ===\n%s\n=== ETALON %s%% missing=%s ===",
                json.dumps(parsed_data, indent=2, ensure_ascii=False),
                validation['score'],
                validation['missing'],
            )
        except Exception as e:
            logger.error(f"Ошибка парсинга/валидации: {e}")
            parsed_data = {}
            validation = etalon_match_score({})

        client_name = parsed_data.get('client_name')
        client_phone = parsed_data.get('client_phone')
        client_email = parsed_data.get('client_email')
        client_telegram = parsed_data.get('client_telegram')
        plot = parsed_data.get('plot')
        budget = parsed_data.get('budget')
        area = parsed_data.get('area')
        material = parsed_data.get('material')
        timeline = parsed_data.get('timeline')
        funding_source = parsed_data.get('funding_source')

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

        score = validation.get('score', 0)
        if not validation.get('is_complete'):
            if score >= KP_THRESHOLD:
                flash(
                    f'Сделка создана. Заполнение {score}% — КП можно генерировать, '
                    f'но лучше дособрать недостающие данные.',
                    'warning',
                )
            elif score >= 50:
                flash(
                    f'Сделка создана. Заполнение {score}% — рекомендуем дособрать данные '
                    f'до {KP_THRESHOLD}% перед генерацией КП.',
                    'warning',
                )
            else:
                flash(
                    f'Сделка создана. Заполнение {score}% — данных недостаточно для КП. '
                    f'Нужно уточнить недостающие поля.',
                    'error',
                )
            return redirect(url_for('deals.incomplete_data', deal_id=deal_id))

        flash('Сделка создана! Данные соответствуют эталону на 100%.', 'success')
        return redirect(url_for('deals.deal_detail', deal_id=deal_id))

    return render_template('deal_form.html', kp_threshold=KP_THRESHOLD)

@deals_bp.route('/<int:deal_id>')
@login_required
def deal_detail(deal_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM deals WHERE id = ?', (deal_id,)).fetchone()
    conn.close()
    if not row:
        flash('Сделка не найдена', 'error')
        return redirect(url_for('deals.list_deals'))

    deal = _deal_with_etalon(row)

    # data для шаблона: алиасы парсера + % заполнения (порог КП)
    data = {
        'name': deal.get('client_name') or '',
        'phone': deal.get('client_phone') or '',
        'email': deal.get('client_email') or '',
        'telegram': deal.get('client_telegram') or '',
        'plot_size': deal.get('plot') or '',
        'budget': deal.get('budget') or '',
        'area': deal.get('area') or '',
        'material': deal.get('material') or '',
        'deadline': deal.get('timeline') or '',
        'financing': deal.get('funding_source') or '',
        'completion_percent': deal.get('etalon_score', 0),
        'is_complete': deal.get('can_generate_kp', False),
        'missing_fields_names': deal.get('etalon_missing') or [],
    }

    field_rows = [
        {'key': 'client_name', 'label': 'Имя клиента', 'value': deal.get('client_name')},
    ]
    for key, label in ETALON_FIELDS:
        value = deal.get(key)
        text = str(value).strip() if value is not None else ''
        if text in {'', '—', '-', 'None', 'null'}:
            text = ''
        field_rows.append({'key': key, 'label': label, 'value': text or None})

    return render_template(
        'deals/view.html',
        deal=deal,
        data=data,
        field_rows=field_rows,
        kp_threshold=KP_THRESHOLD,
    )

@deals_bp.route('/<int:deal_id>/incomplete')
@login_required
def incomplete_data(deal_id):
    """Страница «Недостающие данные» для менеджера."""
    conn = get_db()
    row = conn.execute('SELECT * FROM deals WHERE id = ?', (deal_id,)).fetchone()
    conn.close()
    if not row:
        flash('Сделка не найдена', 'error')
        return redirect(url_for('deals.list_deals'))

    deal = _deal_with_etalon(row)
    match = etalon_match_score(deal)
    missing_items = [
        {
            'key': key,
            'label': label,
            'question': FIELD_QUESTIONS.get(key, ''),
        }
        for key, label in ETALON_FIELDS
        if key in match['missing_keys']
    ]

    return render_template(
        'incomplete_data.html',
        deal=deal,
        missing_items=missing_items,
        kp_threshold=KP_THRESHOLD,
        validation=match,
    )

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

        # Если менеджер дополнил транскрибацию — перепарсить и заполнить пустые поля
        if transcript and transcript != (deal['transcript'] or ''):
            try:
                reparsed = parse_transcript(transcript)
                plot = plot or reparsed.get('plot') or ''
                budget = budget or reparsed.get('budget') or ''
                area = area or reparsed.get('area') or ''
                material = material or reparsed.get('material') or ''
                timeline = timeline or reparsed.get('timeline') or ''
                funding_source = funding_source or reparsed.get('funding_source') or ''
                client_name = client_name or reparsed.get('client_name') or ''
                client_phone = client_phone or reparsed.get('client_phone') or ''
                client_email = client_email or reparsed.get('client_email') or ''
                client_telegram = client_telegram or reparsed.get('client_telegram') or ''
            except Exception as e:
                logger.error(f"Ошибка перепарсинга при редактировании: {e}")

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

        updated = conn.execute('SELECT * FROM deals WHERE id = ?', (deal_id,)).fetchone()
        conn.close()
        match = etalon_match_score(updated)

        if match['is_complete']:
            flash('Сделка обновлена! Данные соответствуют эталону на 100%.', 'success')
            return redirect(url_for('deals.deal_detail', deal_id=deal_id))
        if match['can_generate_kp']:
            flash(
                f'Сделка обновлена. Заполнение {match["score"]}% — КП можно генерировать.',
                'success',
            )
        else:
            flash(
                f'Сделка обновлена. Заполнение {match["score"]}% — ещё не хватает данных для КП.',
                'warning',
            )
        return redirect(url_for('deals.incomplete_data', deal_id=deal_id))

    return render_template(
        'deal_form.html',
        deal=deal,
        edit=True,
        kp_threshold=KP_THRESHOLD,
    )

@deals_bp.route('/<int:deal_id>/generate-kp', methods=['POST'])
@login_required
def generate_kp(deal_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM deals WHERE id = ?', (deal_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'status': 'error', 'message': 'Сделка не найдена'}), 404

    match = etalon_match_score(row)
    if not match['can_generate_kp']:
        return jsonify({
            'status': 'error',
            'message': (
                f'Недостаточно данных для КП: {match["score"]}% '
                f'(нужно ≥ {KP_THRESHOLD}%). Не хватает: {", ".join(match["missing"])}'
            ),
            'score': match['score'],
            'threshold': KP_THRESHOLD,
            'missing': match['missing'],
            'redirect': url_for('deals.incomplete_data', deal_id=deal_id),
        }), 400

    # Stub генерации — реальная сборка КП подключается отдельно
    return jsonify({
        'status': 'success',
        'message': f'Генерация КП запущена (заполнение {match["score"]}%)',
        'deal_id': deal_id,
        'score': match['score'],
    })

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
