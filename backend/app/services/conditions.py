# services/conditions.py — Combined fishing conditions for a harbour.
#
# Brings together the weather and tide services into a single FishingConditions
# object, and derives two human-readable outputs:
#   - recommended_time_window  e.g. "07:15–10:15 UTC (flood, 2.5 m swell)"
#   - conditions_summary       e.g. "Moderate breeze, slight swell on a spring flood"
#
# This module is the right place to add a third signal (e.g. water temperature,
# UV index, solunar table) without touching the weather or tide modules.

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.data.loader import Harbour
from app.services.tides import TideConditions, get_tides
from app.services.weather import WeatherConditions, get_weather

logger = logging.getLogger(__name__)


# ─── Result type ──────────────────────────────────────────────────────────────

@dataclass
class FishingConditions:
    """Aggregated conditions summary for the recommendation response."""

    wind_speed_knots: float
    wind_direction: str
    wind_description: str    # e.g. "Moderate breeze"
    wave_height_m: float
    sea_state: str           # e.g. "Slight"
    tide_phase: str          # e.g. "Flood"
    spring_or_neap: str      # "Spring" or "Neap"
    tidal_coefficient: float
    next_high_water: str     # "HH:MM UTC"
    recommended_time_window: str   # derived 3-hour window
    conditions_summary: str        # one-line human-readable description
    weather_source: str      # "open-meteo" | "mock"


# ─── Time window derivation ───────────────────────────────────────────────────

def _build_time_window(tides: TideConditions, weather: WeatherConditions) -> str:
    """Derive a 3-hour recommended fishing window around the next high water.

    Rule of thumb used by UK shore anglers:
      - Fish from 2 hours before high water to 1 hour after (the flood run).
    If conditions are rough (wave > 2.5 m), shift advice to calmer time.
    """
    # Parse the next HW time string back to a datetime for arithmetic.
    # The string is "HH:MM UTC"; we anchor it to today's date.
    utc_now = datetime.now(tz=timezone.utc)
    hw_time_str = tides.next_high_water  # e.g. "07:42 UTC"
    hw_h, hw_m = map(int, hw_time_str.replace(" UTC", "").split(":"))
    hw_dt = utc_now.replace(hour=hw_h, minute=hw_m, second=0, microsecond=0)
    if hw_dt < utc_now:
        hw_dt += timedelta(hours=12, minutes=25)  # use next tidal cycle

    if weather.wave_height_m > 2.5:
        # Rough conditions: recommend Low Water for sheltered marks instead
        lw_dt = hw_dt - timedelta(hours=6, minutes=12)  # LW is ~6h 12m before HW
        start = lw_dt - timedelta(hours=1)
        end   = lw_dt + timedelta(hours=2)
        note  = "low water (sheltered marks recommended)"
    else:
        # Standard: fish the flood run into high water
        start = hw_dt - timedelta(hours=2)
        end   = hw_dt + timedelta(hours=1)
        note  = f"flood into high water ({tides.spring_or_neap.lower()} tide)"

    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} UTC ({note})"


def _build_summary(weather: WeatherConditions, tides: TideConditions) -> str:
    """One-sentence conditions summary for display and logging."""
    return (
        f"{weather.wind_description} ({weather.wind_speed_knots:.0f} kn {weather.wind_direction}), "
        f"{weather.sea_state.lower()} swell ({weather.wave_height_m:.1f} m), "
        f"{tides.spring_or_neap.lower()} {tides.tide_phase.lower()} tide "
        f"(coefficient {tides.tidal_coefficient:.2f}). "
        f"Next HW {tides.next_high_water}."
    )


# ─── Public API ───────────────────────────────────────────────────────────────

def get_conditions(
    harbour: Harbour,
    *,
    today: Optional[date] = None,
    now: Optional[datetime] = None,
) -> FishingConditions:
    """Fetch weather and tides for a harbour and return combined conditions.

    Args:
        harbour:  The target harbour.
        today:    Override date for mock weather (tests).
        now:      Override UTC datetime for tidal calculations (tests).
    """
    weather = get_weather(harbour, today=today)
    tides   = get_tides(harbour.id, now=now)

    time_window = _build_time_window(tides, weather)
    summary     = _build_summary(weather, tides)

    logger.info(
        "Conditions for %s | %s | window: %s",
        harbour.name,
        summary,
        time_window,
    )

    return FishingConditions(
        wind_speed_knots=weather.wind_speed_knots,
        wind_direction=weather.wind_direction,
        wind_description=weather.wind_description,
        wave_height_m=weather.wave_height_m,
        sea_state=weather.sea_state,
        tide_phase=tides.tide_phase,
        spring_or_neap=tides.spring_or_neap,
        tidal_coefficient=tides.tidal_coefficient,
        next_high_water=tides.next_high_water,
        recommended_time_window=time_window,
        conditions_summary=summary,
        weather_source=weather.data_source,
    )
