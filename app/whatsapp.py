"""
WhatsApp messaging — uses wa.me share links (works for ANY number, no API key).
Opens WhatsApp with a pre-filled message; the user picks the contact.
"""
import urllib.parse
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


def send_whatsapp(phone: str, message: str) -> dict:
    """
    Returns a wa.me share URL for the given phone and message.
    No server-side sending — opens WhatsApp in the browser.
    """
    url = whatsapp_share_url(message, phone)
    logger.info('WhatsApp share URL generated for %s', phone)
    return {'sent': False, 'url': url, 'method': 'share_link'}


def send_whatsapp_bulk(numbers: list, message: str) -> list:
    return [{'to': n, **send_whatsapp(n, message)} for n in numbers if n]


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
        f"{emoji} *BROADCAST — {b.get('type', 'General').upper()}*\n\n"
        f"*{b.get('title', '')}*\n\n"
        f"{b.get('message', '')}\n\n"
        f"📍 Area: {b.get('area', 'All Areas')}\n"
        f"🕐 {b.get('created_at', '')[:16]}\n\n"
        f"🚔 Police: 100 | 🚒 Fire: 101 | 🚑 Ambulance: 108"
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
