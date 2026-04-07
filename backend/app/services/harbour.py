# services/harbour.py — Finds the nearest harbour to a given coordinate.
#
# Uses the Haversine formula which gives the great-circle distance between two
# points on a sphere.  The result is accurate to within ~0.5% for the short
# distances involved in UK coastal navigation (well within our needs).

import math
from typing import Tuple

from app.data.loader import Harbour, get_harbour_by_id, get_harbours

# ─── Constants ────────────────────────────────────────────────────────────────

_EARTH_RADIUS_KM = 6371.0

# Safe default used when a postcode cannot be resolved at all.
# Falmouth sits roughly in the middle of the UK's south-west coastline and is
# a sensible fallback for an app focused on UK sea fishing.
_DEFAULT_HARBOUR_ID = "falmouth"


# ─── Haversine formula ────────────────────────────────────────────────────────

def haversine_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Return the great-circle distance in kilometres between two coordinates.

    All angles are expected in decimal degrees (e.g. 50.1528, -5.0664).

    The formula:
        a = sin²(Δlat/2) + cos(lat1) · cos(lat2) · sin²(Δlon/2)
        c = 2 · atan2(√a, √(1−a))
        d = R · c
    """
    # Convert degrees → radians
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


# ─── Nearest harbour ──────────────────────────────────────────────────────────

def nearest_harbour(lat: float, lon: float) -> Tuple[Harbour, float]:
    """Return the nearest harbour and its distance in km from the given point.

    Iterates over all harbours in the dataset and picks the one with the
    smallest Haversine distance.  The dataset is small (< 20 harbours) so a
    linear scan is fast enough — no spatial index needed for MVP.

    Returns:
        (harbour, distance_km)
    """
    harbours = get_harbours()

    if not harbours:
        raise ValueError("No harbours available in dataset")

    best_harbour = harbours[0]
    best_dist = haversine_km(lat, lon, harbours[0].latitude, harbours[0].longitude)

    for harbour in harbours[1:]:
        dist = haversine_km(lat, lon, harbour.latitude, harbour.longitude)
        if dist < best_dist:
            best_dist = dist
            best_harbour = harbour

    return best_harbour, best_dist


def default_harbour() -> Tuple[Harbour, float]:
    """Return the fallback harbour used when postcode resolution fails.

    The distance is returned as -1.0 to indicate it is not a real measurement.
    """
    harbour = get_harbour_by_id(_DEFAULT_HARBOUR_ID)
    if harbour is None:
        raise RuntimeError(f"Default harbour '{_DEFAULT_HARBOUR_ID}' missing from dataset")
    return harbour, -1.0
