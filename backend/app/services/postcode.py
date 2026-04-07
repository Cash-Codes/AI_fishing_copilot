# services/postcode.py — Resolves a UK postcode to (latitude, longitude).
#
# Uses the postcodes.io public API — free, no API key required.
# Returns None if the postcode is unknown or the API is unreachable.

import logging
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_POSTCODES_IO_URL = "https://api.postcodes.io/postcodes/{}"
_TIMEOUT_S = 4.0


def _outward_code(postcode: str) -> str:
    """Extract the outward code from a full postcode.

    "TR1 1AA"  → "TR1"
    "TR11 3JT" → "TR11"
    "sw1a2aa"  → "SW1A"
    """
    normalised = postcode.strip().upper()
    if " " in normalised:
        return normalised.split()[0]
    return normalised[:-3] if len(normalised) > 3 else normalised


def resolve_postcode(postcode: str) -> Optional[Tuple[float, float]]:
    """Resolve a UK postcode to (latitude, longitude) via postcodes.io.

    Returns None on network error, timeout, or unknown postcode.
    """
    url = _POSTCODES_IO_URL.format(postcode.strip().replace(" ", "%20"))
    try:
        response = httpx.get(url, timeout=_TIMEOUT_S)
        if response.status_code == 200:
            result = response.json().get("result", {})
            lat = result.get("latitude")
            lon = result.get("longitude")
            if lat is not None and lon is not None:
                logger.debug("Postcode %s resolved via postcodes.io", postcode)
                return float(lat), float(lon)
        else:
            logger.debug(
                "postcodes.io returned %s for %s", response.status_code, postcode
            )
    except Exception as exc:
        logger.debug("postcodes.io lookup failed for %s: %s", postcode, exc)
    return None
