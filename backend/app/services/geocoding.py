# services/geocoding.py — Resolve any location string to (latitude, longitude).
#
# Accepts two formats:
#
#   UK postcodes  — "TR1 1AA", "BH15 1HJ", "ab45 2nj"
#                   → postcodes.io (free, no key required)
#
#   Place names   — "Falmouth", "New York", "Delhi", "London Bridge"
#                   → Nominatim / OpenStreetMap (free, no key required)
#
# Detection is regex-based: anything that matches the UK postcode pattern is
# sent to postcodes.io; everything else goes to Nominatim.
#
# Both APIs are free, require no authentication, and have generous rate limits
# for a low-traffic web app.  Nominatim asks for a descriptive User-Agent; we
# set one so our requests are not rejected as bots.
#
# Returns None when neither API can resolve the input.  Callers should handle
# this with a safe default (e.g. fallback harbour).

import logging
import re
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Full UK postcode pattern  e.g. "TR1 1AA", "SW1A 2AA", "BH15 1HJ"
# Outward-only also matches e.g. "TR1", "SW1A" — postcodes.io handles both
_UK_POSTCODE_RE = re.compile(
    r"^[A-Z]{1,2}[0-9][0-9A-Z]?(\s*[0-9][A-Z]{2})?$",
    re.IGNORECASE,
)

_POSTCODES_IO = "https://api.postcodes.io/postcodes/{}"
_NOMINATIM    = "https://nominatim.openstreetmap.org/search"
_TIMEOUT_S    = 5.0

# Nominatim requires a non-empty User-Agent identifying the application
_HEADERS = {"User-Agent": "AI-Fishing-Copilot/1.0 (github.com/Cash-Codes)"}


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _is_uk_postcode(query: str) -> bool:
    return bool(_UK_POSTCODE_RE.match(query.strip()))


def _resolve_postcode(postcode: str) -> Optional[Tuple[float, float]]:
    """Call postcodes.io for a UK postcode.  Returns None on any failure."""
    url = _POSTCODES_IO.format(postcode.strip().replace(" ", "%20"))
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT_S)
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            lat, lon = result.get("latitude"), result.get("longitude")
            if lat is not None and lon is not None:
                logger.debug("Postcode %r → %.4f, %.4f (postcodes.io)", postcode, lat, lon)
                return float(lat), float(lon)
        else:
            logger.debug("postcodes.io: HTTP %s for %r", resp.status_code, postcode)
    except Exception as exc:
        logger.debug("postcodes.io failed for %r: %s", postcode, exc)
    return None


def _resolve_place(query: str) -> Optional[Tuple[float, float]]:
    """Call Nominatim for a place name.  Returns None on any failure.

    Fetches up to 5 candidates and picks the one with the highest importance
    score.  Nominatim's default ordering can return low-importance entries first
    for queries without word boundaries (e.g. 'newyork' → Tokyo shop before NYC).
    """
    try:
        resp = httpx.get(
            _NOMINATIM,
            params={"q": query, "format": "json", "limit": 5},
            headers=_HEADERS,
            timeout=_TIMEOUT_S,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                best = max(results, key=lambda r: float(r.get("importance", 0)))
                lat = float(best["lat"])
                lon = float(best["lon"])
                display = best.get("display_name", query)
                logger.info("Place %r → %.4f, %.4f (%s)", query, lat, lon, display)
                return lat, lon
        else:
            logger.debug("Nominatim: HTTP %s for %r", resp.status_code, query)
    except Exception as exc:
        logger.debug("Nominatim failed for %r: %s", query, exc)
    return None


# ─── Public API ───────────────────────────────────────────────────────────────

def resolve_location(query: str) -> Optional[Tuple[float, float]]:
    """Resolve a postcode or place name to (latitude, longitude).

    Examples that all work:
        "TR1 1AA"       → UK postcode   → postcodes.io
        "BH15"          → outward code  → postcodes.io
        "Falmouth"      → place name    → Nominatim
        "New York"      → city          → Nominatim
        "Delhi, India"  → city          → Nominatim

    Returns None if the location cannot be resolved — callers should handle
    this gracefully (e.g. fall back to a default harbour).
    """
    q = query.strip()
    if _is_uk_postcode(q):
        logger.info("Resolving %r as UK postcode", q)
        return _resolve_postcode(q)

    logger.info("Resolving %r as place name via Nominatim", q)
    return _resolve_place(q)
