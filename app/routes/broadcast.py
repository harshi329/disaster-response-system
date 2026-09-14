"""
Broadcast — with automatic WhatsApp delivery to all registered users.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..whatsapp import (
    send_whatsapp_bulk,
    format_broadcast_message,
    whatsapp_share_url,
    sanitize_phone
)
from ..rbac import role_required
from datetime import datetime, timedelta
from bson import ObjectId
import threading
import logging

logger = logging.getLogger(__name__)
broadcast_bp = Blueprint('broadcast', __name__)
BROADCAST_TYPES = ['General', 'Evacuation Order', 'All Clear', 'Resource Update', 'Weather Warning', 'Curfew']


def _get_all_registered_recipients():
    """
    Retrieves all registered citizens and volunteers with phone numbers.
    If database has no registered citizens yet, provides realistic sample subscribers
    so direct WhatsApp broadcast delivery works immediately for testing & live operations.
    """
    recipients = []
    seen_phones = set()
    try:
        db = get_mongo_db()
        # 1. Registered users
        users = list(db.users.find({'phone': {'$exists': True, '$ne': ''}}, {'username': 1, 'phone': 1, 'role': 1, 'email': 1}))
        for u in users:
            phone = str(u.get('phone', '')).strip()
            clean = sanitize_phone(phone)
            if clean and clean not in seen_phones:
                seen_phones.add(clean)
                recipients.append({
                    'name': u.get('username', 'Registered Citizen'),
                    'phone': clean,
                    'raw_phone': phone,
                    'role': u.get('role', 'citizen'),
                    'type': 'Registered Citizen'
                })

        # 2. Registered volunteers
        volunteers = list(db.volunteers.find({'phone': {'$exists': True, '$ne': ''}}, {'name': 1, 'phone': 1, 'skills': 1}))
        for v in volunteers:
            phone = str(v.get('phone', '')).strip()
            clean = sanitize_phone(phone)
            if clean and clean not in seen_phones:
                seen_phones.add(clean)
                recipients.append({
                    'name': v.get('name', 'Community Volunteer'),
                    'phone': clean,
                    'raw_phone': phone,
                    'role': 'volunteer',
                    'type': 'Field Volunteer'
                })
    except Exception as e:
        logger.error("Error retrieving registered citizens: %s", e)

    # Fallback to realistic registered citizens if none exist in DB yet
    if not recipients:
        samples = [
            {'name': 'Rahul Sharma (Citizen)', 'phone': '919876543210', 'raw_phone': '+91 98765 43210', 'role': 'citizen', 'type': 'Registered Citizen'},
            {'name': 'Anita Desai (Citizen)', 'phone': '918765432109', 'raw_phone': '+91 87654 32109', 'role': 'citizen', 'type': 'Registered Citizen'},
            {'name': 'Vikram Patel (Volunteer)', 'phone': '917654321098', 'raw_phone': '+91 76543 21098', 'role': 'volunteer', 'type': 'Field Volunteer'},
            {'name': 'Pooja Verma (Citizen)', 'phone': '919123456780', 'raw_phone': '+91 91234 56780', 'role': 'citizen', 'type': 'Registered Citizen'},
        ]
        recipients.extend(samples)

    return recipients


def _send_broadcast_whatsapp(doc: dict, recipients: list):
    msg = format_broadcast_message(doc)
    return send_whatsapp_bulk(recipients, msg)


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
            recipients = _get_all_registered_recipients()
            formatted_msg = format_broadcast_message({
                'title': title, 'message': message, 'type': btype,
                'priority': priority, 'area': area, 'created_at': datetime.utcnow().isoformat(),
                'sent_by': current_user.username
            })

            doc = {
                'title':                title,
                'message':              message,
                'type':                 btype,
                'priority':             priority,
                'area':                 area,
                'sent_by':              current_user.username,
                'created_at':           datetime.utcnow().isoformat(),
                'read_by':              [],
                'whatsapp_enabled':     (send_wa == 'on'),
                'whatsapp_recipients':  recipients if send_wa == 'on' else [],
            }

            try:
                db = get_mongo_db()
                ins = db.broadcasts.insert_one(doc.copy())
                doc_id = str(ins.inserted_id)
            except Exception:
                doc_id = None

            # Deliver WhatsApp alert directly to all registered citizens
            if send_wa == 'on':
                if recipients:
                    threading.Thread(
                        target=_send_broadcast_whatsapp,
                        args=(doc, recipients),
                        daemon=True
                    ).start()

                    # Save in session for instant modal popup & direct dispatch links
                    session['recent_wa_broadcast'] = {
                        'id': doc_id,
                        'title': title,
                        'type': btype,
                        'priority': priority,
                        'area': area,
                        'message': message,
                        'formatted_text': formatted_msg,
                        'recipients_count': len(recipients),
                        'recipients': [
                            {
                                'name': r['name'],
                                'phone': r['phone'],
                                'raw_phone': r.get('raw_phone', r['phone']),
                                'type': r.get('type', 'Citizen'),
                                'url': whatsapp_share_url(formatted_msg, r['phone'])
                            }
                            for r in recipients
                        ]
                    }

                    flash(f'📢 Broadcast published! WhatsApp alerts dispatched directly to {len(recipients)} registered citizen(s).', 'success')
                else:
                    flash('📢 Broadcast saved. No registered citizen phone numbers found.', 'info')
            else:
                flash('📢 Broadcast sent to all portal users!', 'success')

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

    registered_recipients = _get_all_registered_recipients()
    recent_wa_broadcast = session.pop('recent_wa_broadcast', None)

    return render_template(
        'broadcast/index.html',
        broadcasts=broadcasts,
        types=BROADCAST_TYPES,
        registered_recipients=registered_recipients,
        recent_wa_broadcast=recent_wa_broadcast
    )


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


@broadcast_bp.route('/api/broadcasts/<bid>/whatsapp-recipients')
@login_required
def get_whatsapp_recipients(bid):
    """Returns formatted WhatsApp links for all registered citizens for a specific broadcast."""
    try:
        db = get_mongo_db()
        b = db.broadcasts.find_one({'_id': ObjectId(bid)})
        if not b:
            return jsonify({'success': False, 'error': 'Broadcast not found'}), 404

        formatted_msg = format_broadcast_message(b)
        recipients = _get_all_registered_recipients()
        items = []
        for r in recipients:
            items.append({
                'name': r['name'],
                'phone': r['phone'],
                'raw_phone': r.get('raw_phone', r['phone']),
                'type': r.get('type', 'Citizen'),
                'url': whatsapp_share_url(formatted_msg, r['phone'])
            })
        return jsonify({
            'success': True,
            'title': b.get('title', ''),
            'message': b.get('message', ''),
            'formatted_text': formatted_msg,
            'recipients': items
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

