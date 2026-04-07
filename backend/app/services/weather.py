# services/weather.py — Current wind and sea-state conditions for a harbour.
#
# Data source priority:
#   1. Open-Meteo forecast API  — free, no API key, ~1 km resolution.
#      Two lightweight calls are made in sequence:
#        a) api.open-meteo.com     → wind speed (knots) + direction
#        b) marine-api.open-meteo.com → wave height (m) + period (s)
#   2. Deterministic mock        — used when either API call fails (network
#      error, timeout, bad status).  Seeded by harbour ID + date so the same
#      harbour always produces the same "weather" for a given day, which keeps
#      tests predictable and avoids flaky behaviour in CI.
#
# Swapping to a different provider later only requires replacing _fetch_wind()
# and _fetch_waves(); everything above that stays the same.

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple

import httpx

from app.data.loader import Harbour

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_WIND_API  = "https://api.open-meteo.com/v1/forecast"
_WAVE_API  = "https://marine-api.open-meteo.com/v1/marine"
_TIMEOUT_S = 4.0  # seconds — short so a slow network doesn't hang a request


# ─── Result type ──────────────────────────────────────────────────────────────

@dataclass
class WeatherConditions:
    """Wind and sea-state at a harbour right now (or a best estimate)."""

    wind_speed_knots: float     # current wind speed
    wind_direction: str         # compass point: "SW", "NNE", etc.
    wind_description: str       # Beaufort plain-English description
    wave_height_m: float        # significant wave height in metres
    sea_state: str              # Douglas scale description
    data_source: str            # "open-meteo" | "mock"


# ─── Beaufort / Douglas helpers ───────────────────────────────────────────────

def _degrees_to_compass(degrees: float) -> str:
    """Convert 0–360° to a 16-point compass label."""
    labels = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    return labels[round(degrees / 22.5) % 16]


def _beaufort_description(knots: float) -> str:
    """Map wind speed in knots to a plain-English Beaufort description."""
    if knots < 1:
        return "Calm"
    if knots < 4:
        return "Light air"
    if knots < 7:
        return "Light breeze"
    if knots < 11:
        return "Gentle breeze"
    if knots < 17:
        return "Moderate breeze"
    if knots < 22:
        return "Fresh breeze"
    if knots < 28:
        return "Strong breeze"
    if knots < 34:
        return "Near gale"
    if knots < 41:
        return "Gale"
    return "Severe gale or stronger"


def _douglas_sea_state(wave_height_m: float) -> str:
    """Map significant wave height to a Douglas scale description."""
    if wave_height_m < 0.1:
        return "Glassy"
    if wave_height_m < 0.5:
        return "Smooth"
    if wave_height_m < 1.25:
        return "Slight"
    if wave_height_m < 2.5:
        return "Moderate"
    if wave_height_m < 4.0:
        return "Rough"
    if wave_height_m < 6.0:
        return "Very rough"
    return "High"


# ─── Open-Meteo API calls ─────────────────────────────────────────────────────

def _fetch_wind(lat: float, lon: float) -> Optional[Tuple[float, float]]:
    """Call Open-Meteo forecast API.  Returns (speed_knots, direction_degrees)."""
    try:
        resp = httpx.get(
            _WIND_API,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kn",
                "timezone": "Europe/London",
                "forecast_days": 1,
            },
            timeout=_TIMEOUT_S,
        )
        if resp.status_code == 200:
            current = resp.json()["current"]
            return float(current["wind_speed_10m"]), float(current["wind_direction_10m"])
    except Exception as exc:
        logger.debug("Open-Meteo wind fetch failed: %s", exc)
    return None


def _fetch_waves(lat: float, lon: float) -> Optional[Tuple[float, float]]:
    """Call Open-Meteo marine API.  Returns (wave_height_m, wave_period_s)."""
    try:
        resp = httpx.get(
            _WAVE_API,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "wave_height,wave_period",
                "timezone": "Europe/London",
                "forecast_days": 1,
            },
            timeout=_TIMEOUT_S,
        )
        if resp.status_code == 200:
            current = resp.json()["current"]
            return float(current["wave_height"]), float(current["wave_period"])
    except Exception as exc:
        logger.debug("Open-Meteo wave fetch failed: %s", exc)
    return None


# ─── Deterministic mock ───────────────────────────────────────────────────────

def _seeded_rng(harbour_id: str, today: date) -> random.Random:
    """Return a Random instance seeded by harbour + date.

    Same seed → same mock weather for a given harbour on a given day, which
    makes tests and offline demos reproducible without touching the network.
    """
    digest = hashlib.sha256(f"{harbour_id}:{today.isoformat()}".encode()).hexdigest()
    return random.Random(int(digest[:8], 16))


def _mock_weather(harbour: Harbour, today: date) -> WeatherConditions:
    """Generate plausible but deterministic weather for a harbour + date."""
    rng = _seeded_rng(harbour.id, today)

    wind_knots = round(rng.uniform(3, 22), 1)         # typical UK coastal range
    wind_dir_deg = rng.uniform(0, 360)
    # Wave height loosely correlated with wind (not physically exact, but realistic)
    base_wave = wind_knots * 0.06
    wave_height = round(max(0.1, base_wave + rng.uniform(-0.3, 0.3)), 2)

    return WeatherConditions(
        wind_speed_knots=wind_knots,
        wind_direction=_degrees_to_compass(wind_dir_deg),
        wind_description=_beaufort_description(wind_knots),
        wave_height_m=wave_height,
        sea_state=_douglas_sea_state(wave_height),
        data_source="mock",
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def get_weather(
    harbour: Harbour,
    *,
    today: Optional[date] = None,
) -> WeatherConditions:
    """Return current weather conditions for the given harbour.

    Tries Open-Meteo first; falls back to the deterministic mock on any error.
    Pass `today` to force a specific date (used in tests).
    """
    wind  = _fetch_wind(harbour.latitude, harbour.longitude)
    waves = _fetch_waves(harbour.latitude, harbour.longitude)

    if wind is not None and waves is not None:
        speed, direction = wind
        wave_h, _ = waves
        logger.debug(
            "Weather from Open-Meteo | %s | wind=%.1fkn %s | wave=%.1fm",
            harbour.name, speed, _degrees_to_compass(direction), wave_h,
        )
        return WeatherConditions(
            wind_speed_knots=round(speed, 1),
            wind_direction=_degrees_to_compass(direction),
            wind_description=_beaufort_description(speed),
            wave_height_m=round(wave_h, 2),
            sea_state=_douglas_sea_state(wave_h),
            data_source="open-meteo",
        )

    logger.info("Falling back to mock weather for %s", harbour.name)
    return _mock_weather(harbour, today or date.today())
