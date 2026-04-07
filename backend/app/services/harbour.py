# services/harbour.py — Finds nearby harbours for a given coordinate.
#
# Primary source: Overpass API (OpenStreetMap) — queries for harbours and
# marinas within a radius of the user's location.  Results are cached by
# ~55 km grid cell (0.5° rounding), but ONLY on success — failures are never
# cached so a retry after a transient 504 can still succeed.
#
# Fallback: when Overpass is unavailable the local harbours.json dataset
# is used so the app keeps working offline or under network issues.
#
# Distance threshold: if every candidate harbour is > MAX_USEFUL_DISTANCE_KM
# from the resolved location, the app is clearly outside its coverage area.
# nearest_harbours() returns the candidates with a flag so the recommend router
# can set used_fallback=True and surface a clear message to the user.

import logging
import math
import re
from typing import Dict, List, Optional, Tuple

import httpx

from app.data.loader import Harbour, get_harbour_by_id, get_harbours

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_EARTH_RADIUS_KM = 6371.0
_DEFAULT_HARBOUR_ID = "falmouth"

# Overpass primary + mirror — tried in order; mirror used on 504 / error.
_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
_OVERPASS_TIMEOUT_S  = 10.0
_SEARCH_RADIUS_M     = 100_000  # 100 km — used for fast seamark-only pass
_SEARCH_RADIUS_M_EXT = 200_000  # 200 km — used for full fallback pass when
                                # seamark pass returns empty (sparse coastal areas)

# If the nearest harbour is further than this, the location is outside useful
# coverage and we surface the fallback flag rather than silently recommending
# a harbour 5 000 km away.
MAX_USEFUL_DISTANCE_KM = 500.0

# Only cache successful (non-empty) Overpass responses.  A module-level dict
# is used instead of @lru_cache so we can skip caching empty results.
_OVERPASS_CACHE: Dict[Tuple[float, float], Tuple[Harbour, ...]] = {}


# ─── Haversine formula ────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two coordinates."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Overpass API ─────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _run_overpass_query(lat_r: float, lon_r: float) -> Optional[Tuple[Harbour, ...]]:
    """Try each Overpass endpoint in turn.  Returns None if all fail.

    Uses a two-pass strategy to handle dense urban areas (e.g. NYC) that time
    out when querying all harbour/marina tags at once:

      Pass 1 (fast): seamark:type=harbour + seamark:type=fishing_harbour only.
                     These entries are sparse so the query is lightweight and
                     reliably completes within the timeout even in dense cities.
      Pass 2 (full): if pass 1 returns nothing, run the broader query that also
                     includes bare 'harbour' and 'leisure=marina' tags, covering
                     sparsely-tagged coastlines that have no seamark data.
    """
    _seamark_query = (
        f"[out:json][timeout:9];\n"
        f"(\n"
        f'  node["seamark:type"="harbour"](around:{_SEARCH_RADIUS_M},{lat_r},{lon_r});\n'
        f'  node["seamark:type"="fishing_harbour"](around:{_SEARCH_RADIUS_M},{lat_r},{lon_r});\n'
        f");\n"
        f"out center;"
    )
    _full_query = (
        f"[out:json][timeout:9];\n"
        f"(\n"
        f'  node["harbour"](around:{_SEARCH_RADIUS_M_EXT},{lat_r},{lon_r});\n'
        f'  way["harbour"](around:{_SEARCH_RADIUS_M_EXT},{lat_r},{lon_r});\n'
        f'  node["seamark:type"="harbour"](around:{_SEARCH_RADIUS_M_EXT},{lat_r},{lon_r});\n'
        f'  node["seamark:type"="fishing_harbour"](around:{_SEARCH_RADIUS_M_EXT},{lat_r},{lon_r});\n'
        f'  node["leisure"="marina"](around:{_SEARCH_RADIUS_M_EXT},{lat_r},{lon_r});\n'
        f'  way["leisure"="marina"](around:{_SEARCH_RADIUS_M_EXT},{lat_r},{lon_r});\n'
        f");\n"
        f"out center;"
    )

    for query_label, query in [("seamark", _seamark_query), ("full", _full_query)]:
        for url in _OVERPASS_URLS:
            try:
                resp = httpx.post(url, data={"data": query}, timeout=_OVERPASS_TIMEOUT_S)
                if resp.status_code != 200:
                    logger.warning(
                        "Overpass %s (%s query) returned HTTP %s", url, query_label, resp.status_code
                    )
                    continue

                seen: set = set()
                seamark_harbours: List[Harbour] = []
                other_harbours: List[Harbour] = []
                for el in resp.json().get("elements", []):
                    tags = el.get("tags") or {}
                    name = tags.get("name", "").strip()
                    if not name or el["id"] in seen:
                        continue
                    seen.add(el["id"])
                    if el["type"] == "node":
                        lat, lon = el["lat"], el["lon"]
                    else:
                        center = el.get("center", {})
                        lat, lon = center.get("lat"), center.get("lon")
                        if lat is None:
                            continue
                    h = Harbour(
                        id=_slug(name), name=name,
                        latitude=float(lat), longitude=float(lon),
                    )
                    if "seamark:type" in tags:
                        seamark_harbours.append(h)
                    else:
                        other_harbours.append(h)

                harbours = seamark_harbours if seamark_harbours else other_harbours

                logger.info(
                    "Overpass (%s, %s query): %d harbours within %d km of (%.2f, %.2f)",
                    url.split("/")[2], query_label,
                    len(harbours), _SEARCH_RADIUS_M // 1000, lat_r, lon_r,
                )

                # Non-empty result: done — no need for the full query pass
                if harbours:
                    return tuple(harbours)

                # Empty seamark pass: break out of URL loop, try full query next
                if query_label == "seamark":
                    logger.debug(
                        "Seamark query empty for (%.2f, %.2f) — falling back to full query",
                        lat_r, lon_r,
                    )
                    break

                # Empty full pass: return empty (valid — no harbours in this area)
                return tuple(harbours)

            except Exception as exc:
                logger.warning("Overpass %s (%s query) error: %s", url, query_label, exc)

    return None   # all endpoints + both queries failed


def _fetch_overpass(lat_r: float, lon_r: float) -> Tuple[Harbour, ...]:
    """Fetch harbours near (lat_r, lon_r), using a success-only cache.

    Failures (network error, 504, all endpoints down) return an empty tuple
    but are NOT written to the cache — the next request will retry Overpass
    rather than serving a stale empty result forever.
    """
    key = (lat_r, lon_r)
    if key in _OVERPASS_CACHE:
        return _OVERPASS_CACHE[key]

    result = _run_overpass_query(lat_r, lon_r)
    if result is None:
        logger.warning("All Overpass endpoints failed for (%.2f, %.2f) — not caching", lat_r, lon_r)
        return ()

    # Only cache if the result is non-empty — an empty result might mean
    # "no harbours here" (valid, cache it) or "server 504" (transient, skip).
    # _run_overpass_query returns None on errors and a tuple (possibly empty)
    # on success, so empty tuples here represent genuine "no results" areas.
    _OVERPASS_CACHE[key] = result
    return result


# ─── Nearest harbour(s) ───────────────────────────────────────────────────────

def nearest_harbours(
    lat: float,
    lon: float,
    n: int = 5,
) -> Tuple[List[Tuple[Harbour, float]], bool]:
    """Return the n closest harbours sorted by distance and an out-of-range flag.

    Returns:
        (candidates, out_of_range)

        candidates   — list of (harbour, distance_km), nearest first
        out_of_range — True when the nearest harbour exceeds MAX_USEFUL_DISTANCE_KM,
                       meaning the location is outside the app's coverage area.
    """
    lat_r = round(lat * 2) / 2
    lon_r = round(lon * 2) / 2

    harbours: List[Harbour] = list(_fetch_overpass(lat_r, lon_r))

    if not harbours:
        logger.info("Overpass returned no results — using local harbour dataset")
        harbours = list(get_harbours())

    if not harbours:
        raise ValueError("No harbours available from any source")

    scored = [(h, haversine_km(lat, lon, h.latitude, h.longitude)) for h in harbours]
    scored.sort(key=lambda x: x[1])
    candidates = scored[:max(1, n)]

    nearest_dist = candidates[0][1]
    out_of_range = nearest_dist > MAX_USEFUL_DISTANCE_KM

    if out_of_range:
        logger.warning(
            "Nearest harbour (%s) is %.0f km away — location likely outside coverage area",
            candidates[0][0].name, nearest_dist,
        )

    return candidates, out_of_range


def nearest_harbour(lat: float, lon: float) -> Tuple[Harbour, float]:
    """Return the single nearest harbour and its distance in km."""
    candidates, _ = nearest_harbours(lat, lon, n=1)
    return candidates[0]


def default_harbour() -> Tuple[Harbour, float]:
    """Return the fallback harbour when location resolution fails entirely.

    Distance is -1.0 — a sentinel meaning 'distance unknown'.
    """
    harbour = get_harbour_by_id(_DEFAULT_HARBOUR_ID)
    if harbour is None:
        raise RuntimeError(f"Default harbour '{_DEFAULT_HARBOUR_ID}' missing from dataset")
    return harbour, -1.0
