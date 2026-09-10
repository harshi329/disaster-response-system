"""
Database helpers — MongoDB only.
"""
import os
import logging
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash
import certifi
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
_mongo_client = None


def get_mongo_db():
    global _mongo_client
    if _mongo_client is None:
        uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/disaster_response')

        # Clean any invalid params
        clean_uri = uri.replace('&tlsInsecure=true', '').replace('?tlsInsecure=true', '')

        if 'mongodb.net' in clean_uri or 'mongodb+srv' in clean_uri:
            # Primary strategy: trusted CA bundle via certifi
            strategies = [
                # Strategy 1: standard secure TLS with certifi bundle
                dict(
                    tls=True,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                ),
                # Strategy 2: fallback for corporate proxies / self-signed inspection
                dict(
                    tls=True,
                    tlsAllowInvalidCertificates=True,
                    tlsAllowInvalidHostnames=True,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                ),
                # Strategy 3: bare connection
                dict(serverSelectionTimeoutMS=5000),
            ]

            for i, kwargs in enumerate(strategies):
                try:
                    client = MongoClient(clean_uri, **kwargs)
                    client['disaster_response'].command('ping')
                    _mongo_client = client
                    logger.info('MongoDB connected using strategy %d', i + 1)
                    break
                except Exception as e:
                    logger.warning('MongoDB strategy %d failed: %s', i + 1, e)
                    continue

            if _mongo_client is None:
                _mongo_client = MongoClient(
                    clean_uri,
                    tls=True,
                    tlsAllowInvalidCertificates=True,
                    tlsAllowInvalidHostnames=True,
                    serverSelectionTimeoutMS=8000,
                )
        else:
            _mongo_client = MongoClient(clean_uri, serverSelectionTimeoutMS=3000)

    db_name = os.environ.get('MONGO_DB_NAME', 'disaster_response')
    return _mongo_client[db_name]


def init_db():
    """Create indexes and ensure default admin user and inventory exist."""
    try:
        db = get_mongo_db()
        db.users.create_index('username', unique=True)
        db.users.create_index('email',    unique=True)
        db.users.create_index('google_id', sparse=True)

        # ── Guarantee default admin user exists ───────────────────────
        admin_user = os.environ.get('ADMIN_USERNAME', 'drs_admin')
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        admin_email = os.environ.get('ADMIN_EMAIL', 'vu.241fa04313@gmail.com')

        admin_doc = db.users.find_one({'username': admin_user})
        if not admin_doc:
            db.users.insert_one({
                'username': admin_user,
                'password': generate_password_hash(admin_pass),
                'email':    admin_email,
                'phone':    '',
                'role':     'admin',
            })
            logger.info('Admin user created: %s', admin_user)
        else:
            updates = {'role': 'admin'}
            if os.environ.get('ADMIN_PASSWORD'):
                updates['password'] = generate_password_hash(admin_pass)
            db.users.update_one({'username': admin_user}, {'$set': updates})

        # ── Migrate legacy 'responder' role users to 'citizen' ───────
        db.users.update_many(
            {'role': 'responder'},
            {'$set': {'role': 'citizen'}}
        )
        db.users.update_many(
            {'role': {'$exists': False}},
            {'$set': {'role': 'citizen'}}
        )

        # ── Ensure default inventory document exists ─────────────────
        if not db.resources.find_one({'_id': 'inventory'}):
            db.resources.insert_one({
                '_id': 'inventory',
                'ambulances': 10,
                'rescue_teams': 5,
                'food_packets': 1000,
                'helicopters': 2,
            })

        # ── Clean up any odd/fake test alerts ────────────────────────
        db.alerts.delete_many({'message': {'$regex': 'test|quotes|dummy', '$options': 'i'}})
        db.sos_alerts.delete_many({'message': {'$regex': 'test alert|test message', '$options': 'i'}})

        # ── Seed realistic emergency SOS alerts if needed ────────────
        if db.sos_alerts.count_documents({}) <= 1:
            from datetime import timedelta
            now = datetime.utcnow()
            sample_sos = [
                {
                    'name': 'Kavitha Rao',
                    'reported_by': 'Kavitha_Rao',
                    'sos_type': 'Medical Emergency',
                    'location': 'Brodipet 4th Line, Near Old Hospital',
                    'message': 'Elderly patient with severe breathing difficulty. Need urgent oxygen support and ambulance assistance.',
                    'people': '2',
                    'status': 'Active',
                    'lat': 16.3067,
                    'lng': 80.4365,
                    'created_at': (now - timedelta(minutes=24)).isoformat(),
                },
                {
                    'name': 'Ramesh Kumar',
                    'reported_by': 'Ramesh_K',
                    'sos_type': 'Trapped / Stuck',
                    'location': 'Krishna Canal Low-lying Bund, Ward 12',
                    'message': 'Water level rising rapidly over 4 feet on ground floor. Family of 4 stranded on upper terrace, need boat rescue.',
                    'people': '4',
                    'status': 'Active',
                    'lat': 16.3142,
                    'lng': 80.4491,
                    'created_at': (now - timedelta(hours=1, minutes=10)).isoformat(),
                },
                {
                    'name': 'Suresh Reddy',
                    'reported_by': 'Suresh_R',
                    'sos_type': 'Flood',
                    'location': 'Auto Nagar Industrial Area, Near Sector 3',
                    'message': 'Flash water logging inside warehouse. 6 workers trapped on loading dock, power lines sparking nearby.',
                    'people': '6',
                    'status': 'Active',
                    'lat': 16.2981,
                    'lng': 80.4550,
                    'created_at': (now - timedelta(hours=2, minutes=5)).isoformat(),
                },
                {
                    'name': 'Priya Varma',
                    'reported_by': 'Priya_V',
                    'sos_type': 'Medical Emergency',
                    'location': 'Arundelpet 6th Cross',
                    'message': 'Insulin and emergency pediatric medications required for child isolated due to waterlogged approach road.',
                    'people': '3',
                    'status': 'Resolved',
                    'resolved_by': 'drs_admin',
                    'resolved_at': (now - timedelta(hours=3, minutes=30)).isoformat(),
                    'created_at': (now - timedelta(hours=4, minutes=15)).isoformat(),
                },
                {
                    'name': 'Venkatesh Babu',
                    'reported_by': 'Venkatesh_B',
                    'sos_type': 'Fire',
                    'location': 'Market Yard Commercial Complex',
                    'message': 'Electrical meter box fire in commercial building; fire service dispatched and area safely evacuated.',
                    'people': '5',
                    'status': 'Resolved',
                    'resolved_by': 'drs_admin',
                    'resolved_at': (now - timedelta(hours=5)).isoformat(),
                    'created_at': (now - timedelta(hours=6)).isoformat(),
                },
                {
                    'name': 'Anil Kumar',
                    'reported_by': 'Anil_K',
                    'sos_type': 'General Emergency',
                    'location': 'Nallapadu Bypass Road',
                    'message': 'Large uprooted tree blocking arterial evacuation route. Cleared with local volunteer team.',
                    'people': '12',
                    'status': 'Resolved',
                    'resolved_by': 'drs_admin',
                    'resolved_at': (now - timedelta(hours=8)).isoformat(),
                    'created_at': (now - timedelta(hours=9)).isoformat(),
                },
            ]
            db.sos_alerts.delete_many({})
            db.sos_alerts.insert_many(sample_sos)
            logger.info('Seeded realistic SOS emergency alerts.')

        # ── Seed sample volunteers if empty ──────────────────────────
        if db.volunteers.count_documents({}) == 0:
            sample_volunteers = [
                {
                    'username': 'dr_arun',
                    'name': 'Dr. Arun Varma',
                    'email': 'arun.varma@volunteer.org',
                    'phone': '+91 98480 12345',
                    'location': 'Guntur - Brodipet',
                    'skills': ['First Aid / Medical', 'Communication / Radio'],
                    'available': 'Yes',
                    'notes': 'Physician available for triage, emergency first aid, and tele-consultation.',
                    'status': 'Available',
                    'registered_at': datetime.utcnow().isoformat(),
                    'assigned_to': None,
                    'deployed_to': None,
                },
                {
                    'username': 'sita_rescue',
                    'name': 'Sita Raman',
                    'email': 'sita.raman@volunteer.org',
                    'phone': '+91 94401 67890',
                    'location': 'Guntur - Arundelpet',
                    'skills': ['Search & Rescue', 'Driving / Transport'],
                    'available': 'No',
                    'notes': 'Certified swimmer and 4x4 off-road vehicle driver.',
                    'status': 'Assigned',
                    'registered_at': datetime.utcnow().isoformat(),
                    'assigned_to': 'Krishna Canal Low-lying Bund',
                    'deployed_to': 'Krishna Canal Low-lying Bund',
                },
                {
                    'username': 'manoj_tech',
                    'name': 'Manoj Kumar',
                    'email': 'manoj.k@volunteer.org',
                    'phone': '+91 99890 54321',
                    'location': 'Guntur - Pattabhipuram',
                    'skills': ['Logistics & Supply', 'Cooking / Food Distribution'],
                    'available': 'Yes',
                    'notes': 'Managing food packet logistics and dry ration distribution centers.',
                    'status': 'Available',
                    'registered_at': datetime.utcnow().isoformat(),
                    'assigned_to': None,
                    'deployed_to': None,
                },
            ]
            db.volunteers.insert_many(sample_volunteers)
            logger.info('Seeded sample volunteers for coordination.')

        # ── Seed realistic general alerts if empty ───────────────────
        if db.alerts.count_documents({}) == 0:
            db.alerts.insert_many([
                {
                    'report_id': 'seed1',
                    'location': 'Krishna River Basin, Low-lying Areas',
                    'disaster_type': 'Flood',
                    'severity': 'High',
                    'message': 'FLOOD ALERT: Krishna River overflow alert near barrage. Residents in low-lying bunds move to higher ground immediately.',
                    'created_at': datetime.utcnow().isoformat(),
                    'status': 'Active',
                },
                {
                    'report_id': 'seed2',
                    'location': 'Industrial Estate Sector 2',
                    'disaster_type': 'Chemical Spill',
                    'severity': 'Medium',
                    'message': 'EMERGENCY WARNING: Minor chemical leak contained in Sector 2. Maintain caution and keep windows closed.',
                    'created_at': datetime.utcnow().isoformat(),
                    'status': 'Active',
                },
            ])
    except Exception as e:
        logger.error('Error during init_db: %s', e)

