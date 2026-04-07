# services/postcode.py — Resolves a UK postcode to (latitude, longitude).
#
# Resolution order (first success wins):
#   1. Local seed map  — instant, no network, covers common UK outward codes
#   2. postcodes.io    — free public API, no key required
#   3. Caller receives None and should apply a safe fallback
#
# The local seed map uses *outward codes* (the part before the space, e.g.
# "TR1" from "TR1 1AA") so a single entry covers the whole postcode district.

import logging
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# ─── Local seed map ───────────────────────────────────────────────────────────
# Maps outward code → (latitude, longitude).
# Covers the harbour areas in our dataset plus major population centres.
# Enough to work entirely offline for demos and tests.

_SEED: dict = {
    # ── Cornwall & Devon ──────────────────────────────────────────────────────
    "TR1":  (50.2632, -5.0510),   # Truro
    "TR11": (50.1528, -5.0664),   # Falmouth
    "TR18": (50.1013, -5.5454),   # Penzance / Newlyn
    "PL13": (50.3520, -4.4570),   # Looe
    "PL28": (50.5387, -4.9388),   # Padstow
    "PL1":  (50.3750, -4.1427),   # Plymouth
    "EX1":  (50.7257, -3.5310),   # Exeter
    "TQ5":  (50.3943, -3.5140),   # Brixham
    "TQ6":  (50.3516, -3.5768),   # Dartmouth
    # ── Dorset & Hampshire ────────────────────────────────────────────────────
    "DT4":  (50.6115, -2.4520),   # Weymouth
    "BH15": (50.7143, -1.9872),   # Poole
    "SO14": (50.9097, -1.4044),   # Southampton
    "PO1":  (50.7989, -1.0919),   # Portsmouth
    # ── Sussex & Kent ────────────────────────────────────────────────────────
    "BN1":  (50.8229, -0.1363),   # Brighton
    "BN2":  (50.8129, -0.0993),   # Brighton Marina
    "TN1":  (51.1279,  0.2639),   # Tunbridge Wells
    "CT1":  (51.2802,  1.0789),   # Canterbury
    "ME1":  (51.3893,  0.5074),   # Medway / Rochester
    # ── Essex & Suffolk ──────────────────────────────────────────────────────
    "CO1":  (51.8959,  0.8919),   # Colchester
    "IP1":  (52.0567,  1.1482),   # Ipswich
    "CO12": (51.8548,  1.2443),   # Harwich
    # ── Norfolk & Lincolnshire ───────────────────────────────────────────────
    "NR1":  (52.6309,  1.2974),   # Norwich
    "PE25": (53.1584,  0.3413),   # Skegness
    # ── Yorkshire ────────────────────────────────────────────────────────────
    "HU1":  (53.7446, -0.3352),   # Hull
    "YO11": (54.2797, -0.3893),   # Scarborough
    "YO15": (54.0992, -0.1698),   # Bridlington
    "YO22": (54.4877, -0.6140),   # Whitby
    "YO1":  (53.9623, -1.0816),   # York
    "LS1":  (53.7997, -1.5492),   # Leeds
    # ── North East ───────────────────────────────────────────────────────────
    "NE1":  (54.9783, -1.6178),   # Newcastle
    "SR1":  (54.9061, -1.3839),   # Sunderland
    "TS1":  (54.5740, -1.2343),   # Middlesbrough
    # ── Scotland (east coast) ────────────────────────────────────────────────
    "TD14": (55.8744, -2.0897),   # Eyemouth
    "EH1":  (55.9533, -3.1883),   # Edinburgh
    "EH42": (56.0026, -2.5220),   # Dunbar
    "G1":   (55.8617, -4.2583),   # Glasgow
    "KY10": (56.2232, -2.6985),   # Anstruther (East Neuk of Fife)
    "KY1":  (56.1124, -3.1593),   # Kirkcaldy
    "DD1":  (56.4620, -2.9707),   # Dundee
    "DD11": (56.5614, -2.5884),   # Arbroath
    "AB11": (57.1497, -2.0943),   # Aberdeen city
    "AB39": (56.9634, -2.2032),   # Stonehaven
    "AB42": (57.5049, -1.7834),   # Peterhead
    "AB43": (57.6937, -2.0042),   # Fraserburgh
    "AB44": (57.6637, -2.4987),   # Macduff / Banff
    "AB45": (57.6637, -2.5300),   # Banff area
    # ── Scotland (north & west) ──────────────────────────────────────────────
    "IV1":  (57.4778, -4.2247),   # Inverness
    "IV26": (57.8970, -5.1590),   # Ullapool
    "PA34": (56.4149, -5.4714),   # Oban
    "PH41": (57.0058, -5.8282),   # Mallaig
    "KW1":  (58.4369, -3.0836),   # Wick / Caithness
    "HS1":  (58.2086, -6.3857),   # Stornoway
    # ── Wales ────────────────────────────────────────────────────────────────
    "CF10": (51.4816, -3.1791),   # Cardiff
    "SA1":  (51.6214, -3.9436),   # Swansea
    "SA62": (51.8411, -5.0688),   # Pembroke Dock / Milford Haven
    "LL30": (53.3266, -3.8270),   # Llandudno
    # ── London & surrounds ───────────────────────────────────────────────────
    "EC1":  (51.5194, -0.0990),   # City of London
    "SW1":  (51.4993, -0.1345),   # Westminster
    "W1":   (51.5074, -0.1278),   # West End
    "E1":   (51.5150, -0.0722),   # East London
    # ── Islands ──────────────────────────────────────────────────────────────
    "IM1":  (54.1528, -4.4866),   # Isle of Man
    "GY1":  (49.4657, -2.5853),   # Guernsey
    "JE1":  (49.1852, -2.1100),   # Jersey
}


def _outward_code(postcode: str) -> str:
    """Extract the outward code (part before the space) from a postcode.

    "TR1 1AA" → "TR1"
    "TR11 3JT" → "TR11"
    "sw1a2aa"  → "SW1A"  (handles no-space input)
    """
    normalised = postcode.strip().upper()
    if " " in normalised:
        return normalised.split()[0]
    # No space — inward code is always 3 characters; outward is the remainder
    return normalised[:-3] if len(normalised) > 3 else normalised


def _lookup_seed(postcode: str) -> Optional[Tuple[float, float]]:
    """Try the local seed map.  Returns None when the outward code is absent."""
    outward = _outward_code(postcode)
    coords = _SEED.get(outward)
    if coords:
        logger.debug("Postcode %s resolved from seed map (%s)", postcode, outward)
    return coords


def _lookup_api(postcode: str) -> Optional[Tuple[float, float]]:
    """Query postcodes.io — completely free, no API key.

    Returns None on any error (network failure, unknown postcode, timeout).
    Keeps a short timeout so a slow network never blocks a request for long.
    """
    url = f"https://api.postcodes.io/postcodes/{postcode.replace(' ', '%20')}"
    try:
        response = httpx.get(url, timeout=3.0)
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", {})
            lat = result.get("latitude")
            lon = result.get("longitude")
            if lat is not None and lon is not None:
                logger.debug("Postcode %s resolved via postcodes.io", postcode)
                return float(lat), float(lon)
        else:
            logger.debug(
                "postcodes.io returned %s for postcode %s",
                response.status_code,
                postcode,
            )
    except Exception as exc:  # network error, timeout, parse error
        logger.debug("postcodes.io lookup failed for %s: %s", postcode, exc)
    return None


def resolve_postcode(postcode: str) -> Optional[Tuple[float, float]]:
    """Resolve a UK postcode to (latitude, longitude).

    Tries the local seed map first (fast, no network), then falls back to
    the postcodes.io public API.  Returns None if the postcode cannot be
    resolved by either method — callers should handle this with a safe default.
    """
    return _lookup_seed(postcode) or _lookup_api(postcode)
