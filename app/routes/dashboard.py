from flask import Blueprint, render_template
from flask_login import login_required
from ..database import get_mongo_db

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    db = None
    try:
        db = get_mongo_db()
    except Exception:
        pass

    active_users = 1
    rescue_teams = 25
    ambulances   = 8
    food_packets = 3250
    recent_reports = []
    latest_alert   = None

    if db is not None:
        try:
            active_users = max(1, db.users.count_documents({}))
        except Exception:
            pass

        try:
            inventory    = db.resources.find_one({'_id': 'inventory'}) or {}
            rescue_teams = inventory.get('rescue_teams', rescue_teams)
            ambulances   = inventory.get('ambulances', ambulances)
            food_packets = inventory.get('food_packets', food_packets)
        except Exception:
            pass

        try:
            recent_reports = list(
                db.disaster_reports.find().sort('timestamp', -1).limit(5)
            )
            for r in recent_reports:
                r['_id'] = str(r['_id'])
        except Exception:
            pass

        try:
            latest_alert = db.alerts.find_one(
                {'status': 'Active'}, sort=[('created_at', -1)]
            )
            if latest_alert:
                latest_alert['_id'] = str(latest_alert['_id'])
        except Exception:
            pass

    return render_template(
        'dashboard/index.html',
        active_users=active_users,
        rescue_teams=rescue_teams,
        ambulances=ambulances,
        food_packets=food_packets,
        recent_reports=recent_reports,
        latest_alert=latest_alert,
    )
