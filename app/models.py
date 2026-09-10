"""
User model — backed by MongoDB users collection.
"""
import re
from flask_login import UserMixin
from bson import ObjectId
from .database import get_mongo_db


class User(UserMixin):
    def __init__(self, id, username, email, phone=None, role='citizen'):
        self.id       = str(id)
        self.username = username
        self.email    = email
        self.phone    = phone
        self.role     = role or 'citizen'

    # ── Convenience role checks ────────────────────────────────────────
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_responder(self):
        # Backward compatibility alias
        return self.is_admin

    @property
    def is_volunteer(self):
        return self.role in ('volunteer', 'admin')

    @property
    def is_citizen(self):
        return self.role == 'citizen'

    # ── DB helpers ─────────────────────────────────────────────────────
    @staticmethod
    def get_by_id(user_id):
        try:
            db  = get_mongo_db()
            doc = db.users.find_one({'_id': ObjectId(str(user_id))})
            if doc:
                return User(
                    doc['_id'],
                    doc['username'],
                    doc['email'],
                    doc.get('phone'),
                    doc.get('role', 'citizen'),
                )
        except Exception:
            pass
        return None

    @staticmethod
    def get_by_identifier(identifier):
        """Find a user by username or email (case-insensitive)."""
        if not identifier:
            return None
        try:
            db = get_mongo_db()
            clean_id = str(identifier).strip()
            # 1. Exact match first (fastest)
            doc = db.users.find_one({'username': clean_id})
            if not doc:
                doc = db.users.find_one({'email': clean_id.lower()})
            if not doc:
                # 2. Case-insensitive regex match on username or email
                pattern = f'^{re.escape(clean_id)}$'
                doc = db.users.find_one({
                    '$or': [
                        {'username': {'$regex': pattern, '$options': 'i'}},
                        {'email': {'$regex': pattern, '$options': 'i'}},
                    ]
                })
            return doc
        except Exception:
            return None

    @staticmethod
    def get_by_username(username):
        return User.get_by_identifier(username)

    @staticmethod
    def get_by_email(email):
        return User.get_by_identifier(email)
