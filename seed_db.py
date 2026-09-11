"""
Run once to seed MongoDB with sample benchmark data matching Analytics dashboard and initialize resource inventory.
Usage: python seed_db.py
"""
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from app.database import get_mongo_db, init_db
from app import create_app


def get_benchmark_seed_data():
    now = datetime.utcnow()

    reports = [
        # 05-29: 2 Medium reports
        {'location': 'Old Railway Underpass', 'type': 'Flood', 'severity': 'Medium', 'risk_score': 6.5,
         'description': 'Heavy waterlogging reaching 3 feet. Civilian traffic halted.',
         'summary': 'Waterlogging advisory issued; pump stations deployed.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.6250, 'lng': 77.2150,
         'timestamp': '2026-05-29T10:15:00'},
        {'location': 'Central Bus Terminal', 'type': 'Flood', 'severity': 'Medium', 'risk_score': 6.0,
         'description': 'Storm drain backflow inundating terminal bays.',
         'summary': 'Buses redirected to satellite parking lot.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.6400, 'lng': 77.2250,
         'timestamp': '2026-05-29T14:30:00'},

        # 05-31: 7 reports (2 High, 5 Medium)
        {'location': 'Yamuna River Bank, Sector 14', 'type': 'Flood', 'severity': 'High', 'risk_score': 9.2,
         'description': 'Water levels breached safety embankment. Evacuation in progress.',
         'summary': 'Critical flood condition. Immediate emergency assistance deployed.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.6139, 'lng': 77.2090,
         'timestamp': '2026-05-31T08:30:00'},
        {'location': 'Brodipet Industrial Complex', 'type': 'Fire', 'severity': 'High', 'risk_score': 8.8,
         'description': 'Major chemical warehouse fire. NDRF teams and fire tenders on site.',
         'summary': 'High severity commercial fire with heavy smoke dispersion.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.5600, 'lng': 77.2000,
         'timestamp': '2026-05-31T11:15:00'},
        {'location': 'Metro Station Line 3', 'type': 'Flood', 'severity': 'Medium', 'risk_score': 5.8,
         'description': 'Rainwater seepage into concourse entrance.',
         'summary': 'Drainage diversion underway; station operations maintained.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.6180, 'lng': 77.2100,
         'timestamp': '2026-05-31T12:00:00'},
        {'location': 'Market Square Substation', 'type': 'Fire', 'severity': 'Medium', 'risk_score': 6.0,
         'description': 'Transformer explosion near shopping street.',
         'summary': 'Power substation isolated and blaze suppressed.',
         'status': 'Resolved', 'reported_by': 'admin', 'lat': 28.6300, 'lng': 77.2200,
         'timestamp': '2026-05-31T13:45:00'},
        {'location': 'Green Valley Timber Yard', 'type': 'Fire', 'severity': 'Medium', 'risk_score': 6.2,
         'description': 'Dry wood storage caught fire from lightning strike.',
         'summary': 'Fire containment line established.',
         'status': 'Resolved', 'reported_by': 'admin', 'lat': 28.5900, 'lng': 77.1800,
         'timestamp': '2026-05-31T15:20:00'},
        {'location': 'North Sector Highway Bridge', 'type': 'Earthquake', 'severity': 'Medium', 'risk_score': 5.5,
         'description': 'Minor surface cracks detected along flyover expansion joints.',
         'summary': 'Traffic routed to single lane for structural inspection.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.6500, 'lng': 77.2300,
         'timestamp': '2026-05-31T16:50:00'},
        {'location': 'Coastal Ring Road Sector 9', 'type': 'Cyclone', 'severity': 'Medium', 'risk_score': 6.8,
         'description': 'Gale force winds uprooted trees and electric pylons.',
         'summary': 'Road clearance squads operating with heavy cranes.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.5800, 'lng': 77.2400,
         'timestamp': '2026-05-31T18:10:00'},

        # 06-01: 2 reports (1 High, 1 Low)
        {'location': 'Hill Zone Ridge Colony', 'type': 'Earthquake', 'severity': 'High', 'risk_score': 8.5,
         'description': 'Seismic tremors triggered structural collapse and rockfall.',
         'summary': 'Severe structural damage reported. Search squads conducting triage.',
         'status': 'Active', 'reported_by': 'admin', 'lat': 28.7041, 'lng': 77.1025,
         'timestamp': '2026-06-01T08:20:00'},
        {'location': 'West Block Community Park', 'type': 'Flood', 'severity': 'Low', 'risk_score': 3.5,
         'description': 'Shallow standing water on walking tracks.',
         'summary': 'Natural drainage progressing normally.',
         'status': 'Resolved', 'reported_by': 'admin', 'lat': 28.6100, 'lng': 77.1950,
         'timestamp': '2026-06-01T09:40:00'},
    ]

    alerts = []
    for r in reports:
        alerts.append({
            'location': r['location'],
            'disaster_type': r['type'],
            'severity': r['severity'],
            'message': f"EMERGENCY ADVISORY: {r['type'].upper()} incident in {r['location']}. Please exercise caution.",
            'status': r['status'],
            'created_at': r['timestamp'],
        })

    sos_alerts = []
    sos_types = ['Medical Emergency', 'Trapped / Stuck', 'Fire', 'Flood', 'Medical Emergency', 'Earthquake', 'Flood', 'General Emergency']
    for i, stype in enumerate(sos_types):
        t_offset = (now - timedelta(hours=(i + 1) * 3)).isoformat()
        sos_alerts.append({
            'name': f'Citizen #{101 + i}',
            'location': f'Sector {4 + (i % 6)}, Block {chr(65 + i % 4)}',
            'message': f'Urgent assistance requested for {stype.lower()}. Responders dispatched.',
            'people': (i % 3) + 1,
            'sos_type': stype,
            'status': 'Resolved',
            'created_at': t_offset,
            'resolved_at': now.isoformat(),
            'resolved_by': 'admin'
        })

    inventory = {
        '_id': 'inventory',
        'ambulances': 7,
        'rescue_teams': 3,
        'food_packets': 650,
        'helicopters': 1,
    }

    return reports, alerts, sos_alerts, inventory


def seed():
    app = create_app()
    with app.app_context():
        init_db()
        db = get_mongo_db()

        # ── Default admin user ─────────────────────────────────────────
        if not db.users.find_one({'username': 'drs_admin'}):
            db.users.insert_one({
                'username': 'drs_admin',
                'password': generate_password_hash('admin123'),
                'email':    'vu.241fa04313@gmail.com',
                'phone':    '',
                'role':     'admin',
            })
            print('[OK] Admin user created  (username: drs_admin / password: admin123)')
        else:
            db.users.update_one({'username': 'drs_admin'}, {'$set': {'role': 'admin'}})
            print('[INFO] Admin user verified.')

        # ── Sample benchmark data ──────────────────────────────────────
        reports, alerts, sos_alerts, inventory = get_benchmark_seed_data()

        db.disaster_reports.delete_many({})
        db.disaster_reports.insert_many(reports)

        db.alerts.delete_many({})
        db.alerts.insert_many(alerts)

        db.sos_alerts.delete_many({})
        db.sos_alerts.insert_many(sos_alerts)

        db.resources.delete_many({})
        db.resources.insert_one(inventory)

        print(f'[OK] Database seeded successfully with benchmark analytics:')
        print(f'   - {len(reports)} Disaster Reports')
        print(f'   - {len(alerts)} Emergency Alerts')
        print(f'   - {len(sos_alerts)} Resolved SOS Alerts')
        print(f'   - Active inventory baseline ready')


if __name__ == '__main__':
    seed()
