from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from ..database import get_mongo_db
from ..agents.analysis_agent import analyze_disaster
from ..agents.resource_agent import allocate_resources
from ..agents.route_agent import optimize_route
from ..agents.alert_agent import generate_alert
from ..rbac import min_role_required
from datetime import datetime
from bson import ObjectId

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/reports')
@login_required
def index():
    page     = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    reports  = []
    total    = 0
    try:
        db      = get_mongo_db()
        total   = db.disaster_reports.count_documents({})
        reports = list(
            db.disaster_reports.find()
            .sort('timestamp', -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        for r in reports:
            r['_id'] = str(r['_id'])
    except Exception:
        flash('Could not connect to database.', 'warning')
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        'reports/index.html',
        reports=reports,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@reports_bp.route('/reports/new', methods=['GET', 'POST'])
@login_required
def new_report():
    if request.method == 'POST':
        location    = request.form.get('location', '').strip()[:200]
        description = request.form.get('description', '').strip()[:2000]
        lat         = request.form.get('lat', '')
        lng         = request.form.get('lng', '')

        if not location or not description:
            flash('Location and description are required.', 'danger')
            return render_template('reports/new.html')
        if len(location) < 3:
            flash('Location must be at least 3 characters.', 'danger')
            return render_template('reports/new.html')
        if len(description) < 10:
            flash('Description must be at least 10 characters.', 'danger')
            return render_template('reports/new.html')

        # ── Run AI Agents ──────────────────────────────────────────────────
        analysis   = analyze_disaster(location, description)
        report_doc = {
            'location':    location,
            'description': description,
            'type':        analysis['type'],
            'severity':    analysis['severity'],
            'risk_score':  analysis['risk_score'],
            'summary':     analysis['summary'],
            'status':      'Active',
            'reported_by': current_user.username,
            'timestamp':   datetime.utcnow().isoformat(),
            'lat':         float(lat) if lat else None,
            'lng':         float(lng) if lng else None,
        }

        report_id = 'demo'
        try:
            db = get_mongo_db()
            result = db.disaster_reports.insert_one(report_doc.copy())
            report_id = str(result.inserted_id)
        except Exception:
            pass

        # Only admin can allocate resources
        if current_user.role == 'admin':
            allocation = allocate_resources(analysis['severity'], report_id)
        else:
            allocation = {
                'allocated': {},
                'insufficient': [],
                'status': 'Pending Admin Review (Only Admins can allocate resources)',
            }

        route = optimize_route(location, analysis['type'])
        alert = generate_alert(location, analysis['type'], analysis['severity'], report_id)

        return render_template(
            'reports/result.html',
            report=report_doc,
            report_id=report_id,
            analysis=analysis,
            allocation=allocation,
            route=route,
            alert=alert,
        )

    return render_template('reports/new.html')


@reports_bp.route('/reports/<report_id>')
@login_required
def view_report(report_id):
    report = None
    try:
        db = get_mongo_db()
        report = db.disaster_reports.find_one({'_id': ObjectId(report_id)})
        if report:
            report['_id'] = str(report['_id'])
    except Exception:
        pass
    if not report:
        flash('Report not found.', 'warning')
        return redirect(url_for('reports.index'))
    return render_template('reports/view.html', report=report)


@reports_bp.route('/reports/<report_id>/status', methods=['POST'])
@login_required
@min_role_required('admin')
def update_status(report_id):
    VALID_STATUSES = {'Active', 'In Progress', 'Resolved', 'Closed'}
    new_status = request.form.get('status', '').strip()
    if new_status not in VALID_STATUSES:
        flash('Invalid status.', 'danger')
        return redirect(url_for('reports.view_report', report_id=report_id))
    try:
        db = get_mongo_db()
        db.disaster_reports.update_one(
            {'_id': ObjectId(report_id)},
            {'$set': {
                'status':     new_status,
                'updated_by': current_user.username,
                'updated_at': datetime.utcnow().isoformat(),
            }}
        )
        flash(f'Report status updated to {new_status}.', 'success')
    except Exception:
        flash('Could not update status.', 'danger')
    return redirect(url_for('reports.view_report', report_id=report_id))
