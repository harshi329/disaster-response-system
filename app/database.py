"""
Database helpers — MongoDB only.
Users, reports, alerts, resources, SOS, broadcasts, volunteers all in MongoDB.
"""
import os
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError

_mongo_client = None


def get_mongo_db():
    global _mongo_client
    if _mongo_client is None:
        uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/disaster_response')
        if 'mongodb.net' in uri or 'mongodb+srv' in uri:
            _mongo_client = MongoClient(
                uri,
                serverSelectionTimeoutMS=20000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000,
                tls=True,
                tlsAllowInvalidCertificates=True,
                tlsAllowInvalidHostnames=True,
                retryWrites=True,
            )
        else:
            _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _mongo_client['disaster_response']


def init_db():
    """Create indexes for the users collection."""
    try:
        db = get_mongo_db()
        db.users.create_index('username', unique=True)
        db.users.create_index('email',    unique=True)
        db.users.create_index('google_id', sparse=True)
    except Exception:
        pass
