"""
Broadcast — with automatic WhatsApp delivery to all registered users.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..whatsapp import send_whatsapp_bulk, format_broadcast_message
from ..rbac import role_required
from datetime import datetime, timedelta
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


def get_fresh_sample_broadcasts():
    now = datetime.utcnow()
    return [
        {
            'title': '🚨 URGENT EVACUATION: Yamuna River Bank & Low-Lying Sectors',
            'message': 'Water levels have crossed the danger mark (205.53m) following upstream reservoir release. All residents in low-lying riverside communities must evacuate immediately to designated relief shelters: Municipal Community Center #4 and Govt. Senior Secondary School. Emergency rescue teams and transport buses are stationed at River Road checkpost. Call 108 or tap SOS in this app for immediate assistance.',
            'type': 'Evacuation Order',
            'priority': 'Critical',
            'area': 'River Road & Low-Lying Riverside Sectors',
            'sent_by': 'Admin (Disaster Management Authority)',
            'created_at': (now - timedelta(minutes=5)).isoformat(),
            'read_by': [],
        },
        {
            'title': '⚠️ RED ALERT: Heavy Rainfall & Flash Flood Advisory (Next 48 Hours)',
            'message': 'IMD has issued a Red Alert predicting 120-180mm torrential rainfall and flash flood risks over the next 48 hours. Citizens are strongly advised to remain indoors, avoid electric poles and waterlogged underpasses, keep power banks charged, and stock up on clean drinking water and essential medications.',
            'type': 'Weather Warning',
            'priority': 'Urgent',
            'area': 'All Metropolitan Sectors & NCR Region',
            'sent_by': 'Admin (Disaster Management Authority)',
            'created_at': (now - timedelta(minutes=25)).isoformat(),
            'read_by': [],
        },
        {
            'title': '📦 Relief Camps Active: Free Food Packets, Clean Water & Medical Aid',
            'message': 'Emergency relief distribution is now actively operating at 3 major hubs: Central School Ground (Camp A), Sector 12 Sports Complex (Camp B), and District Red Cross Center (Camp C). Free meal packets, bottled drinking water, baby food, blankets, and 24/7 medical triage booths are fully stocked and available for all affected citizens.',
            'type': 'Resource Update',
            'priority': 'Urgent',
            'area': 'Relief Shelters (Sectors 4, 7 & 12)',
            'sent_by': 'Admin (Civil Supplies & Relief Dept)',
            'created_at': (now - timedelta(hours=1, minutes=10)).isoformat(),
            'read_by': [],
        },
        {
            'title': '🚁 Search & Rescue Operations Active: Air Support & Boats Deployed',
            'message': 'Combined air-and-boat rescue squads are deployed across submerged neighborhoods. If trapped on rooftops, display bright clothing or flash your phone light skyward. Keep mobile phones in battery saver mode and submit an SOS alert in this app for direct GPS rescue dispatch.',
            'type': 'General',
            'priority': 'Critical',
            'area': 'Hill Zone & North District Flood Zones',
            'sent_by': 'Admin (Emergency Operations Center)',
            'created_at': (now - timedelta(hours=2, minutes=45)).isoformat(),
            'read_by': [],
        },
        {
            'title': '🛑 Traffic & Travel Advisory: Arterial Roads Closed for Emergency Vehicles',
            'message': 'All arterial underpasses and bridges along the river corridor are closed to civilian traffic to facilitate unrestricted movement for ambulances, fire engines, and rescue convoys. Please do not venture into flooded streets and yield immediately to emergency sirens.',
            'type': 'Curfew',
            'priority': 'Normal',
            'area': 'Central Highway & River Road Corridors',
            'sent_by': 'Admin (Traffic & Police Control)',
            'created_at': (now - timedelta(hours=4, minutes=15)).isoformat(),
            'read_by': [],
        },
    ]


SAMPLE_BROADCASTS = get_fresh_sample_broadcasts()


@broadcast_bp.route('/broadcast', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        if current_user.role != 'admin':
            flash('Only administrators can issue public broadcasts.', 'danger')
            return redirect(url_for('broadcast.index'))

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
        # If no broadcasts exist, seed realistic sample emergency broadcasts for citizens
        if db.broadcasts.count_documents({}) == 0:
            for s in get_fresh_sample_broadcasts():
                db.broadcasts.insert_one(s)

        broadcasts = list(db.broadcasts.find().sort('created_at', -1).limit(40))
        for b in broadcasts:
            b['_id'] = str(b['_id'])
    except Exception:
        pass

    return render_template('broadcast/index.html', broadcasts=broadcasts, types=BROADCAST_TYPES)


@broadcast_bp.route('/broadcast/seed-samples', methods=['POST'])
@login_required
@role_required('admin')
def seed_samples():
    """Admin action to add or restore sample emergency broadcasts."""
    try:
        db = get_mongo_db()
        for s in get_fresh_sample_broadcasts():
            db.broadcasts.insert_one(s)
        flash('Sample emergency broadcasts successfully added for citizens!', 'success')
    except Exception as e:
        flash(f'Could not add sample broadcasts: {e}', 'danger')
    return redirect(url_for('broadcast.index'))


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
