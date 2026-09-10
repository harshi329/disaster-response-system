from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..rbac import role_required
from bson import ObjectId
from datetime import datetime

resources_bp = Blueprint('resources', __name__)

DEFAULT_INVENTORY = {
    'ambulances': 10,
    'rescue_teams': 5,
    'food_packets': 1000,
    'helicopters': 2,
}


@resources_bp.route('/resources')
@login_required
def index():
    inventory    = DEFAULT_INVENTORY.copy()
    allocations  = []
    active_reports = []
    try:
        db = get_mongo_db()
        inv = db.resources.find_one({'_id': 'inventory'})
        if inv:
            inventory = {k: v for k, v in inv.items() if k != '_id'}
        allocations = list(db.allocations.find().sort('_id', -1).limit(20))
        for a in allocations:
            a['_id'] = str(a['_id'])
        # Active reports for manual assignment (admin only)
        active_reports = list(
            db.disaster_reports.find({'status': {'$in': ['Active', 'In Progress']}})
            .sort('timestamp', -1).limit(20)
        )
        for r in active_reports:
            r['_id'] = str(r['_id'])
    except Exception:
        flash('Could not load live inventory. Showing defaults.', 'warning')

    return render_template(
        'resources/index.html',
        inventory=inventory,
        allocations=allocations,
        active_reports=active_reports,
    )


@resources_bp.route('/resources/assign', methods=['POST'])
@login_required
@role_required('admin')
def assign():
    """Admin manually assigns resources to a report."""
    report_id    = request.form.get('report_id', '').strip()
    ambulances   = int(request.form.get('ambulances', 0))
    rescue_teams = int(request.form.get('rescue_teams', 0))
    food_packets = int(request.form.get('food_packets', 0))
    helicopters  = int(request.form.get('helicopters', 0))

    if not report_id:
        flash('Please select a report.', 'danger')
        return redirect(url_for('resources.index'))

    allocated   = {}
    insufficient = []

    try:
        db        = get_mongo_db()
        inventory = db.resources.find_one({'_id': 'inventory'})
        if not inventory:
            inventory = DEFAULT_INVENTORY.copy()
            inventory['_id'] = 'inventory'
            db.resources.insert_one(inventory)

        needed = {
            'ambulances':   ambulances,
            'rescue_teams': rescue_teams,
            'food_packets': food_packets,
            'helicopters':  helicopters,
        }

        for resource, qty in needed.items():
            if qty <= 0:
                continue
            available = inventory.get(resource, 0)
            give      = min(qty, available)
            allocated[resource] = give
            if give < qty:
                insufficient.append(resource)
            if give > 0:
                db.resources.update_one(
                    {'_id': 'inventory'},
                    {'$inc': {resource: -give}}
                )

        # Log allocation
        db.allocations.insert_one({
            'report_id':   report_id,
            'severity':    'Manual',
            'allocated':   allocated,
            'insufficient': insufficient,
            'assigned_by': current_user.username,
            'assigned_at': datetime.utcnow().isoformat(),
        })

        if insufficient:
            flash(f'Partial allocation. Insufficient: {", ".join(insufficient)}.', 'warning')
        else:
            flash(f'Resources assigned successfully to report {report_id[:8]}…', 'success')

    except Exception as e:
        flash(f'Could not assign resources: {e}', 'danger')

    return redirect(url_for('resources.index'))


@resources_bp.route('/resources/restock', methods=['POST'])
@login_required
@role_required('admin')
def restock():
    """Admin restocks resource inventory."""
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
            {'$inc': updates},
            upsert=True
        )
        flash('Inventory restocked successfully.', 'success')
    except Exception as e:
        flash(f'Could not restock: {e}', 'danger')
    return redirect(url_for('resources.index'))

