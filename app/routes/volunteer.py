"""
Volunteer registration and management.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..whatsapp import send_whatsapp, format_volunteer_message
from ..rbac import min_role_required
from datetime import datetime
from bson import ObjectId
import threading

volunteer_bp = Blueprint('volunteer', __name__)

SKILLS = [
    'First Aid / Medical', 'Search & Rescue', 'Fire Fighting',
    'Logistics & Supply', 'Communication / Radio', 'Driving / Transport',
    'Cooking / Food Distribution', 'Counseling / Mental Health',
    'Engineering / Construction', 'IT / Tech Support',
]


@volunteer_bp.route('/volunteer', methods=['GET', 'POST'])
@login_required
def register():
    # Check if already registered
    existing = None
    try:
        db = get_mongo_db()
        existing = db.volunteers.find_one({'username': current_user.username})
        if existing:
            existing['_id'] = str(existing['_id'])
    except Exception:
        pass

    if request.method == 'POST':
        name      = request.form.get('name', '').strip()
        phone     = request.form.get('phone', '').strip()
        location  = request.form.get('location', '').strip()
        skills    = request.form.getlist('skills')
        available = request.form.get('available', 'Yes')
        notes     = request.form.get('notes', '').strip()

        if not name or not phone or not location or not skills:
            flash('All fields are required.', 'danger')
            return render_template('volunteer/register.html', skills=SKILLS, existing=existing)

        doc = {
            'username':   current_user.username,
            'name':       name,
            'phone':      phone,
            'location':   location,
            'skills':     skills,
            'available':  available,
            'notes':      notes,
            'status':     'Active',
            'registered_at': datetime.utcnow().isoformat(),
            'deployed_to': None,
        }

        try:
            db = get_mongo_db()
            if existing:
                db.volunteers.update_one({'username': current_user.username}, {'$set': doc})
                flash('Volunteer profile updated!', 'success')
            else:
                db.volunteers.insert_one(doc)
                flash('🙌 Thank you! You are now registered as a volunteer.', 'success')
            # Send WhatsApp confirmation to volunteer
            if phone:
                threading.Thread(
                    target=send_whatsapp,
                    args=(phone, format_volunteer_message(doc)),
                    daemon=True
                ).start()
        except Exception:
            flash('Could not save. Please try again.', 'danger')

        return redirect(url_for('volunteer.register'))

    return render_template('volunteer/register.html', skills=SKILLS, existing=existing)


@volunteer_bp.route('/volunteer/all')
@login_required
@min_role_required('admin')
def all_volunteers():
    volunteers = []
    stats = {'total': 0, 'available': 0, 'deployed': 0}
    try:
        db = get_mongo_db()
        volunteers = list(db.volunteers.find().sort('registered_at', -1))
        for v in volunteers:
            v['_id'] = str(v['_id'])
        stats['total']     = len(volunteers)
        stats['available'] = sum(1 for v in volunteers if v.get('available') == 'Yes')
        stats['deployed']  = sum(1 for v in volunteers if v.get('deployed_to'))
    except Exception:
        flash('Could not load volunteers.', 'warning')

    return render_template('volunteer/all.html', volunteers=volunteers, stats=stats, skills=SKILLS)


@volunteer_bp.route('/volunteer/<vol_id>/deploy', methods=['POST'])
@login_required
@min_role_required('admin')
def deploy(vol_id):
    location = request.form.get('deploy_location', '').strip()
    try:
        db = get_mongo_db()
        db.volunteers.update_one(
            {'_id': ObjectId(vol_id)},
            {'$set': {'deployed_to': location, 'available': 'No'}}
        )
        flash(f'Volunteer deployed to {location}.', 'success')
    except Exception:
        flash('Could not deploy volunteer.', 'danger')
    return redirect(url_for('volunteer.all_volunteers'))
