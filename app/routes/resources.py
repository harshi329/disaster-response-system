import json
import random
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
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

KNOWN_COORDINATES = {
    'river road': (28.6139, 77.2090),
    'green park': (28.5600, 77.2000),
    'hill zone': (28.7041, 77.1025),
    'delhi': (28.6139, 77.2090),
    'mumbai': (19.0760, 72.8777),
    'bangalore': (12.9716, 77.5946),
    'chennai': (13.0827, 80.2707),
    'kolkata': (22.5726, 88.3639),
    'hyderabad': (17.3850, 78.4867),
    'pune': (18.5204, 73.8567),
    'ahmedabad': (23.0225, 72.5714),
}


def resolve_coordinates(location_str: str, lat=None, lng=None):
    """Ensure valid float coordinates for mapping and tracking."""
    try:
        if lat is not None and lng is not None and float(lat) != 0 and float(lng) != 0:
            return round(float(lat), 6), round(float(lng), 6)
    except (ValueError, TypeError):
        pass

    loc_clean = (location_str or '').strip().lower()
    for key, coords in KNOWN_COORDINATES.items():
        if key in loc_clean:
            return coords

    # Fallback to deterministic pseudo-offset near base coordinates
    h = abs(hash(loc_clean or 'default'))
    lat_off = ((h % 100) - 50) * 0.001
    lng_off = (((h // 100) % 100) - 50) * 0.001
    return round(28.6139 + lat_off, 6), round(77.2090 + lng_off, 6)


def get_inventory_and_stats(db):
    """Returns real-time inventory at staging base, deployed assets in field, and on-scene counts."""
    inv = db.resources.find_one({'_id': 'inventory'})
    if not inv:
        inv = DEFAULT_INVENTORY.copy()
        inv['_id'] = 'inventory'
        inv['distributed_food_packets'] = 0
        db.resources.insert_one(inv)

    inventory = {
        'ambulances': max(0, inv.get('ambulances', 10)),
        'rescue_teams': max(0, inv.get('rescue_teams', 5)),
        'food_packets': max(0, inv.get('food_packets', 1000)),
        'helicopters': max(0, inv.get('helicopters', 2)),
        'distributed_food_packets': max(0, inv.get('distributed_food_packets', 0)),
    }

    deployed = {'ambulances': 0, 'rescue_teams': 0, 'food_packets': 0, 'helicopters': 0}
    on_scene = {'ambulances': 0, 'rescue_teams': 0, 'food_packets': 0, 'helicopters': 0}

    # Aggregate active units from allocations
    active_allocs = list(db.allocations.find({'status': {'$ne': 'Mission Completed'}}))
    for a in active_allocs:
        for u in a.get('units', []):
            u_type = u.get('type')
            u_phase = u.get('phase', 'en_route')
            u_qty = u.get('quantity', 1)
            if u_type in deployed and u_phase != 'returned':
                deployed[u_type] += u_qty
                if u_phase == 'on_scene':
                    on_scene[u_type] += u_qty

    return inventory, deployed, on_scene


def build_tracked_units(allocated: dict, target_lat: float, target_lng: float, problem_title: str, assigned_by: str):
    """
    Constructs rich tactical unit telemetry objects for advanced life-support ambulances (ALS),
    NDRF search & rescue squads, essential life-support ration logistics, and air rescue wings.
    """
    units = []
    # Command Staging Base offset ~4 to 6 km away from incident site
    depot_lat = round(target_lat - 0.035, 6)
    depot_lng = round(target_lng - 0.026, 6)

    unit_configs = [
        {
            'key': 'ambulances',
            'name_prefix': 'ALS Paramedic Unit',
            'type_label': 'Emergency Medical Service',
            'icon': 'bi-truck-front-fill',
            'color': '#0d6efd',
            'speed': 60,
            'lead_title': 'Chief Paramedic',
            'default_leads': ['R. Sharma, EMT-P', 'A. Verma, EMT-P', 'P. Nair, MD', 'S. Gupta, EMT'],
        },
        {
            'key': 'rescue_teams',
            'name_prefix': 'NDRF Tactical Rescue Squad',
            'type_label': 'Search & Rescue (USAR)',
            'icon': 'bi-people-fill',
            'color': '#198754',
            'speed': 48,
            'lead_title': 'Squad Commander',
            'default_leads': ['Capt. Vikram Singh', 'Maj. Sandeep Rao', 'Insp. Joshi'],
        },
        {
            'key': 'food_packets',
            'name_prefix': 'Life-Support Rations Unit',
            'type_label': 'Relief Nutrition Supplies',
            'icon': 'bi-box-seam-fill',
            'color': '#ffc107',
            'speed': 40,
            'lead_title': 'Relief Logistics Officer',
            'default_leads': ['M. Khan (Civil Supplies)', 'D. Reddy (Rations Lead)'],
        },
        {
            'key': 'helicopters',
            'name_prefix': 'Tactical Air Rescue Chopper',
            'type_label': 'Air Rescue & Evacuation Wing',
            'icon': 'bi-airplane-fill',
            'color': '#0dcaf0',
            'speed': 160,
            'lead_title': 'Flight Operations Commander',
            'default_leads': ['Wing Cdr. Roy', 'Capt. Malhotra'],
        },
    ]

    unit_idx = 0
    for cfg in unit_configs:
        qty = allocated.get(cfg['key'], 0)
        if qty <= 0:
            continue

        num_physical_units = 1 if cfg['key'] == 'food_packets' else min(qty, 4)
        for i in range(num_physical_units):
            uid = f"{cfg['key'][:3].upper()}-{random.randint(101, 999)}"
            lead = cfg['default_leads'][i % len(cfg['default_leads'])]
            # Stagger starting progression smoothly (between 35% and 80%)
            progress = min(85, max(35, 45 + (unit_idx * 12)))
            unit_idx += 1

            # Coordinate along the trajectory from Command Staging Base to Incident Site
            t = progress / 100.0
            cur_lat = round(depot_lat + (target_lat - depot_lat) * t, 6)
            cur_lng = round(depot_lng + (target_lng - depot_lng) * t, 6)
            dist_km = round(max(0.2, (1.0 - t) * 6.0), 1)
            eta_mins = max(1, int((dist_km / cfg['speed']) * 60))

            units.append({
                'unit_id': uid,
                'type': cfg['key'],
                'type_label': cfg['type_label'],
                'name': f"{cfg['name_prefix']} #{uid}" if cfg['key'] != 'food_packets' else f"{cfg['name_prefix']} ({qty} Rations)",
                'icon': cfg['icon'],
                'color': cfg['color'],
                'quantity': qty if cfg['key'] == 'food_packets' else 1,
                'phase': 'en_route',
                'status': 'En Route — In Transit',
                'speed': f"{cfg['speed']} km/h",
                'eta_mins': eta_mins,
                'distance_km': dist_km,
                'progress': progress,
                'lead_name': f"{cfg['lead_title']}: {lead}",
                'origin_lat': depot_lat,
                'origin_lng': depot_lng,
                'current_lat': cur_lat,
                'current_lng': cur_lng,
                'target_lat': target_lat,
                'target_lng': target_lng,
                'assigned_by': assigned_by,
                'assigned_at': datetime.utcnow().strftime('%H:%M:%S UTC'),
                'problem_title': problem_title,
                'returned_to_stock': False,
                'distributed': False,
            })

    return units


@resources_bp.route('/resources')
@login_required
def index():
    inventory = DEFAULT_INVENTORY.copy()
    deployed = {'ambulances': 0, 'rescue_teams': 0, 'food_packets': 0, 'helicopters': 0}
    on_scene = {'ambulances': 0, 'rescue_teams': 0, 'food_packets': 0, 'helicopters': 0}
    pending_alerts = []
    tracked_deployments = []

    try:
        db = get_mongo_db()

        # 1. Load Active Disaster Reports & Alerts needing resources
        active_reports = list(
            db.disaster_reports.find({'status': {'$in': ['Active', 'In Progress', 'Pending']}})
            .sort('timestamp', -1).limit(20)
        )
        active_alerts = list(
            db.alerts.find({'status': {'$in': ['Active', 'Pending', 'Responding']}})
            .sort('created_at', -1).limit(20)
        )

        seen_locations = set()
        for r in active_reports:
            r_id = str(r['_id'])
            loc = r.get('location', 'Unknown Location')
            d_type = r.get('type', 'Disaster')
            sev = r.get('severity', 'High')
            lat, lng = resolve_coordinates(loc, r.get('lat'), r.get('lng'))
            seen_locations.add(loc.lower())

            rec = {
                'ambulances': 2 if sev == 'High' else 1,
                'rescue_teams': 2 if sev == 'High' else 1,
                'food_packets': 200 if sev == 'High' else 100,
                'helicopters': 1 if sev == 'High' else 0,
            }

            pending_alerts.append({
                'id': r_id,
                'type': d_type,
                'location': loc,
                'severity': sev,
                'description': r.get('description') or r.get('summary') or f"{sev} priority {d_type} reported.",
                'timestamp': r.get('timestamp') or datetime.utcnow().isoformat(),
                'status': r.get('status', 'Active'),
                'lat': lat,
                'lng': lng,
                'recommended': rec,
                'is_alert': False,
            })

        for a in active_alerts:
            loc = a.get('location', 'Unknown')
            if loc.lower() in seen_locations:
                continue
            seen_locations.add(loc.lower())
            a_id = str(a['_id'])
            d_type = a.get('disaster_type', 'Emergency')
            sev = a.get('severity', 'High')
            lat, lng = resolve_coordinates(loc)

            rec = {
                'ambulances': 2 if sev == 'High' else 1,
                'rescue_teams': 2 if sev == 'High' else 1,
                'food_packets': 200 if sev == 'High' else 100,
                'helicopters': 1 if sev == 'High' else 0,
            }

            pending_alerts.append({
                'id': a_id,
                'type': d_type,
                'location': loc,
                'severity': sev,
                'description': a.get('message') or f"{sev} priority alert at {loc}.",
                'timestamp': a.get('created_at') or datetime.utcnow().isoformat(),
                'status': a.get('status', 'Active'),
                'lat': lat,
                'lng': lng,
                'recommended': rec,
                'is_alert': True,
            })

        # 2. Load Allocations and build Tracked Deployments
        raw_allocations = list(db.allocations.find({'status': {'$ne': 'Mission Completed'}}).sort('_id', -1).limit(20))
        if not raw_allocations:
            raw_allocations = list(db.allocations.find().sort('_id', -1).limit(20))

        # If no allocations exist yet, auto-seed a realistic deployment for the top active report
        if not raw_allocations and pending_alerts:
            top = pending_alerts[0]
            seed_allocated = {
                'ambulances': 1,
                'rescue_teams': 1,
                'food_packets': 100,
                'helicopters': 1,
            }
            # Deduct from inventory
            db.resources.update_one(
                {'_id': 'inventory'},
                {'$inc': {'ambulances': -1, 'rescue_teams': -1, 'food_packets': -100, 'helicopters': -1}}
            )
            seed_units = build_tracked_units(
                seed_allocated,
                target_lat=top['lat'],
                target_lng=top['lng'],
                problem_title=f"{top['type']} at {top['location']}",
                assigned_by='drs_admin'
            )
            seed_doc = {
                'report_id': top['id'],
                'problem_title': f"{top['type']} at {top['location']}",
                'location': top['location'],
                'severity': top['severity'],
                'target_lat': top['lat'],
                'target_lng': top['lng'],
                'allocated': seed_allocated,
                'insufficient': [],
                'units': seed_units,
                'assigned_by': 'drs_admin',
                'notes': 'Initial emergency response mobilization issued by Incident Command.',
                'status': 'En Route'
            }
            db.allocations.insert_one(seed_doc)
            raw_allocations = [seed_doc]

        for a in raw_allocations:
            a['_id'] = str(a['_id'])
            p_title = a.get('problem_title') or f"Incident at {a.get('location', 'Site')}"
            loc = a.get('location') or 'Incident Site'
            t_lat = a.get('target_lat')
            t_lng = a.get('target_lng')

            if not t_lat or not t_lng:
                t_lat, t_lng = resolve_coordinates(loc)
                a['target_lat'] = t_lat
                a['target_lng'] = t_lng

            units = a.get('units') or []
            if not units and a.get('allocated'):
                units = build_tracked_units(
                    a['allocated'],
                    target_lat=t_lat,
                    target_lng=t_lng,
                    problem_title=p_title,
                    assigned_by=a.get('assigned_by', 'Admin')
                )
                a['units'] = units

            tracked_deployments.append({
                'id': a['_id'],
                'report_id': a.get('report_id', ''),
                'problem_title': p_title,
                'location': loc,
                'severity': a.get('severity', 'High'),
                'target_lat': t_lat,
                'target_lng': t_lng,
                'allocated': a.get('allocated', {}),
                'units': units,
                'assigned_by': a.get('assigned_by', 'Admin'),
                'assigned_at': a.get('assigned_at', ''),
                'notes': a.get('notes', ''),
            })

        inventory, deployed, on_scene = get_inventory_and_stats(db)

    except Exception as e:
        flash(f'Notice: Loaded live telemetry ({e}).', 'warning')

    return render_template(
        'resources/index.html',
        inventory=inventory,
        deployed=deployed,
        on_scene=on_scene,
        pending_alerts=pending_alerts,
        tracked_deployments=tracked_deployments,
        tracked_json=json.dumps(tracked_deployments),
    )


@resources_bp.route('/resources/assign', methods=['POST'])
@login_required
@role_required('admin')
def assign():
    """Admin manually mobilizes resources to a report or emergency alert."""
    report_id    = request.form.get('report_id', '').strip()
    ambulances   = int(request.form.get('ambulances', 0))
    rescue_teams = int(request.form.get('rescue_teams', 0))
    food_packets = int(request.form.get('food_packets', 0))
    helicopters  = int(request.form.get('helicopters', 0))
    notes        = request.form.get('notes', '').strip()[:300]

    if not report_id:
        flash('Please select an active emergency alert or report.', 'danger')
        return redirect(url_for('resources.index'))

    total_requested = ambulances + rescue_teams + food_packets + helicopters
    if total_requested <= 0:
        flash('Please allocate at least one resource (Ambulance, Rescue Squad, Rations, or Helicopter).', 'warning')
        return redirect(url_for('resources.index'))

    try:
        db = get_mongo_db()

        # Find target emergency problem from reports or alerts
        problem_doc = None
        try:
            problem_doc = db.disaster_reports.find_one({'_id': ObjectId(report_id)})
        except Exception:
            pass

        if not problem_doc:
            try:
                problem_doc = db.alerts.find_one({'_id': ObjectId(report_id)})
            except Exception:
                pass

        location = 'Unknown Location'
        disaster_type = 'Emergency'
        severity = 'High'
        t_lat = None
        t_lng = None

        if problem_doc:
            location = problem_doc.get('location', 'Unknown Location')
            disaster_type = problem_doc.get('type') or problem_doc.get('disaster_type', 'Emergency')
            severity = problem_doc.get('severity', 'High')
            t_lat = problem_doc.get('lat')
            t_lng = problem_doc.get('lng')

        target_lat, target_lng = resolve_coordinates(location, t_lat, t_lng)
        problem_title = f"{disaster_type} at {location}"

        # Deduct from Staging Base Inventory
        inv_doc = db.resources.find_one({'_id': 'inventory'})
        if not inv_doc:
            inv_doc = DEFAULT_INVENTORY.copy()
            inv_doc['_id'] = 'inventory'
            db.resources.insert_one(inv_doc)

        needed = {
            'ambulances': ambulances,
            'rescue_teams': rescue_teams,
            'food_packets': food_packets,
            'helicopters': helicopters,
        }

        allocated = {}
        insufficient = []

        for resource, qty in needed.items():
            if qty <= 0:
                continue
            available = inv_doc.get(resource, 0)
            give = min(qty, available)
            allocated[resource] = give
            if give < qty:
                insufficient.append(resource)
            if give > 0:
                db.resources.update_one(
                    {'_id': 'inventory'},
                    {'$inc': {resource: -give}}
                )

        # Build Rich Tactical Tracking Units
        units = build_tracked_units(
            allocated=allocated,
            target_lat=target_lat,
            target_lng=target_lng,
            problem_title=problem_title,
            assigned_by=current_user.username
        )

        # Save to db.allocations with En Route status
        db.allocations.insert_one({
            'report_id': report_id,
            'problem_title': problem_title,
            'location': location,
            'severity': severity,
            'target_lat': target_lat,
            'target_lng': target_lng,
            'allocated': allocated,
            'insufficient': insufficient,
            'units': units,
            'notes': notes,
            'assigned_by': current_user.username,
            'assigned_at': datetime.utcnow().isoformat(),
            'status': 'En Route'
        })

        # Update problem status in database
        if problem_doc:
            try:
                db.disaster_reports.update_one(
                    {'_id': problem_doc['_id']},
                    {'$set': {'status': 'In Progress', 'resources_sent': True}}
                )
                db.alerts.update_many(
                    {'location': location},
                    {'$set': {'status': 'Responding'}}
                )
            except Exception:
                pass

        summary_items = []
        if allocated.get('ambulances'):
            summary_items.append(f"{allocated['ambulances']} ALS Ambulance(s)")
        if allocated.get('rescue_teams'):
            summary_items.append(f"{allocated['rescue_teams']} Rescue Squad(s)")
        if allocated.get('food_packets'):
            summary_items.append(f"{allocated['food_packets']} Ration Package(s)")
        if allocated.get('helicopters'):
            summary_items.append(f"{allocated['helicopters']} Air Rescue Chopper(s)")

        disp_text = ", ".join(summary_items) if summary_items else "Resources"
        if insufficient:
            flash(f"Partially deployed: {disp_text} mobilized for {problem_title}. Insufficient base inventory for: {', '.join(insufficient)}.", 'warning')
        else:
            flash(f"Tactically mobilized & deployed: {disp_text} to {problem_title}! Live telemetry is tracking their progress below.", 'success')

    except Exception as e:
        flash(f"Could not mobilize resources: {e}", 'danger')

    return redirect(url_for('resources.index'))


@resources_bp.route('/resources/api/unit-status', methods=['POST'])
@login_required
def update_unit_status():
    """
    Called automatically when a deployed tactical unit reaches scene, demobilizes, or returns to base.
    Persists unit telemetry and dynamically restores available inventory when units return to base,
    and increments distributed relief rations when life-support supplies arrive on scene.
    """
    data = request.get_json(silent=True) or {}
    allocation_id = data.get('allocation_id')
    unit_id = data.get('unit_id')
    new_phase = data.get('phase')  # 'on_scene', 'returning', 'returned'

    if not allocation_id or not unit_id or not new_phase:
        return jsonify({'error': 'Missing allocation_id, unit_id, or phase'}), 400

    db = get_mongo_db()
    alloc = None
    try:
        alloc = db.allocations.find_one({'_id': ObjectId(allocation_id)})
    except Exception:
        pass
    if not alloc:
        alloc = db.allocations.find_one({'_id': allocation_id})

    if not alloc:
        return jsonify({'error': 'Allocation not found'}), 404

    units = alloc.get('units', [])
    target_unit = None
    all_returned = True

    for u in units:
        if u.get('unit_id') == unit_id:
            target_unit = u
            u['phase'] = new_phase

            if new_phase == 'on_scene':
                u['status'] = 'On Scene — Operations Active'
                u['progress'] = 100
                if u.get('type') == 'food_packets' and not u.get('distributed'):
                    u['distributed'] = True
                    qty = u.get('quantity', 100)
                    db.resources.update_one(
                        {'_id': 'inventory'},
                        {'$inc': {'distributed_food_packets': qty}}
                    )

            elif new_phase == 'returning':
                u['status'] = 'Demobilizing — Returning to Base'

            elif new_phase == 'returned':
                u['status'] = 'Mission Accomplished — Stationed at Base'
                u['progress'] = 0
                # Reusable asset replenishment: restores available fleet stock
                if u.get('type') in ('ambulances', 'rescue_teams', 'helicopters') and not u.get('returned_to_stock'):
                    u['returned_to_stock'] = True
                    qty = u.get('quantity', 1)
                    db.resources.update_one(
                        {'_id': 'inventory'},
                        {'$inc': {u.get('type'): qty}}
                    )

        if u.get('phase') != 'returned':
            all_returned = False

    alloc_status = 'Mission Completed' if all_returned else ('On Scene' if new_phase == 'on_scene' else alloc.get('status', 'In Progress'))

    db.allocations.update_one(
        {'_id': alloc['_id']},
        {'$set': {'units': units, 'status': alloc_status}}
    )

    inventory, deployed, on_scene = get_inventory_and_stats(db)

    return jsonify({
        'success': True,
        'unit_id': unit_id,
        'phase': new_phase,
        'unit': target_unit,
        'inventory': inventory,
        'deployed': deployed,
        'on_scene': on_scene,
    })


@resources_bp.route('/resources/api/live-status')
@login_required
def live_status():
    """Real-time poll endpoint to synchronize live base inventory and active deployed metrics."""
    db = get_mongo_db()
    inventory, deployed, on_scene = get_inventory_and_stats(db)
    return jsonify({
        'inventory': inventory,
        'deployed': deployed,
        'on_scene': on_scene,
    })


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
        flash('Staging Base Inventory replenished successfully.', 'success')
    except Exception as e:
        flash(f'Could not restock: {e}', 'danger')
    return redirect(url_for('resources.index'))


