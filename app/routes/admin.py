"""
Admin panel — user management (list, change role, delete).
Only accessible to users with role == 'admin'.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..rbac import role_required
from bson import ObjectId

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ROLES = ['citizen', 'volunteer', 'admin']


@admin_bp.route('/users')
@login_required
@role_required('admin')
def users():
    user_list = []
    try:
        db = get_mongo_db()
        user_list = list(db.users.find({}, {'password': 0}).sort('username', 1))
        for u in user_list:
            u['_id'] = str(u['_id'])
    except Exception:
        flash('Could not load users.', 'warning')
    return render_template('admin/users.html', users=user_list, roles=ROLES)


@admin_bp.route('/users/<user_id>/role', methods=['POST'])
@login_required
@role_required('admin')
def change_role(user_id):
    new_role = request.form.get('role', 'citizen')
    if new_role not in ROLES:
        flash('Invalid role.', 'danger')
        return redirect(url_for('admin.users'))

    # Prevent admin from demoting themselves
    if user_id == str(current_user.id):
        flash('You cannot change your own role.', 'warning')
        return redirect(url_for('admin.users'))

    try:
        db = get_mongo_db()
        db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'role': new_role}})
        flash(f'Role updated to {new_role}.', 'success')
    except Exception:
        flash('Could not update role.', 'danger')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    # Prevent admin from deleting themselves
    if user_id == str(current_user.id):
        flash('You cannot delete your own account.', 'warning')
        return redirect(url_for('admin.users'))

    try:
        db = get_mongo_db()
        db.users.delete_one({'_id': ObjectId(user_id)})
        flash('User deleted.', 'success')
    except Exception:
        flash('Could not delete user.', 'danger')

    return redirect(url_for('admin.users'))


@admin_bp.route('/resources', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_resources():
    """Admin can restock / edit resource inventory."""
    DEFAULT = {'ambulances': 10, 'rescue_teams': 5, 'food_packets': 1000, 'helicopters': 2}

    if request.method == 'POST':
        try:
            db = get_mongo_db()
            updates = {
                'ambulances':   int(request.form.get('ambulances', 0)),
                'rescue_teams': int(request.form.get('rescue_teams', 0)),
                'food_packets': int(request.form.get('food_packets', 0)),
                'helicopters':  int(request.form.get('helicopters', 0)),
            }
            db.resources.update_one(
                {'_id': 'inventory'},
                {'$set': updates},
                upsert=True
            )
            flash('Resource inventory updated.', 'success')
        except Exception as e:
            flash(f'Could not update inventory: {e}', 'danger')
        return redirect(url_for('admin.manage_resources'))

    inventory = DEFAULT.copy()
    try:
        db = get_mongo_db()
        inv = db.resources.find_one({'_id': 'inventory'})
        if inv:
            inventory = {k: v for k, v in inv.items() if k != '_id'}
    except Exception:
        flash('Could not load inventory. Showing defaults.', 'warning')

    return render_template('admin/resources.html', inventory=inventory)
