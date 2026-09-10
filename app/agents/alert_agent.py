"""
Emergency Alert Agent
Generates public alerts and authority notifications based on disaster analysis.
"""
from datetime import datetime
from ..database import get_mongo_db

ALERT_TEMPLATES = {
    'Flood': {
        'High':   'FLOOD ALERT: Avoid {location} area. Move to higher ground immediately.',
        'Medium': 'FLOOD WARNING: {location} area may experience flooding. Stay alert.',
        'Low':    'FLOOD WATCH: Minor flooding possible near {location}. Monitor updates.',
    },
    'Earthquake': {
        'High':   'EARTHQUAKE ALERT: Major earthquake near {location}. Evacuate buildings immediately.',
        'Medium': 'EARTHQUAKE WARNING: Moderate earthquake near {location}. Check for structural damage.',
        'Low':    'EARTHQUAKE NOTICE: Minor tremor detected near {location}.',
    },
    'Fire': {
        'High':   'FIRE ALERT: Large fire at {location}. Evacuate immediately. Do not return.',
        'Medium': 'FIRE WARNING: Fire reported at {location}. Avoid the area.',
        'Low':    'FIRE NOTICE: Small fire at {location}. Authorities responding.',
    },
    'default': {
        'High':   'EMERGENCY ALERT: {disaster_type} at {location}. Follow evacuation orders.',
        'Medium': 'EMERGENCY WARNING: {disaster_type} reported at {location}. Stay cautious.',
        'Low':    'EMERGENCY NOTICE: {disaster_type} at {location}. Monitor situation.',
    },
}


def generate_alert(location: str, disaster_type: str, severity: str, report_id: str) -> dict:
    """
    Creates and stores an emergency alert. Returns alert details.
    """
    sev = (severity or 'Low').capitalize()
    if sev not in ('High', 'Medium', 'Low'):
        sev = 'Low'

    templates = ALERT_TEMPLATES.get(disaster_type, ALERT_TEMPLATES['default'])
    template = templates.get(sev, ALERT_TEMPLATES['default'].get(sev, 'EMERGENCY NOTICE: {disaster_type} at {location}. Monitor situation.'))
    message = template.format(location=location, disaster_type=disaster_type)

    alert = {
        'report_id': report_id,
        'location': location,
        'disaster_type': disaster_type,
        'severity': sev,
        'message': message,
        'created_at': datetime.utcnow().isoformat(),
        'status': 'Active',
    }

    try:
        db = get_mongo_db()
        result = db.alerts.insert_one(alert.copy())
        alert['_id'] = str(result.inserted_id)
    except Exception:
        alert['_id'] = None

    return alert
