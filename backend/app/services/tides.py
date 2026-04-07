# services/tides.py — Estimated tide conditions for a harbour.
#
# Why no external API?  There is no reliable *free* UK tide API.  The UKHO
# (Admiralty) API and WorldTides both require paid keys.  What we *can* do
# accurately without any network call:
#
#   1. Spring / neap classification — derived from lunar age, which is an
#      exact astronomical calculation (accurate to < 1 day).
#
#   2. Tidal coefficient (strength 0–1) — cosine of the lunar phase gives
#      a smooth, physically-motivated strength curve.
#
#   3. Tide phase (flood / HW slack / ebb / LW slack) — derived from "hours
#      since high water".  We calculate this using a harbour-specific
#      port establishment time (HWF&C — High Water Full and Change) sourced
#      from Admiralty Tide Tables, then advancing by ~50 minutes per lunar
#      day (the lag introduced by the moon's orbital motion).
#
# Accuracy:  the phase estimate is typically within ±1 hour of reality for
# a given day.  Good enough to advise "fish on the flood" but not for
# navigation.  The data_source field is always "calculated" to be transparent.
#
# Swapping to a live API later:  replace `_calculate_tide_phase()` with a
# call to the preferred provider; everything above that stays the same.

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

# ─── Harbour establishment times (HWF&C) ─────────────────────────────────────
#
# "Port establishment" is the time of high water at that port on the day of a
# new moon, expressed as hours after midnight UTC.  Source: Admiralty Tide
# Tables (simplified to nearest 15 minutes for our harbours).
#
# These are the constants that make harbour-specific tidal timing possible
# without an external API.  A future iteration can refine them or replace them
# with real harmonic constants.

_PORT_ESTABLISHMENT: Dict[str, float] = {
    "falmouth":    6.50,   # HW ~06:30 UTC at new moon
    "newlyn":      6.25,
    "padstow":     6.00,
    "looe":        6.25,
    "brixham":     4.75,
    "dartmouth":   4.75,
    "weymouth":    1.25,   # Weymouth has a double HW pattern (Solent effect)
    "poole":       1.50,
    "brighton":   23.50,   # just before midnight
    "whitby":      5.25,
    "scarborough": 4.75,
    "eyemouth":    3.00,
    "anstruther":  3.50,
    "macduff":     2.25,   # Moray Firth
    "peterhead":   1.25,
    "oban":        1.25,   # West coast — complex, simplified here
    "ullapool":    5.75,
    "wick":        3.75,
}

_DEFAULT_ESTABLISHMENT = 6.0   # fallback for any harbour not in the table
_TIDAL_PERIOD_H = 12.417       # M2 semidiurnal period in hours (12h 25min)
_TIDAL_ADVANCE_PER_DAY = 50 / 60  # minutes → hours: moon advances ~50 min/day
_LUNAR_CYCLE_DAYS = 29.53058868
_KNOWN_NEW_MOON = date(2000, 1, 6)  # reference new moon (J2000)


# ─── Result type ──────────────────────────────────────────────────────────────

@dataclass
class TideConditions:
    """Estimated tidal state at a harbour."""

    tide_phase: str              # "Flood", "High Water", "Ebb", or "Low Water"
    spring_or_neap: str          # "Spring" or "Neap"
    tidal_coefficient: float     # 0–1 (1.0 = maximum spring, 0.0 = maximum neap)
    next_high_water: str         # "HH:MM UTC" — approximate
    hours_to_next_hw: float      # hours until the next high water
    data_source: str             # always "calculated"


# ─── Internal helpers ─────────────────────────────────────────────────────────

def lunar_age(today: date) -> float:
    """Return the age of the moon in days (0–29.53).

    Uses the known-new-moon reference (2000-01-06) and the mean lunar cycle.
    Accurate to within a few hours for the spring/neap classification needed.
    """
    days_since_ref = (today - _KNOWN_NEW_MOON).days
    return days_since_ref % _LUNAR_CYCLE_DAYS


def tidal_coefficient(age: float) -> float:
    """Smooth 0–1 strength curve.

    Peaks at 1.0 at new moon (age ≈ 0) and full moon (age ≈ 14.77), and
    reaches its minimum of 0.0 at the quarter moons (age ≈ 7.38 / 22.15).
    Physically motivated: tidal range ∝ |cos(phase)|.
    """
    phase_rad = (age / (_LUNAR_CYCLE_DAYS / 2)) * math.pi
    return round(abs(math.cos(phase_rad)), 3)


def _hours_since_last_hw(harbour_id: str, now_utc: datetime) -> float:
    """Estimate hours elapsed since the last high water at the given port.

    Returns a value in [0, _TIDAL_PERIOD_H).
    """
    establishment = _PORT_ESTABLISHMENT.get(harbour_id, _DEFAULT_ESTABLISHMENT)
    age = lunar_age(now_utc.date())

    # High water advances ~50 minutes per lunar day from the establishment time.
    # We take the result modulo one tidal period to get the first HW of the day.
    hw0 = (establishment + age * _TIDAL_ADVANCE_PER_DAY) % _TIDAL_PERIOD_H

    hours_now = now_utc.hour + now_utc.minute / 60.0

    # Find where we are in the current tidal cycle by checking both HW events
    # in the day (hw0 and hw0 + 12.417h) and taking the most recent one.
    candidates = [hw0, hw0 + _TIDAL_PERIOD_H, hw0 - _TIDAL_PERIOD_H]
    elapsed_options = [hours_now - hw for hw in candidates if 0 <= hours_now - hw < _TIDAL_PERIOD_H]

    return elapsed_options[0] if elapsed_options else (hours_now - hw0) % _TIDAL_PERIOD_H


def _phase_label(hours_since_hw: float) -> str:
    """Map hours-since-HW to a tide phase label.

    One full cycle (12h 25min = 12.417h):
       0.0 – 1.0h  →  High Water slack  (water barely moving)
       1.0 – 5.7h  →  Ebb tide          (water falling)
       5.7 – 7.0h  →  Low Water slack
       7.0 – 12.4h →  Flood tide        (water rising)
    """
    if hours_since_hw < 1.0:
        return "High Water"
    if hours_since_hw < 5.7:
        return "Ebb"
    if hours_since_hw < 7.0:
        return "Low Water"
    return "Flood"


def _next_hw_time(harbour_id: str, now_utc: datetime) -> Tuple[str, float]:
    """Return (HH:MM UTC string, hours_until) for the next high water."""
    hours_since = _hours_since_last_hw(harbour_id, now_utc)
    hours_until = _TIDAL_PERIOD_H - hours_since
    next_hw = now_utc + timedelta(hours=hours_until)
    return next_hw.strftime("%H:%M UTC"), round(hours_until, 2)


# ─── Public API ───────────────────────────────────────────────────────────────

def get_tides(
    harbour_id: str,
    *,
    now: Optional[datetime] = None,
) -> TideConditions:
    """Return estimated tidal conditions at the given harbour.

    Args:
        harbour_id:  The harbour's id string (matches harbours.json).
        now:         Override current UTC time — used in tests for determinism.

    Data source is always "calculated" (no network call).
    """
    utc_now = now or datetime.now(tz=timezone.utc)
    age = lunar_age(utc_now.date())
    coeff = tidal_coefficient(age)

    spring_neap = "Spring" if coeff >= 0.5 else "Neap"
    hours_since = _hours_since_last_hw(harbour_id, utc_now)
    phase = _phase_label(hours_since)
    hw_str, hours_to_hw = _next_hw_time(harbour_id, utc_now)

    return TideConditions(
        tide_phase=phase,
        spring_or_neap=spring_neap,
        tidal_coefficient=coeff,
        next_high_water=hw_str,
        hours_to_next_hw=hours_to_hw,
        data_source="calculated",
    )
