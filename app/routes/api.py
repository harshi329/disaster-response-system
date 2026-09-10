"""
REST API endpoints for real-time dashboard updates.
"""
from flask import Blueprint, jsonify
from flask_login import login_required
from ..database import get_mongo_db

api_bp = Blueprint('api', __name__)


@api_bp.route('/stats')
@login_required
def stats():
    data = {'rescue_teams': 25, 'ambulances': 8, 'food_packets': 3250, 'active_reports': 0, 'active_users': 1}
    try:
        db = get_mongo_db()
        inv = db.resources.find_one({'_id': 'inventory'}) or {}
        data['rescue_teams'] = inv.get('rescue_teams', data['rescue_teams'])
        data['ambulances']   = inv.get('ambulances', data['ambulances'])
        data['food_packets'] = inv.get('food_packets', data['food_packets'])
        data['active_reports'] = db.disaster_reports.count_documents({'status': 'Active'})
        data['active_users']   = max(1, db.users.count_documents({}))
    except Exception:
        pass
    return jsonify(data)


@api_bp.route('/alerts/latest')
@login_required
def latest_alert():
    try:
        db = get_mongo_db()
        alert = db.alerts.find_one({'status': 'Active'}, sort=[('created_at', -1)])
        if alert:
            alert['_id'] = str(alert['_id'])
            return jsonify(alert)
    except Exception:
        pass
    return jsonify({})


@api_bp.route('/reports/recent')
@login_required
def recent_reports():
    reports = []
    try:
        db = get_mongo_db()
        reports = list(db.disaster_reports.find().sort('timestamp', -1).limit(5))
        for r in reports:
            r['_id'] = str(r['_id'])
    except Exception:
        pass
    return jsonify(reports)
