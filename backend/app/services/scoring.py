# services/scoring.py — Recommendation confidence scoring engine.
#
# Produces a single normalised score in [0, 1] from three independent signals:
#   1. Distance   — how close the harbour is to the user's postcode
#   2. Species    — whether the harbour is known for the target fish this season
#   3. Preference — the user's stated optimisation goal weights the two signals
#
# Design principles:
#   - Each signal is scored independently in [0, 1].
#   - The final score is a weighted sum of the two signals; weights sum to 1.0
#     so the output is always in [0, 1] without extra clamping.
#   - All numbers are chosen to be defensible and easy to explain to a user
#     ("your score is low because Whitby is 350 km away and it's the wrong
#      season for Bass").
#   - The `today` argument is injectable so tests are fully deterministic
#     without mocking datetime.

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from app.data.loader import Harbour, get_species_by_name
from app.services.conditions import FishingConditions

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Distance (km) at which the distance component reaches zero.
# At 100 km the score is 0.5; anything ≥ 200 km scores 0.
# Trade-off: a higher ceiling would reward distant harbours less harshly, but
# for a UK sea-fishing app most users won't travel more than 100 km so this
# feels about right for MVP.
_MAX_DISTANCE_KM = 200.0

# How each preference shifts the balance between distance and species signals.
# Tuple layout: (distance_weight, species_weight).  Must sum to 1.0.
#
# "closest"           → the user just wants the nearest harbour; species is
#                       a secondary concern.
# "best-chance"       → optimise for species match and season; distance
#                       matters less.
# "calmer-conditions" → ideally we'd weight a swell/wind score here, but we
#                       don't have weather data yet.  Equal weights are honest;
#                       a future iteration can add a third weather signal.
_PREFERENCE_WEIGHTS: Dict[str, Tuple[float, float]] = {
    "closest":           (0.80, 0.20),
    "best-chance":       (0.35, 0.65),
    "calmer-conditions": (0.50, 0.50),
}
_DEFAULT_WEIGHTS: Tuple[float, float] = (0.50, 0.50)

# Month names used when parsing best_season strings such as "May–October".
_MONTH_NAMES: Dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


# ─── Harbour-selection constants ─────────────────────────────────────────────

# Weights used by select_harbour() to rank candidate harbours.
# These are distinct from _PREFERENCE_WEIGHTS (which control the confidence
# score shown to the user).  Selection weights determine WHICH harbour is
# picked; confidence weights determine HOW SURE we are about that pick.
_SELECT_WEIGHTS: Dict[str, Tuple[float, float, float]] = {
    # (proximity, calm, fishing_quality)
    "closest":           (0.85, 0.15, 0.00),
    "calmer-conditions": (0.30, 0.70, 0.00),
    "best-chance":       (0.25, 0.00, 0.75),
}
_SELECT_DEFAULT: Tuple[float, float, float] = (0.40, 0.20, 0.40)


# ─── Public result type ───────────────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    """Transparent record of how the final score was computed.

    Storing the individual signals and weights makes it easy to:
      - explain the score to the user in plain English
      - write precise unit tests
      - debug why a particular recommendation scored unexpectedly
    """

    distance_score: float    # 0–1: 1.0 = right next door, 0.0 = ≥ 200 km away
    species_score: float     # 0–1: 1.0 = known for species + in season
    distance_weight: float   # share of final score driven by distance
    species_weight: float    # share of final score driven by species/season
    confidence_score: float  # weighted sum — the number shown to the user


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _distance_score(distance_km: float) -> float:
    """Linear decay from 1.0 at 0 km to 0.0 at _MAX_DISTANCE_KM.

    Linear was chosen over exponential decay because it is easier to explain:
    "every 2 km further costs 0.01 on your score".  The sentinel value -1.0
    (used when the postcode could not be resolved) maps to 0.0.
    """
    if distance_km < 0:
        return 0.0  # -1.0 sentinel from default_harbour() — unknown distance
    return max(0.0, 1.0 - distance_km / _MAX_DISTANCE_KM)


def _parse_season(best_season: str) -> Optional[Tuple[int, int]]:
    """Parse a season string into a (start_month, end_month) tuple.

    Returns None for year-round species (caller treats every month as valid).

    Examples:
        "May–October"               → (5, 10)
        "October–March"             → (10, 3)   ← wraps around year-end
        "Year-round (peak Jul–Sep)" → None
    """
    lower = best_season.lower()
    if "year" in lower:
        return None  # year-round; don't penalise any month

    # Find every month name and its position in the string so we preserve order.
    positions = [
        (lower.find(name), num)
        for name, num in _MONTH_NAMES.items()
        if name in lower
    ]
    positions.sort()  # ascending by character position

    if len(positions) >= 2:
        return positions[0][1], positions[-1][1]  # (first month found, last month found)
    if len(positions) == 1:
        return positions[0][1], positions[0][1]   # single-month season
    return None


def _is_in_season(best_season: str, month: int) -> bool:
    """Return True when `month` falls within a species' best season.

    Handles seasons that wrap around the calendar year (e.g. October–March).
    """
    bounds = _parse_season(best_season)
    if bounds is None:
        return True  # year-round species

    start, end = bounds
    if start <= end:
        # Normal range: May–October → months 5, 6, 7, 8, 9, 10
        return start <= month <= end
    else:
        # Wrap-around range: October–March → 10, 11, 12, 1, 2, 3
        return month >= start or month <= end


def _species_score(harbour: Harbour, species_name: Optional[str], month: int) -> float:
    """Score how well this harbour suits the requested species this month.

    Scoring bands:
        0.5  — no species requested (neutral; neither helps nor hurts)
        0.1  — harbour not known for species AND out of season
        0.3  — species active this season but harbour not known for it
        0.6  — harbour is known for species but it's the wrong time of year
        1.0  — harbour is known for species AND we're in the best season

    The harbour match is a simple substring check on `short_description`.
    This is fast, requires no extra data, and works well because the
    descriptions were written to name the species each harbour is famous for.
    A future iteration could use a structured species-harbour mapping.
    """
    if not species_name:
        return 0.5

    harbour_knows_species = species_name.lower() in harbour.short_description.lower()

    species_data = get_species_by_name(species_name)
    # If the species isn't in our dataset we assume it's always in season
    # rather than penalising the score for a data gap.
    in_season = _is_in_season(species_data.best_season, month) if species_data else True

    if harbour_knows_species and in_season:
        return 1.0
    if harbour_knows_species and not in_season:
        return 0.6   # right place, wrong time of year
    if in_season:
        return 0.3   # good season but this harbour isn't known for this fish
    return 0.1       # harbour not a match and out of season


# ─── Selection signal helpers ────────────────────────────────────────────────

def _proximity_score(distance_km: float) -> float:
    """Smooth hyperbolic decay: 0 km → 1.0, 20 km → 0.5, 100 km → 0.17.

    Softer than the linear _distance_score so a harbour that is 20 km further
    but significantly calmer or more species-appropriate can still win.
    """
    if distance_km < 0:
        return 0.0
    return 1.0 / (1.0 + distance_km / 20.0)


def _calm_score(wave_m: float, wind_kn: float) -> float:
    """0–1, higher = calmer sea.  Wave height and wind speed equally weighted.

    Thresholds match the Douglas scale / Beaufort scale for practical fishing:
      wave 4 m+ or wind 32 kn+ → score approaches 0 (unsafe / too rough)
    """
    wave = max(0.0, 1.0 - wave_m / 4.0)
    wind = max(0.0, 1.0 - wind_kn / 32.0)
    return (wave + wind) / 2.0


def _fishing_quality_score(tide_phase: str, spring_or_neap: str) -> float:
    """0–1 tidal quality for fishing.  Flood/spring tide = best opportunity.

    Flood tide concentrates baitfish over structure; spring tides produce
    stronger currents that trigger feeding.
    """
    phase_score = {
        "Flood":       1.00,
        "High Water":  0.85,
        "Ebb":         0.55,
        "Low Water":   0.30,
    }.get(tide_phase, 0.50)
    neap_factor = 1.0 if spring_or_neap == "Spring" else 0.75
    return phase_score * neap_factor


def select_harbour(
    candidates: List[Tuple[Harbour, float]],
    conditions_list: List[FishingConditions],
    species: Optional[str],
    preference: Optional[str],
    *,
    today: Optional[date] = None,
) -> int:
    """Return the index of the best candidate harbour for the given preference.

    Each preference weights three independent signals differently:

      closest           → maximise proximity; calm sea as tiebreaker.
      calmer-conditions → maximise calm (wave + wind); proximity secondary.
      best-chance       → maximise species/season match + tidal quality;
                          proximity as a minor factor.

    Args:
        candidates:      (harbour, distance_km) pairs, nearest-first.
        conditions_list: FishingConditions for each candidate, same order.
        species:         Target fish species, or None.
        preference:      User preference key, or None (defaults to best-chance).
        today:           Override date for season checks (tests).

    Returns:
        Index into `candidates` / `conditions_list` for the selected harbour.
    """
    pref = preference or "best-chance"
    month = (today or date.today()).month
    w_prox, w_calm, w_fish = _SELECT_WEIGHTS.get(pref, _SELECT_DEFAULT)

    best_idx = 0
    best_score = -1.0

    for i, ((harbour, dist_km), cond) in enumerate(zip(candidates, conditions_list)):
        prox = _proximity_score(dist_km)
        calm = _calm_score(cond.wave_height_m, cond.wind_speed_knots)
        fish = _fishing_quality_score(cond.tide_phase, cond.spring_or_neap)
        sp   = _species_score(harbour, species, month)

        # For best-chance, blend fishing quality with species match
        fish_sp = (fish + sp) / 2.0 if w_fish > 0 else 0.0

        score = w_prox * prox + w_calm * calm + w_fish * fish_sp

        logger.debug(
            "Candidate %s | prox=%.2f calm=%.2f fish_sp=%.2f → score=%.3f",
            harbour.name, prox, calm, fish_sp, score,
        )

        if score > best_score:
            best_score = score
            best_idx = i

    logger.info(
        "Harbour selected: %s (idx=%d, pref=%s, score=%.3f)",
        candidates[best_idx][0].name, best_idx, pref, best_score,
    )
    return best_idx


# ─── Public API ───────────────────────────────────────────────────────────────

def score_recommendation(
    distance_km: float,
    harbour: Harbour,
    species: Optional[str],
    preference: Optional[str],
    *,
    today: Optional[date] = None,
) -> ScoreBreakdown:
    """Compute a confidence score for a harbour/species/preference combination.

    Args:
        distance_km:  Haversine distance from the user's postcode to the harbour.
                      Pass -1.0 when the distance is unknown (fallback harbour).
        harbour:      The Harbour object selected for the recommendation.
        species:      The fish species the user is targeting, or None.
        preference:   The user's stated preference ("closest", "best-chance", …).
        today:        Override the current date — used in tests for determinism.

    Returns:
        A ScoreBreakdown with individual signal scores and the final weighted score.
    """
    month = (today or date.today()).month
    d_weight, s_weight = _PREFERENCE_WEIGHTS.get(preference or "", _DEFAULT_WEIGHTS)

    d_score = _distance_score(distance_km)
    s_score = _species_score(harbour, species, month)
    confidence = round(d_weight * d_score + s_weight * s_score, 4)

    logger.debug(
        "Score | harbour=%s dist=%.1fkm dist_score=%.2f species_score=%.2f "
        "weights=(%.2f, %.2f) → confidence=%.4f",
        harbour.name, distance_km, d_score, s_score, d_weight, s_weight, confidence,
    )

    return ScoreBreakdown(
        distance_score=round(d_score, 4),
        species_score=round(s_score, 4),
        distance_weight=d_weight,
        species_weight=s_weight,
        confidence_score=confidence,
    )
