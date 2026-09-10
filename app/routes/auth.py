import os
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from ..database import get_mongo_db
from ..models import User
from ..otp import generate_and_send_otp, verify_otp
from .. import login_manager

auth_bp = Blueprint('auth', __name__)

# ── Google OAuth setup ────────────────────────────────────────────────────────
oauth = OAuth()
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)


def _init_oauth(app):
    """Call this from create_app() after the app is created."""
    oauth.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)


def _flash_otp_result(result: dict, email: str):
    if result['method'] == 'email':
        parts  = email.split('@')
        masked = parts[0][:2] + '***@' + parts[1] if len(parts) == 2 else '***'
        flash(f'OTP sent to your email <strong>{masked}</strong>. Please check your inbox and spam folder.', 'success')
    else:
        flash('Email delivery is offline. Use the instant verification code shown below.', 'info')


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password   = request.form.get('password', '').strip()

        row = User.get_by_identifier(identifier)
        if not row:
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html')

        # Inform users who registered via Google OAuth that they should use Google login
        if row.get('google_id') and not row.get('password'):
            flash('This account was created with Google. Please click "Continue with Google" above.', 'info')
            return render_template('auth/login.html')

        if not check_password_hash(row.get('password', ''), password):
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html')

        # Admin logs in directly with credentials — NO OTP required!
        if row.get('role') == 'admin':
            user = User(row['_id'], row['username'], row['email'], row.get('phone'), 'admin')
            login_user(user)
            flash(f'Admin login successful. Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard.index'))

        # Citizens & volunteers proceed with OTP verification
        canonical_username = row['username']
        email  = row.get('email', '')
        result = generate_and_send_otp(canonical_username, email=email)

        session['pending_user'] = canonical_username
        if not result['sent']:
            session['fallback_otp'] = result['otp']
        else:
            session.pop('fallback_otp', None)

        _flash_otp_result(result, email)
        return redirect(url_for('auth.verify_otp_view'))

    return render_template('auth/login.html')


@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp_view():
    if 'pending_user' not in session:
        return redirect(url_for('auth.login'))

    fallback_otp = session.get('fallback_otp')

    if request.method == 'POST':
        otp      = request.form.get('otp', '').strip()
        username = session['pending_user']

        if verify_otp(username, otp):
            row  = User.get_by_username(username)
            user = User(row['_id'], row['username'], row['email'], row.get('phone'), row.get('role', 'citizen'))
            login_user(user)
            session.pop('pending_user', None)
            session.pop('fallback_otp', None)
            flash('Login successful. Welcome back!', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid or expired OTP. Please try again.', 'danger')

    return render_template('auth/verify_otp.html', fallback_otp=fallback_otp)


@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    username = session.get('pending_user')
    if not username:
        return redirect(url_for('auth.login'))

    row = User.get_by_username(username)
    if not row:
        return redirect(url_for('auth.login'))

    email  = row.get('email', '')
    result = generate_and_send_otp(username, email=email)
    if not result['sent']:
        session['fallback_otp'] = result['otp']
    else:
        session.pop('fallback_otp', None)

    _flash_otp_result(result, email)
    return redirect(url_for('auth.verify_otp_view'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()[:50]
        password = request.form.get('password', '').strip()
        email    = request.form.get('email', '').strip()[:200]
        phone    = request.form.get('phone', '').strip()[:20]

        if not username or not password or not email:
            flash('Username, email and password are required.', 'danger')
            return render_template('auth/register.html')
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('auth/register.html')
        import re as _re
        if not _re.match(r'^[a-zA-Z0-9_]+$', username):
            flash('Username can only contain letters, numbers and underscores.', 'danger')
            return render_template('auth/register.html')

        hashed = generate_password_hash(password)
        try:
            db = get_mongo_db()
            db.users.insert_one({
                'username': username,
                'password': hashed,
                'email':    email,
                'phone':    phone,
                'role':     'citizen',
            })
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            flash('Username or email already exists.', 'danger')

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


# ── Google OAuth ──────────────────────────────────────────────────────────────

@auth_bp.route('/login/google')
def google_login():
    """Redirect to Google's consent screen."""
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        flash('Google login is not configured. Please use username/password.', 'warning')
        return redirect(url_for('auth.login'))

    configured_redirect = os.environ.get('GOOGLE_REDIRECT_URI')
    if configured_redirect:
        redirect_uri = configured_redirect
    else:
        redirect_uri = url_for('auth.google_callback', _external=True)
        import re
        if re.search(r'://(127\.0\.0\.1|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)', redirect_uri):
            port = request.host.split(':')[-1] if ':' in request.host else os.environ.get('PORT', 5000)
            redirect_uri = f'http://localhost:{port}/login/google/callback'

    return google.authorize_redirect(redirect_uri)


@auth_bp.route('/login/google/callback')
def google_callback():
    """Handle Google's redirect back with the auth code."""
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        flash('Google login is not configured.', 'warning')
        return redirect(url_for('auth.login'))

    try:
        token     = google.authorize_access_token()
        user_info = token.get('userinfo') or google.userinfo()
    except Exception as e:
        flash('Google authentication failed. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    google_id = user_info.get('sub')
    email     = user_info.get('email', '')
    name      = user_info.get('name', '')
    picture   = user_info.get('picture', '')

    if not google_id or not email:
        flash('Could not retrieve account info from Google.', 'danger')
        return redirect(url_for('auth.login'))

    db = get_mongo_db()

    # ── 1. Try to find existing user by google_id ─────────────────────
    doc = db.users.find_one({'google_id': google_id})

    # ── 2. Fallback: find by email (links existing account) ──────────
    if not doc:
        doc = db.users.find_one({'email': email})
        if doc:
            # Link google_id to this existing account
            db.users.update_one(
                {'_id': doc['_id']},
                {'$set': {'google_id': google_id, 'picture': picture}}
            )
            doc = db.users.find_one({'_id': doc['_id']})

    # Admin accounts cannot sign in via Google OAuth
    if doc and doc.get('role') == 'admin':
        flash('Admin accounts must sign in using Admin credentials (username & password).', 'warning')
        return redirect(url_for('auth.login'))

    # ── 3. Auto-register new user ─────────────────────────────────────
    if not doc:
        # Derive a unique username from the Google display name
        base     = re.sub(r'[^a-zA-Z0-9_]', '', name.replace(' ', '_')) or 'user'
        username = base
        counter  = 1
        while db.users.find_one({'username': username}):
            username = f'{base}{counter}'
            counter += 1

        new_doc = {
            'username':  username,
            'email':     email,
            'password':  '',          # no password for OAuth-only accounts
            'phone':     '',
            'role':      'citizen',
            'google_id': google_id,
            'picture':   picture,
        }
        result = db.users.insert_one(new_doc)
        doc    = db.users.find_one({'_id': result.inserted_id})
        flash(f'Welcome! Your account <strong>{username}</strong> has been created.', 'success')

    # ── 4. Log in ─────────────────────────────────────────────────────
    user = User(doc['_id'], doc['username'], doc['email'],
                doc.get('phone'), doc.get('role', 'citizen'))
    login_user(user)
    flash(f'Signed in with Google as <strong>{doc["username"]}</strong>.', 'success')
    return redirect(url_for('dashboard.index'))


# ── Offline fallback page ─────────────────────────────────────────────────────
@auth_bp.route('/offline')
def offline():
    return render_template('offline.html')


# ── Voice test page (no login required for debugging) ────────────────────────
@auth_bp.route('/voice-test')
def voice_test():
    return render_template('voice_test.html')
