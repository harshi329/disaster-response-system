"""
Route Optimization Agent
Uses OpenRouteService (ORS) Directions API to get a real driving route
between two coordinates.

Flow:
  1. Geocode the disaster location to lat/lng via ORS Geocoding API
  2. Find the nearest relief shelter from a predefined list
  3. Call ORS Directions API for a real route with turn-by-turn distance + time
  4. If ORS is unavailable or API key not set → fall back to heuristic lookup

Get a free ORS API key at: https://openrouteservice.org/dev/#/signup
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

ORS_BASE       = 'https://api.openrouteservice.org'
ORS_GEOCODE    = f'{ORS_BASE}/geocode/search'
ORS_DIRECTIONS = f'{ORS_BASE}/v2/directions/driving-car'
TIMEOUT        = 8  # seconds

# ── Known relief shelters (lat, lng, name) ────────────────────────────────────
# Extend this list for your deployment area
RELIEF_SHELTERS = [
    (28.6139, 77.2090, 'Delhi Relief Center'),
    (28.7041, 77.1025, 'North Delhi Shelter'),
    (28.5355, 77.3910, 'Noida Emergency Camp'),
    (28.4595, 77.0266, 'Gurgaon Rescue Hub'),
    (19.0760, 72.8777, 'Mumbai Relief Shelter'),
    (13.0827, 80.2707, 'Chennai Emergency Center'),
    (12.9716, 77.5946, 'Bangalore Rescue Camp'),
    (17.3850, 78.4867, 'Hyderabad Relief Hub'),
]

# ── Static fallback table (used when ORS is unavailable) ─────────────────────
_STATIC_ROUTES = {
    'river road': {
        'waypoints':            ['River Road Station', 'Highway 4', 'Highland Shelter'],
        'estimated_time_mins':  12,
        'distance_km':          6.2,
        'notes':                'River Road bridge closed. Use Highway 4.',
    },
    'green park': {
        'waypoints':            ['Green Park Gate', 'Main Avenue', 'City Relief Center'],
        'estimated_time_mins':  8,
        'distance_km':          3.1,
        'notes':                'Main Avenue clear. Direct route available.',
    },
    'hill zone': {
        'waypoints':            ['Hill Zone Base', 'Mountain Road', 'Valley Shelter'],
        'estimated_time_mins':  25,
        'distance_km':          14.0,
        'notes':                'Mountain Road may have debris. Proceed with caution.',
    },
    'default': {
        'waypoints':            ['Disaster Site', 'Highway 1', 'Relief Shelter'],
        'estimated_time_mins':  15,
        'distance_km':          8.5,
        'notes':                'Avoid flooded underpasses. Use Highway 1 bypass.',
    },
}


def _api_key() -> str:
    return os.environ.get('OPENROUTESERVICE_API_KEY', '').strip()


def _geocode(location: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a location string using ORS Geocoding."""
    key = _api_key()
    if not key:
        return None
    try:
        resp = requests.get(
            ORS_GEOCODE,
            params={
                'api_key': key,
                'text':    location,
                'size':    1,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json().get('features', [])
        if not features:
            return None
        coords = features[0]['geometry']['coordinates']  # [lng, lat]
        return float(coords[1]), float(coords[0])
    except Exception as e:
        logger.warning('ORS geocode failed for "%s": %s', location, e)
        return None


def _nearest_shelter(lat: float, lng: float) -> tuple[float, float, str]:
    """Return the (lat, lng, name) of the closest shelter."""
    best     = RELIEF_SHELTERS[0]
    best_d   = float('inf')
    for s_lat, s_lng, s_name in RELIEF_SHELTERS:
        # Rough Euclidean distance (fine for choosing nearest)
        d = (lat - s_lat) ** 2 + (lng - s_lng) ** 2
        if d < best_d:
            best_d = d
            best   = (s_lat, s_lng, s_name)
    return best


def _ors_directions(
    origin_lat: float, origin_lng: float,
    dest_lat:   float, dest_lng:   float,
) -> dict | None:
    """Call ORS Directions API and return parsed result."""
    key = _api_key()
    if not key:
        return None
    try:
        resp = requests.post(
            ORS_DIRECTIONS,
            headers={'Authorization': key, 'Content-Type': 'application/json'},
            json={
                'coordinates': [
                    [origin_lng, origin_lat],
                    [dest_lng,   dest_lat  ],
                ],
                'instructions':     True,
                'language':         'en',
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data    = resp.json()
        segment = data['routes'][0]['segments'][0]
        steps   = segment.get('steps', [])

        # Build a human-readable waypoint list from step names
        waypoints = []
        for step in steps[:6]:  # cap at 6 steps
            name = step.get('name', '').strip()
            if name and name != '-':
                waypoints.append(name)
        if not waypoints:
            waypoints = ['Departure', 'Route', 'Destination']

        distance_m    = data['routes'][0]['summary']['distance']
        duration_s    = data['routes'][0]['summary']['duration']
        distance_km   = round(distance_m / 1000, 1)
        time_mins     = max(1, round(duration_s / 60))

        # Build advisory notes from ORS warnings if present
        warnings = data['routes'][0].get('warnings', [])
        notes    = warnings[0].get('message', '') if warnings else \
                   f'Real-time route via OpenRouteService. Distance: {distance_km} km.'

        return {
            'waypoints':           waypoints,
            'estimated_time_mins': time_mins,
            'distance_km':         distance_km,
            'notes':               notes,
            'source':              'OpenRouteService',
        }
    except Exception as e:
        logger.warning('ORS directions failed: %s', e)
        return None


def _static_fallback(location: str) -> dict:
    """Return a static heuristic route based on known location keywords."""
    loc_key = location.lower().strip()
    for key, val in _STATIC_ROUTES.items():
        if key != 'default' and key in loc_key:
            route = val.copy()
            route['source'] = 'static_fallback'
            return route
    route            = _STATIC_ROUTES['default'].copy()
    route['waypoints'] = [f'{location} Station', 'Highway 1', 'Relief Shelter']
    route['source']  = 'static_fallback'
    return route


# ── Public API ────────────────────────────────────────────────────────────────
def optimize_route(location: str, disaster_type: str) -> dict:
    """
    Returns:
        {
            origin:               str,
            destination:          str,
            waypoints:            list[str],
            estimated_time_mins:  int,
            distance_km:          float,
            notes:                str,
            route_summary:        str,
            source:               'OpenRouteService' | 'static_fallback',
        }
    """
    ors_result = None

    # ── Try real ORS routing ──────────────────────────────────────────────────
    if _api_key():
        coords = _geocode(location)
        if coords:
            origin_lat, origin_lng     = coords
            dest_lat, dest_lng, dest_name = _nearest_shelter(origin_lat, origin_lng)
            ors_result                 = _ors_directions(
                origin_lat, origin_lng, dest_lat, dest_lng
            )
            if ors_result:
                ors_result['destination'] = dest_name

    # ── Fall back to static table if ORS unavailable ──────────────────────────
    if not ors_result:
        ors_result = _static_fallback(location)
        ors_result['destination'] = ors_result['waypoints'][-1]

    return {
        'origin':               location,
        'destination':          ors_result['destination'],
        'waypoints':            ors_result['waypoints'],
        'estimated_time_mins':  ors_result['estimated_time_mins'],
        'distance_km':          ors_result['distance_km'],
        'notes':                ors_result['notes'],
        'route_summary':        ' → '.join(ors_result['waypoints']),
        'source':               ors_result.get('source', 'unknown'),
    }
