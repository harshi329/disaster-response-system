"""
WhatsApp messaging — direct cloud gateways (Twilio, Meta Cloud API, CallMeBot)
and instant wa.me / api.whatsapp.com direct dispatch links for all registered citizens.
"""
import os
import json
import base64
import urllib.parse
import urllib.request
import logging

logger = logging.getLogger(__name__)


def sanitize_phone(phone: str) -> str:
    """Normalize phone number to international format without + or spaces."""
    if not phone:
        return ''
    clean = ''.join(c for c in str(phone) if c.isdigit())
    # If 10 digits starting with 6-9, assume Indian mobile number and prepend 91
    if len(clean) == 10 and clean[0] in ('6', '7', '8', '9'):
        clean = '91' + clean
    return clean


def whatsapp_share_url(message: str, phone: str = '') -> str:
    """
    Generate an api.whatsapp.com URL that opens WhatsApp with a pre-filled message.
    Compatible across desktop (WhatsApp Web) and mobile (WhatsApp App).
    Works for ANY WhatsApp number worldwide — no API key needed.
    """
    encoded = urllib.parse.quote(message.strip())
    clean = sanitize_phone(phone)
    if clean:
        return f'https://api.whatsapp.com/send?phone={clean}&text={encoded}'
    return f'https://api.whatsapp.com/send?text={encoded}'


def send_twilio_whatsapp(to_phone: str, message: str) -> dict:
    """Send WhatsApp message directly via Twilio API if credentials are configured."""
    sid = os.environ.get('TWILIO_ACCOUNT_SID')
    token = os.environ.get('TWILIO_AUTH_TOKEN')
    from_num = os.environ.get('TWILIO_WHATSAPP_FROM') or os.environ.get('TWILIO_PHONE_NUMBER', 'whatsapp:+14155238886')
    if not (sid and token):
        return {'sent': False, 'reason': 'Twilio credentials not configured'}

    clean = sanitize_phone(to_phone)
    if not clean:
        return {'sent': False, 'reason': 'Invalid recipient phone'}

    if not from_num.startswith('whatsapp:'):
        from_num = f'whatsapp:{from_num}'

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({
        'From': from_num,
        'To': f'whatsapp:+{clean}',
        'Body': message
    }).encode('utf-8')

    auth_str = f"{sid}:{token}"
    auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', f'Basic {auth_b64}')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8')
            logger.info("Twilio WhatsApp sent directly to %s", clean)
            return {'sent': True, 'method': 'twilio_api', 'response': body}
    except Exception as e:
        logger.warning("Twilio WhatsApp direct send failed to %s: %s", clean, e)
        return {'sent': False, 'method': 'twilio_api', 'error': str(e)}


def send_meta_cloud_whatsapp(to_phone: str, message: str) -> dict:
    """Send WhatsApp message directly via Meta WhatsApp Cloud API if configured."""
    token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    phone_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    if not (token and phone_id):
        return {'sent': False, 'reason': 'Meta WhatsApp Cloud credentials not configured'}

    clean = sanitize_phone(to_phone)
    if not clean:
        return {'sent': False, 'reason': 'Invalid recipient phone'}

    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, method='POST')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8')
            logger.info("Meta WhatsApp Cloud sent directly to %s", clean)
            return {'sent': True, 'method': 'meta_cloud_api', 'response': body}
    except Exception as e:
        logger.warning("Meta WhatsApp Cloud send failed to %s: %s", clean, e)
        return {'sent': False, 'method': 'meta_cloud_api', 'error': str(e)}


def send_callmebot_whatsapp(to_phone: str, message: str) -> dict:
    """Send WhatsApp message directly via CallMeBot gateway if configured."""
    apikey = os.environ.get('CALLMEBOT_API_KEY')
    if not apikey:
        return {'sent': False, 'reason': 'CallMeBot API key not configured'}

    clean = sanitize_phone(to_phone)
    encoded = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={clean}&text={encoded}&apikey={apikey}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'DisasterResponse/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return {'sent': True, 'method': 'callmebot_api'}
    except Exception as e:
        return {'sent': False, 'method': 'callmebot_api', 'error': str(e)}


def send_whatsapp(phone: str, message: str) -> dict:
    """
    Attempts direct server-side gateway delivery (Twilio, Meta, CallMeBot)
    and always generates an immediate direct WhatsApp share link as well.
    """
    clean = sanitize_phone(phone)
    url = whatsapp_share_url(message, clean)

    # 1. Try Twilio if configured
    if os.environ.get('TWILIO_ACCOUNT_SID') and os.environ.get('TWILIO_AUTH_TOKEN'):
        res = send_twilio_whatsapp(clean, message)
        if res.get('sent'):
            return {'sent': True, 'url': url, 'method': 'twilio_api'}

    # 2. Try Meta Cloud API if configured
    if os.environ.get('WHATSAPP_ACCESS_TOKEN') and os.environ.get('WHATSAPP_PHONE_NUMBER_ID'):
        res = send_meta_cloud_whatsapp(clean, message)
        if res.get('sent'):
            return {'sent': True, 'url': url, 'method': 'meta_cloud_api'}

    # 3. Try CallMeBot if configured
    if os.environ.get('CALLMEBOT_API_KEY'):
        res = send_callmebot_whatsapp(clean, message)
        if res.get('sent'):
            return {'sent': True, 'url': url, 'method': 'callmebot_api'}

    # 4. Instant Direct WhatsApp link
    logger.info('WhatsApp direct dispatch link prepared for %s', clean)
    return {'sent': False, 'url': url, 'method': 'direct_whatsapp_link'}


def send_whatsapp_bulk(recipients: list, message: str) -> list:
    """
    Sends/prepares WhatsApp delivery for a list of phone strings or recipient dicts.
    """
    results = []
    for r in recipients:
        phone = r['phone'] if isinstance(r, dict) else r
        name = r.get('name', 'Citizen') if isinstance(r, dict) else 'Citizen'
        if not phone:
            continue
        clean = sanitize_phone(phone)
        status = send_whatsapp(clean, message)
        results.append({
            'name': name,
            'phone': clean,
            'raw_phone': phone,
            'url': status.get('url') or whatsapp_share_url(message, clean),
            'sent': status.get('sent', False),
            'method': status.get('method', 'direct_whatsapp_link')
        })
    return results


def format_sos_message(sos: dict) -> str:
    return (
        f"🆘 *SOS ALERT — DISASTER RESPONSE SYSTEM*\n\n"
        f"*Type:* {sos.get('sos_type', 'Emergency')}\n"
        f"*Location:* {sos.get('location', '—')}\n"
        f"*People:* {sos.get('people', '—')}\n"
        f"*Message:* {sos.get('message', '—')}\n"
        f"*Reported by:* {sos.get('reported_by', '—')}\n"
        f"*Time:* {sos.get('created_at', '')[:16]}\n\n"
        f"🚔 Police: 100 | 🚒 Fire: 101 | 🚑 Ambulance: 108\n"
        f"NDRF: 011-24363260"
    )


def format_broadcast_message(b: dict) -> str:
    emoji = {'Critical': '🚨', 'Urgent': '⚠️', 'Normal': '📢'}.get(b.get('priority', 'Normal'), '📢')
    return (
        f"{emoji} *DISASTER BROADCAST — {b.get('type', 'General').upper()}*\n\n"
        f"*{b.get('title', '')}*\n\n"
        f"{b.get('message', '')}\n\n"
        f"📍 *Affected Area:* {b.get('area', 'All Areas')}\n"
        f"🕐 *Time:* {b.get('created_at', '')[:16]}\n"
        f"👤 *Issued by:* {b.get('sent_by', 'Disaster Authority')}\n\n"
        f"🚨 *24/7 Emergency Helplines:*\n"
        f"• Emergency Control: 112\n"
        f"• Ambulance: 108\n"
        f"• Fire: 101\n"
        f"• Police: 100\n"
        f"• Disaster Relief: 1070"
    )


def format_volunteer_message(v: dict) -> str:
    skills = ', '.join(v.get('skills', []))
    return (
        f"🙋 *VOLUNTEER REGISTERED — DISASTER RESPONSE*\n\n"
        f"*Name:* {v.get('name', '—')}\n"
        f"*Location:* {v.get('location', '—')}\n"
        f"*Skills:* {skills}\n"
        f"*Available:* {v.get('available', '—')}\n\n"
        f"Thank you! You will be contacted when needed.\n"
        f"🚔 Police: 100 | 🚒 Fire: 101 | 🚑 Ambulance: 108"
    )


def format_chat_message(username: str, question: str, answer: str) -> str:
    clean = answer.replace('**', '*').replace('• ', '• ')[:800]
    return (
        f"🤖 *ARIA — Disaster Response Assistant*\n\n"
        f"*Q:* {question[:200]}\n\n"
        f"*A:*\n{clean}\n\n"
        f"🚔 Police: 100 | 🚒 Fire: 101 | 🚑 Ambulance: 108"
    )

