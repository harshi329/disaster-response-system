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
            'email':      getattr(current_user, 'email', ''),
            'name':       name,
            'phone':      phone,
            'location':   location,
            'skills':     skills,
            'available':  available,
            'notes':      notes,
            'status':     'Available' if available == 'Yes' else 'Unavailable',
            'registered_at': datetime.utcnow().isoformat(),
            'assigned_to': None,
            'deployed_to': None,
        }

        try:
            db = get_mongo_db()
            if existing:
                db.volunteers.update_one({'username': current_user.username}, {'$set': doc})
                flash('Volunteer profile updated!', 'success')
            else:
                db.volunteers.insert_one(doc)
                flash('🙌 Thank you! You are now registered as an official volunteer.', 'success')

            # Automatically upgrade user role to volunteer if currently citizen
            if current_user.role == 'citizen':
                db.users.update_one({'username': current_user.username}, {'$set': {'role': 'volunteer'}})
                current_user.role = 'volunteer'

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
def all_volunteers():
    # Only registered volunteers and admin can view contact details for coordination
    if current_user.role not in ('volunteer', 'admin'):
        flash('Please register as a volunteer to access the Volunteer Coordination Directory.', 'info')
        return redirect(url_for('volunteer.register'))

    volunteers = []
    stats = {'total': 0, 'available': 0, 'assigned': 0}
    try:
        db = get_mongo_db()
        volunteers = list(db.volunteers.find().sort('registered_at', -1))
        for v in volunteers:
            v['_id'] = str(v['_id'])
            # Normalize assignment field
            if not v.get('assigned_to') and v.get('deployed_to'):
                v['assigned_to'] = v.get('deployed_to')
        stats['total']     = len(volunteers)
        stats['available'] = sum(1 for v in volunteers if v.get('available') == 'Yes')
        stats['assigned']  = sum(1 for v in volunteers if v.get('assigned_to') or v.get('deployed_to'))
    except Exception:
        flash('Could not load volunteers.', 'warning')

    return render_template('volunteer/all.html', volunteers=volunteers, stats=stats, skills=SKILLS)


@volunteer_bp.route('/volunteer/<vol_id>/assign', methods=['POST'])
@login_required
@min_role_required('admin')
def assign(vol_id):
    """Admin assigns volunteer to an area or task."""
    location = request.form.get('deploy_location', '').strip() or request.form.get('assign_location', '').strip()
    try:
        db = get_mongo_db()
        vol = db.volunteers.find_one({'_id': ObjectId(vol_id)})
        vol_name = vol.get('name', 'Volunteer') if vol else 'Volunteer'
        db.volunteers.update_one(
            {'_id': ObjectId(vol_id)},
            {'$set': {
                'assigned_to': location,
                'deployed_to': location,
                'available': 'No',
                'status': 'Assigned',
                'assigned_at': datetime.utcnow().isoformat(),
            }}
        )
        flash(f'Volunteer {vol_name} has been assigned to: {location}.', 'success')
        # Notify volunteer via WhatsApp if phone available
        phone = vol.get('phone') if vol else None
        if phone:
            msg = f"📢 *Volunteer Task Assignment*\nHello {vol_name}, you have been assigned to: *{location}*.\nPlease report immediately. When done, update your status."
            threading.Thread(target=send_whatsapp, args=(phone, msg), daemon=True).start()
    except Exception as e:
        flash(f'Could not assign volunteer: {e}', 'danger')
    return redirect(url_for('volunteer.all_volunteers'))


@volunteer_bp.route('/volunteer/<vol_id>/deploy', methods=['POST'])
@login_required
@min_role_required('admin')
def deploy(vol_id):
    # Backward compatibility redirect to assign
    return assign(vol_id)


@volunteer_bp.route('/volunteer/<vol_id>/complete', methods=['POST'])
@login_required
def complete_work(vol_id):
    """Mark volunteer task as completed, releasing them back to Free / Available."""
    try:
        db = get_mongo_db()
        vol = db.volunteers.find_one({'_id': ObjectId(vol_id)})
        if not vol:
            flash('Volunteer not found.', 'danger')
            return redirect(url_for('volunteer.all_volunteers'))

        # Only admin or the assigned volunteer themselves can mark work completed
        if current_user.role != 'admin' and vol.get('username') != current_user.username:
            flash('You can only mark your own assignments as completed.', 'danger')
            return redirect(url_for('volunteer.all_volunteers'))

        vol_name = vol.get('name', 'Volunteer')
        prev_loc = vol.get('assigned_to') or vol.get('deployed_to') or 'task'

        db.volunteers.update_one(
            {'_id': ObjectId(vol_id)},
            {'$set': {
                'assigned_to': None,
                'deployed_to': None,
                'available': 'Yes',
                'status': 'Available',
                'completed_at': datetime.utcnow().isoformat(),
            }}
        )
        flash(f'✅ Work at {prev_loc} completed successfully! {vol_name} is now Free & Available for new assignments.', 'success')

        # Send WhatsApp confirmation to volunteer
        phone = vol.get('phone')
        if phone:
            msg = f"✅ *Task Completed*\nThank you {vol_name}! Your mission at {prev_loc} is marked completed.\nYour status is now *Free & Available*."
            threading.Thread(target=send_whatsapp, args=(phone, msg), daemon=True).start()
    except Exception as e:
        flash(f'Could not update volunteer status: {e}', 'danger')

    return redirect(url_for('volunteer.all_volunteers'))
