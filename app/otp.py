"""
OTP system — 6-digit code with 10-minute expiry.
Storage: MongoDB `otp_store` collection (TTL index auto-expires documents).
Falls back to in-memory dict if MongoDB is unavailable.
"""
import os, random, time, smtplib, logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger  = logging.getLogger(__name__)
OTP_TTL = 600  # 10 minutes

# ── In-memory fallback (used only if MongoDB is down) ────────────────────────
_mem_store: dict = {}


# ── MongoDB helpers ───────────────────────────────────────────────────────────
def _get_collection():
    from .database import get_mongo_db
    db  = get_mongo_db()
    col = db['otp_store']
    # Create TTL index once — documents auto-delete after OTP_TTL seconds
    try:
        col.create_index('expires_at', expireAfterSeconds=0)
    except Exception:
        pass
    return col


def _make_otp(username: str) -> str:
    otp        = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(seconds=OTP_TTL)

    try:
        col = _get_collection()
        col.replace_one(
            {'username': username},
            {
                'username':   username,
                'otp':        otp,
                'expires_at': expires_at,
                'attempts':   0,
            },
            upsert=True,
        )
    except Exception:
        # MongoDB unavailable — use in-memory fallback
        _mem_store[username] = {
            'otp':        otp,
            'expires_at': time.time() + OTP_TTL,
            'attempts':   0,
        }

    return otp


def verify_otp(username: str, otp: str) -> bool:
    # ── Try MongoDB first ────────────────────────────────────────────────────
    try:
        col    = _get_collection()
        record = col.find_one({'username': username})
        if record:
            if datetime.utcnow() > record['expires_at']:
                col.delete_one({'username': username})
                return False
            attempts = record.get('attempts', 0) + 1
            if attempts > 5:
                col.delete_one({'username': username})
                return False
            col.update_one({'username': username}, {'$set': {'attempts': attempts}})
            if record['otp'] == otp.strip():
                col.delete_one({'username': username})
                return True
            return False
    except Exception:
        pass

    # ── Fallback: in-memory ──────────────────────────────────────────────────
    record = _mem_store.get(username)
    if not record:
        return False
    if time.time() > record['expires_at']:
        _mem_store.pop(username, None)
        return False
    record['attempts'] += 1
    if record['attempts'] > 5:
        _mem_store.pop(username, None)
        return False
    if record['otp'] == otp.strip():
        _mem_store.pop(username, None)
        return True
    return False


# ── Email delivery with resilience & circuit breaker ─────────────────────────
_smtp_auth_failed_until: float = 0.0


def _send_email(to_email: str, otp: str, username: str) -> bool:
    global _smtp_auth_failed_until

    sender   = os.environ.get('MAIL_EMAIL', '').strip()
    password = os.environ.get('MAIL_PASSWORD', '').strip()
    if not sender or not password:
        logger.warning('MAIL_EMAIL or MAIL_PASSWORD not set in .env')
        return False

    # Circuit breaker: if Gmail authentication previously failed, do not block login
    # attempts repeatedly with 15s delays. Retry only after 5 minutes.
    if time.time() < _smtp_auth_failed_until:
        logger.warning('SMTP authentication is currently cached as failing; skipping email attempt.')
        return False

    try:
        msg            = MIMEMultipart('alternative')
        msg['Subject'] = f'Your OTP: {otp} – Disaster Response System'
        msg['From']    = f'Disaster Response System <{sender}>'
        msg['To']      = to_email

        text = (f'Hello {username},\n\nYour OTP is: {otp}\n'
                f'Valid for 10 minutes. Do not share.\n\n— Disaster Response System')

        html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:40px 20px;">
<table width="520" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.1);">
  <tr><td style="background:#dc3545;padding:28px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:22px;">Disaster Response System</h1>
    <p style="color:rgba(255,255,255,.85);margin:6px 0 0;font-size:14px;">Two-Factor Authentication</p>
  </td></tr>
  <tr><td style="padding:36px;text-align:center;">
    <p style="color:#444;font-size:16px;margin:0 0 8px;">Hello <strong>{username}</strong>,</p>
    <p style="color:#666;font-size:14px;margin:0 0 20px;">Your login OTP is:</p>
    <div style="background:#fff5f5;border:2px dashed #dc3545;border-radius:12px;
                padding:22px;margin:0 auto 20px;display:inline-block;min-width:240px;">
      <div style="font-size:52px;font-weight:900;letter-spacing:16px;color:#dc3545;">{otp}</div>
    </div>
    <p style="color:#888;font-size:13px;margin:0;">Valid for <strong>10 minutes</strong>. Do not share.</p>
  </td></tr>
  <tr><td style="background:#f8f9fa;padding:12px;text-align:center;border-top:1px solid #dee2e6;">
    <small style="color:#aaa;font-size:11px;">Autonomous Disaster Response Coordination System</small>
  </td></tr>
</table></td></tr></table>
</body></html>"""

        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html,  'html'))

        # Fast timeout (4 seconds) so user login is never frozen
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=4) as server:
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())

        _smtp_auth_failed_until = 0.0
        logger.info('OTP email sent to %s', to_email)
        return True

    except smtplib.SMTPAuthenticationError:
        # Cache failure for 300 seconds (5 minutes)
        _smtp_auth_failed_until = time.time() + 300
        logger.error('Gmail auth failed (check MAIL_EMAIL and MAIL_PASSWORD). Cached for 5m.')
        return False
    except Exception as e:
        logger.error('Email OTP delivery failed: %s', e)
        return False


# ── Public API ────────────────────────────────────────────────────────────────
def generate_and_send_otp(username: str, email: str = '') -> dict:
    otp = _make_otp(username)
    if email and _send_email(email, otp, username):
        return {'otp': otp, 'sent': True, 'method': 'email'}
    return {'otp': otp, 'sent': False, 'method': 'fallback'}


def generate_otp(username: str) -> str:
    return _make_otp(username)
