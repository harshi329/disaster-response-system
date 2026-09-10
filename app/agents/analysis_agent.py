"""
Disaster Analysis Agent
Analyzes a disaster report and returns type, severity, and risk score.
Uses Groq API (openai/gpt-oss-20b or qwen/qwen3.6-27b) when available,
and falls back to intelligent, balanced rule-based classification.
"""
import os
import json
import re
import requests

# Models available on the configured Groq account
GROQ_MODELS = ['openai/gpt-oss-20b', 'qwen/qwen3.6-27b']

# Keywords that indicate MINOR / LOW risk
LOW_SEVERITY_KEYWORDS = [
    'minor', 'small', 'low', 'slight', 'minimal', 'little', 'puddle', 'leak',
    'dripping', 'branch', 'trash', 'test', 'demo', 'exercise', 'drill',
    'power outage', 'waterlogging', 'traffic', 'slow', 'nuisance', 'pothole',
    'contained', 'smoke smell', 'gutter', 'drain'
]

# Keywords that indicate CATASTROPHIC / HIGH risk
CRITICAL_KEYWORDS = [
    'catastrophic', 'fatal', 'fatalities', 'deadly', 'casualties', 'massive',
    'tsunami', 'hurricane', 'tornado', 'severe earthquake', 'collapse',
    'collapsed', 'trapped', 'submerged', 'evacuate immediately', 'evacuation order',
    'uncontrolled fire', 'major explosion', 'life threatening', 'people missing',
    'critical condition'
]

# Keywords that indicate MODERATE / MEDIUM risk
MODERATE_KEYWORDS = [
    'flood', 'fire', 'landslide', 'storm', 'accident', 'chemical', 'gas leak',
    'heavy rain', 'water rising', 'damage', 'blocked road', 'spill'
]

DISASTER_TYPES = [
    'Flood', 'Earthquake', 'Fire', 'Tsunami', 'Hurricane', 'Tornado',
    'Landslide', 'Wildfire', 'Explosion', 'Chemical Spill', 'Gas Leak',
    'Storm', 'Accident', 'Power Outage', 'Other'
]


def _rule_based_analysis(description: str) -> dict:
    desc_lower = description.lower().strip()

    # 1. Detect disaster type
    detected_type = 'Other'
    for dtype in DISASTER_TYPES:
        if dtype.lower() in desc_lower:
            detected_type = dtype
            break

    # Contextual hints for common types
    if detected_type == 'Other':
        if any(w in desc_lower for w in ['water', 'rain', 'puddle', 'leak', 'drain']):
            detected_type = 'Flood'
        elif any(w in desc_lower for w in ['smoke', 'burn', 'flame', 'spark']):
            detected_type = 'Fire'
        elif any(w in desc_lower for w in ['shake', 'tremor', 'quake']):
            detected_type = 'Earthquake'
        elif any(w in desc_lower for w in ['wind', 'gale', 'cyclone']):
            detected_type = 'Storm'

    # 2. Check keywords using word boundary regex
    is_low = any(re.search(r'\b' + re.escape(kw) + r'\b', desc_lower) for kw in LOW_SEVERITY_KEYWORDS)
    is_critical = any(re.search(r'\b' + re.escape(kw) + r'\b', desc_lower) for kw in CRITICAL_KEYWORDS)
    is_moderate = any(re.search(r'\b' + re.escape(kw) + r'\b', desc_lower) for kw in MODERATE_KEYWORDS)

    if is_critical and not is_low:
        severity = 'High'
        risk_score = 9
        summary = f"High-risk {detected_type.lower()} incident detected. Emergency response dispatched."
    elif is_low:
        severity = 'Low'
        risk_score = 2
        summary = f"Minor {detected_type.lower()} issue reported. Low risk, situation monitored."
    elif is_moderate:
        severity = 'Medium'
        risk_score = 5
        summary = f"Moderate {detected_type.lower()} reported. Local response teams notified."
    else:
        # Default / unrecognized: default to Low risk rather than alarming High risk
        severity = 'Low'
        risk_score = 2
        summary = f"{detected_type} report logged. Assessed as low risk."

    return {
        'type': detected_type,
        'severity': severity,
        'risk_score': risk_score,
        'summary': summary,
    }


def _analyze_with_groq(location: str, description: str) -> dict:
    api_key = os.environ.get('GROQ_API_KEY', '').strip()
    if not api_key:
        return None

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    prompt = (
        "You are an emergency disaster assessment AI agent.\n"
        "Analyze this report objectively. Assess whether it is a genuine severe disaster or a minor/nuisance incident.\n"
        "Rules for severity & risk_score:\n"
        "- 'Low': minor issues, small puddles/leaks, light rain, fallen branches, minor power blips, drills/tests. Risk score 1-3.\n"
        "- 'Medium': localized fire, moderate water rise, non-fatal accidents, small localized landslides, chemical/gas odors. Risk score 4-6.\n"
        "- 'High': life-threatening disasters, building collapses, massive wildfires/floods, severe earthquakes, casualties, evacuation needed. Risk score 7-10.\n\n"
        f"Location: {location}\n"
        f"Description: {description}\n\n"
        "Respond ONLY with a JSON object in this exact schema (no markdown fences, no other text):\n"
        '{"type": "<Disaster Type>", "severity": "<High|Medium|Low>", "risk_score": <1-10>, "summary": "<one calm, accurate sentence>"}'
    )

    for model in GROQ_MODELS:
        try:
            resp = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.1,
                    'max_tokens': 150,
                },
                timeout=5,
            )
            if resp.status_code == 200:
                text = resp.json()['choices'][0]['message']['content'].strip()
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    sev = (data.get('severity') or 'Low').capitalize()
                    if sev not in ('High', 'Medium', 'Low'):
                        sev = 'Low'
                    data['severity'] = sev
                    default_score = 2 if sev == 'Low' else (5 if sev == 'Medium' else 8)
                    try:
                        data['risk_score'] = max(1, min(10, int(data.get('risk_score', default_score))))
                    except (ValueError, TypeError):
                        data['risk_score'] = default_score
                    data['type'] = str(data.get('type') or 'Other').strip().title()
                    data['summary'] = str(data.get('summary') or f"{data['type']} incident recorded.")
                    return data
        except Exception:
            continue
    return None


def analyze_disaster(location: str, description: str) -> dict:
    """
    Returns:
        {
            type: str,
            severity: 'High' | 'Medium' | 'Low',
            risk_score: int (1-10),
            summary: str
        }
    """
    # 1. Try Groq AI model
    ai_result = _analyze_with_groq(location, description)
    if ai_result:
        return ai_result

    # 2. Fall back to smart rule-based analysis
    return _rule_based_analysis(description)
