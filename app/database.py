"""
Database helpers — MongoDB only.
"""
import os
import logging
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)
_mongo_client = None


def get_mongo_db():
    global _mongo_client
    if _mongo_client is None:
        uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/disaster_response')

        # Clean any invalid params
        clean_uri = uri.replace('&tlsInsecure=true', '').replace('?tlsInsecure=true', '')

        if 'mongodb.net' in clean_uri or 'mongodb+srv' in clean_uri:
            # Try multiple connection strategies for Render compatibility
            strategies = [
                # Strategy 1: tlsAllowInvalidCertificates
                dict(
                    tls=True,
                    tlsAllowInvalidCertificates=True,
                    tlsAllowInvalidHostnames=True,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                ),
                # Strategy 2: certifi CA file
                dict(
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                ),
                # Strategy 3: bare connection
                dict(serverSelectionTimeoutMS=5000),
            ]

            for i, kwargs in enumerate(strategies):
                try:
                    if i == 1:
                        import certifi
                        kwargs['tlsCAFile'] = certifi.where()

                    client = MongoClient(clean_uri, **kwargs)
                    # Test connection
                    client['disaster_response'].command('ping')
                    _mongo_client = client
                    logger.info('MongoDB connected using strategy %d', i + 1)
                    break
                except Exception as e:
                    logger.warning('Strategy %d failed: %s', i + 1, e)
                    continue

            if _mongo_client is None:
                # Last resort — just connect without validation
                _mongo_client = MongoClient(
                    clean_uri,
                    tls=True,
                    tlsAllowInvalidCertificates=True,
                    tlsAllowInvalidHostnames=True,
                    serverSelectionTimeoutMS=8000,
                )
        else:
            _mongo_client = MongoClient(clean_uri, serverSelectionTimeoutMS=3000)

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
