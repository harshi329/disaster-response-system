"""
Broadcast — with automatic WhatsApp delivery to all registered users.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..whatsapp import send_whatsapp_bulk, format_broadcast_message
from ..rbac import role_required
from datetime import datetime
from bson import ObjectId
import threading

broadcast_bp = Blueprint('broadcast', __name__)
BROADCAST_TYPES = ['General', 'Evacuation Order', 'All Clear', 'Resource Update', 'Weather Warning', 'Curfew']


def _get_all_phones():
    try:
        db   = get_mongo_db()
        rows = db.users.find(
            {'phone': {'$exists': True, '$ne': ''}},
            {'phone': 1}
        )
        return [r['phone'] for r in rows if r.get('phone')]
    except Exception:
        return []


def _send_broadcast_whatsapp(doc: dict, phones: list):
    msg = format_broadcast_message(doc)
    send_whatsapp_bulk(phones, msg)


@broadcast_bp.route('/broadcast', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'responder')
def index():
    if request.method == 'POST':
        title    = request.form.get('title', '').strip()
        message  = request.form.get('message', '').strip()
        btype    = request.form.get('btype', 'General')
        priority = request.form.get('priority', 'Normal')
        area     = request.form.get('area', 'All Areas').strip()
        send_wa  = request.form.get('send_whatsapp', 'on')

        if not title or not message:
            flash('Title and message are required.', 'danger')
        else:
            doc = {
                'title':      title,
                'message':    message,
                'type':       btype,
                'priority':   priority,
                'area':       area,
                'sent_by':    current_user.username,
                'created_at': datetime.utcnow().isoformat(),
                'read_by':    [],
            }
            try:
                db = get_mongo_db()
                db.broadcasts.insert_one(doc.copy())
            except Exception:
                pass

            # Send WhatsApp to all registered users
            if send_wa == 'on':
                phones = _get_all_phones()
                if phones:
                    threading.Thread(
                        target=_send_broadcast_whatsapp,
                        args=(doc, phones),
                        daemon=True
                    ).start()
                    flash(f'📢 Broadcast sent! WhatsApp delivered to {len(phones)} user(s).', 'success')
                else:
                    flash('📢 Broadcast saved. No phone numbers registered for WhatsApp.', 'info')
            else:
                flash('📢 Broadcast sent to all users!', 'success')

        return redirect(url_for('broadcast.index'))

    broadcasts = []
    try:
        db = get_mongo_db()
        broadcasts = list(db.broadcasts.find().sort('created_at', -1).limit(30))
        for b in broadcasts:
            b['_id'] = str(b['_id'])
    except Exception:
        pass

    return render_template('broadcast/index.html', broadcasts=broadcasts, types=BROADCAST_TYPES)


@broadcast_bp.route('/api/broadcasts/latest')
@login_required
def latest():
    try:
        db = get_mongo_db()
        items = list(db.broadcasts.find(
            {'read_by': {'$ne': current_user.username}}
        ).sort('created_at', -1).limit(3))
        for b in items:
            b['_id'] = str(b['_id'])
        return jsonify({'broadcasts': items, 'count': len(items)})
    except Exception:
        return jsonify({'broadcasts': [], 'count': 0})


@broadcast_bp.route('/api/broadcasts/<bid>/read', methods=['POST'])
@login_required
def mark_read(bid):
    try:
        db = get_mongo_db()
        db.broadcasts.update_one(
            {'_id': ObjectId(bid)},
            {'$addToSet': {'read_by': current_user.username}}
        )
    except Exception:
        pass
    return jsonify({'ok': True})
