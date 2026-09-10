from flask import Blueprint, render_template, request, flash
from flask_login import login_required
from ..database import get_mongo_db

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/alerts')
@login_required
def index():
    page     = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    alerts   = []
    total    = 0
    try:
        db    = get_mongo_db()
        total = db.alerts.count_documents({})
        alerts = list(
            db.alerts.find()
            .sort('created_at', -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        for a in alerts:
            a['_id'] = str(a['_id'])
    except Exception:
        flash('Could not load alerts from database.', 'warning')
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        'alerts/index.html',
        alerts=alerts,
        page=page,
        total_pages=total_pages,
        total=total,
    )
