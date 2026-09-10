"""
Database helpers — MongoDB only.
"""
import os
import logging
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash
import certifi

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
    except Exception as e:
        logger.error('Error during init_db: %s', e)

