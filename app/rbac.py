"""
Role-Based Access Control (RBAC)
---------------------------------
Roles (in ascending order of privilege):
  citizen   — default on registration; can submit SOS, register as volunteer,
               view dashboard, alerts, map, weather, chatbot, analytics
  responder — everything citizen can do, plus: submit/view reports,
               resolve SOS, view all volunteers
  admin     — full access; additionally: deploy volunteers, send broadcasts,
               manage resource inventory, manage users

Usage in routes:
    from ..rbac import role_required

    @bp.route('/some-admin-page')
    @login_required
    @role_required('admin')
    def admin_page(): ...

    # Allow multiple roles:
    @role_required('admin', 'responder')
    def responder_page(): ...
"""
from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

# Hierarchy: higher index = more privilege
ROLE_HIERARCHY = ['citizen', 'volunteer', 'admin']


def _rank(role: str) -> int:
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


def has_role(user, *roles: str) -> bool:
    """Return True if the user has at least one of the given roles."""
    user_role = getattr(user, 'role', 'citizen') or 'citizen'
    return user_role in roles


def has_min_role(user, min_role: str) -> bool:
    """Return True if the user's role is >= min_role in the hierarchy."""
    user_role = getattr(user, 'role', 'citizen') or 'citizen'
    return _rank(user_role) >= _rank(min_role)


def role_required(*roles: str):
    """
    Decorator that restricts a view to users with at least one of the given roles.
    Must be applied AFTER @login_required.

    Example:
        @login_required
        @role_required('admin', 'responder')
        def my_view(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not has_role(current_user, *roles):
                flash(
                    f'Access denied. Required role: {" or ".join(roles)}. '
                    f'Your role: {getattr(current_user, "role", "citizen")}.',
                    'danger'
                )
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def min_role_required(min_role: str):
    """
    Decorator that restricts a view to users whose role rank >= min_role.
    Useful when you want 'admin' to automatically pass a 'responder' check.

    Example:
        @login_required
        @min_role_required('responder')   # allows responder AND admin
        def my_view(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not has_min_role(current_user, min_role):
                flash(
                    f'Access denied. Minimum required role: {min_role}. '
                    f'Your role: {getattr(current_user, "role", "citizen")}.',
                    'danger'
                )
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator
