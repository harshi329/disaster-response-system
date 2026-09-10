"""
Run once to seed MongoDB with sample data and initialize resource inventory.
Usage: python seed_db.py
"""
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash
from app.database import get_mongo_db, init_db
from app import create_app

SAMPLE_REPORTS = [
    {'location': 'River Road', 'type': 'Flood', 'severity': 'High', 'risk_score': 9,
     'description': 'Flood near River Road. Water rising quickly.',
     'summary': 'Flood detected. Severity: High. Immediate attention required.',
     'status': 'Active', 'reported_by': 'admin', 'lat': 28.6139, 'lng': 77.2090},
    {'location': 'Green Park', 'type': 'Fire', 'severity': 'Medium', 'risk_score': 6,
     'description': 'Fire reported in Green Park residential area.',
     'summary': 'Fire detected. Severity: Medium.',
     'status': 'Active', 'reported_by': 'admin', 'lat': 28.5600, 'lng': 77.2000},
    {'location': 'Hill Zone', 'type': 'Earthquake', 'severity': 'High', 'risk_score': 9,
     'description': 'Major earthquake in Hill Zone. Buildings collapsed.',
     'summary': 'Earthquake detected. Severity: High.',
     'status': 'Active', 'reported_by': 'admin', 'lat': 28.7041, 'lng': 77.1025},
]

SAMPLE_ALERTS = [
    {'location': 'River Road', 'disaster_type': 'Flood', 'severity': 'High',
     'message': 'FLOOD ALERT: Avoid River Road area. Move to higher ground immediately.',
     'status': 'Active', 'created_at': datetime.utcnow().isoformat()},
]

INVENTORY = {
    '_id': 'inventory',
    'ambulances': 10,
    'rescue_teams': 5,
    'food_packets': 1000,
    'helicopters': 2,
}

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
            print('✅ Admin user created  (username: drs_admin / password: admin123)')
        else:
            # Ensure existing admin user has admin role
            db.users.update_one({'username': 'drs_admin'}, {'$set': {'role': 'admin'}})
            print('ℹ️  Admin user already exists — role set to admin.')

        # Ensure all existing users without a role or with legacy responder role get 'citizen'
        db.users.update_many(
            {'role': {'$in': ['responder', None]}},
            {'$set': {'role': 'citizen'}}
        )
        db.users.update_many(
            {'role': {'$exists': False}},
            {'$set': {'role': 'citizen'}}
        )
        print('✅ Backfilled citizen role for existing users.')

        # ── Sample data ────────────────────────────────────────────────
        # Clear existing
        db.disaster_reports.delete_many({})
        db.alerts.delete_many({})
        db.resources.delete_many({})

        # Insert
        now = datetime.utcnow()
        for i, r in enumerate(SAMPLE_REPORTS):
            r['timestamp'] = (now - timedelta(minutes=i * 15)).isoformat()
            db.disaster_reports.insert_one(r)

        for a in SAMPLE_ALERTS:
            db.alerts.insert_one(a)

        db.resources.insert_one(INVENTORY)

        print('✅ Database seeded successfully.')

if __name__ == '__main__':
    seed()
