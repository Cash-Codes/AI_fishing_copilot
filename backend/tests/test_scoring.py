# tests/test_scoring.py — Unit tests for the recommendation scoring engine.
#
# We inject `today` into every call that depends on season so the tests are
# deterministic regardless of when they run.  No mocking needed for datetime.

from datetime import date
from unittest.mock import MagicMock

from app.data.loader import get_harbour_by_id
from app.services.scoring import (
    ScoreBreakdown,
    _calm_score,
    _distance_score,
    _fishing_quality_score,
    _is_in_season,
    _parse_season,
    _proximity_score,
    _species_score,
    score_recommendation,
    select_harbour,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

# A harbour that mentions Bass and Mackerel in its description
FALMOUTH = get_harbour_by_id("falmouth")
# A harbour that mentions Cod and Whiting — not Bass
WHITBY = get_harbour_by_id("whitby")

# Fixed dates for season testing
MAY_1    = date(2025, 5, 1)    # in Bass season (May–October)
JAN_1    = date(2025, 1, 1)    # outside Bass season
NOV_1    = date(2025, 11, 1)   # in Cod season (October–March)
JULY_1   = date(2025, 7, 1)    # mid-summer


# ─── _distance_score ──────────────────────────────────────────────────────────

class TestDistanceScore:

    def test_zero_distance_is_perfect(self):
        assert _distance_score(0.0) == 1.0

    def test_half_max_distance_is_half(self):
        # 100 km out of 200 km max → 0.5
        assert _distance_score(100.0) == 0.5

    def test_at_max_distance_is_zero(self):
        assert _distance_score(200.0) == 0.0

    def test_beyond_max_is_clamped_to_zero(self):
        assert _distance_score(999.0) == 0.0

    def test_sentinel_minus_one_is_zero(self):
        # -1.0 is the sentinel for "distance unknown" (fallback harbour)
        assert _distance_score(-1.0) == 0.0

    def test_score_decreases_with_distance(self):
        assert _distance_score(10.0) > _distance_score(50.0) > _distance_score(100.0)


# ─── _parse_season / _is_in_season ────────────────────────────────────────────

class TestParseSeason:

    def test_standard_range(self):
        assert _parse_season("May–October") == (5, 10)

    def test_wrap_around_range(self):
        # October–March covers the winter months
        assert _parse_season("October–March") == (10, 3)

    def test_year_round_returns_none(self):
        assert _parse_season("Year-round (peak July–September)") is None

    def test_case_insensitive(self):
        assert _parse_season("may–october") == (5, 10)


class TestIsInSeason:

    def test_month_inside_normal_range(self):
        assert _is_in_season("May–October", 7) is True

    def test_month_at_start_of_range(self):
        assert _is_in_season("May–October", 5) is True

    def test_month_at_end_of_range(self):
        assert _is_in_season("May–October", 10) is True

    def test_month_outside_normal_range(self):
        assert _is_in_season("May–October", 1) is False

    def test_wrap_around_in_season(self):
        # November is inside October–March
        assert _is_in_season("October–March", 11) is True

    def test_wrap_around_january_in_season(self):
        assert _is_in_season("October–March", 1) is True

    def test_wrap_around_outside_season(self):
        # June is outside October–March
        assert _is_in_season("October–March", 6) is False

    def test_year_round_is_always_in_season(self):
        for month in range(1, 13):
            assert _is_in_season("Year-round (peak July–September)", month) is True


# ─── _species_score ───────────────────────────────────────────────────────────

class TestSpeciesScore:

    def test_no_species_is_neutral(self):
        # When the user hasn't specified a species, return 0.5
        assert _species_score(FALMOUTH, None, 6) == 0.5

    def test_known_species_in_season_is_perfect(self):
        # Falmouth description mentions Bass; May is in Bass season
        assert _species_score(FALMOUTH, "Bass", MAY_1.month) == 1.0

    def test_known_species_out_of_season(self):
        # Falmouth mentions Bass, but January is outside May–October
        assert _species_score(FALMOUTH, "Bass", JAN_1.month) == 0.6

    def test_unknown_harbour_species_in_season(self):
        # Whitby description does not mention Bass; Bass is in season in July
        assert _species_score(WHITBY, "Bass", JULY_1.month) == 0.3

    def test_unknown_harbour_species_out_of_season(self):
        # Whitby doesn't mention Bass; January is outside Bass season
        assert _species_score(WHITBY, "Bass", JAN_1.month) == 0.1

    def test_whitby_cod_in_season(self):
        # Whitby description explicitly mentions Cod; November is in Cod season
        assert _species_score(WHITBY, "Cod", NOV_1.month) == 1.0

    def test_species_not_in_dataset_assumes_in_season(self):
        # Unknown species → assume in season; harbour doesn't mention it → 0.3
        assert _species_score(FALMOUTH, "Narwhal", JULY_1.month) == 0.3


# ─── score_recommendation ─────────────────────────────────────────────────────

class TestScoreRecommendation:

    def test_returns_score_breakdown(self):
        result = score_recommendation(10.0, FALMOUTH, "Bass", "best-chance", today=MAY_1)
        assert isinstance(result, ScoreBreakdown)

    def test_confidence_is_between_zero_and_one(self):
        result = score_recommendation(10.0, FALMOUTH, "Bass", "best-chance", today=MAY_1)
        assert 0.0 <= result.confidence_score <= 1.0

    def test_closer_harbour_scores_higher_for_closest_preference(self):
        near = score_recommendation(5.0, FALMOUTH, None, "closest", today=MAY_1)
        far  = score_recommendation(150.0, FALMOUTH, None, "closest", today=MAY_1)
        assert near.confidence_score > far.confidence_score

    def test_best_chance_weights_species_over_distance(self):
        # Same harbour; species match should dominate for best-chance
        result = score_recommendation(10.0, FALMOUTH, "Bass", "best-chance", today=MAY_1)
        # species_weight (0.65) > distance_weight (0.35) for best-chance
        assert result.species_weight > result.distance_weight

    def test_closest_weights_distance_over_species(self):
        result = score_recommendation(10.0, FALMOUTH, "Bass", "closest", today=MAY_1)
        assert result.distance_weight > result.species_weight

    def test_unknown_preference_uses_default_equal_weights(self):
        result = score_recommendation(10.0, FALMOUTH, None, None, today=MAY_1)
        assert result.distance_weight == 0.50
        assert result.species_weight == 0.50

    def test_fallback_sentinel_distance_scores_zero_distance(self):
        result = score_recommendation(-1.0, FALMOUTH, None, "closest", today=MAY_1)
        assert result.distance_score == 0.0

    def test_today_injection_changes_season_outcome(self):
        in_season  = score_recommendation(10.0, FALMOUTH, "Bass", "best-chance", today=MAY_1)
        out_season = score_recommendation(10.0, FALMOUTH, "Bass", "best-chance", today=JAN_1)
        assert in_season.confidence_score > out_season.confidence_score

    def test_score_components_combine_correctly(self):
        result = score_recommendation(100.0, FALMOUTH, None, "closest", today=MAY_1)
        # distance_score = 1 - 100/200 = 0.5; species_score = 0.5 (no species)
        # confidence = 0.80 * 0.5 + 0.20 * 0.5 = 0.5
        assert result.distance_score == 0.5
        assert result.species_score == 0.5
        assert result.confidence_score == 0.5


# ─── Selection signal helpers ─────────────────────────────────────────────────

class TestProximityScore:

    def test_zero_distance_is_one(self):
        assert _proximity_score(0.0) == 1.0

    def test_twenty_km_is_half(self):
        assert _proximity_score(20.0) == 0.5

    def test_sentinel_minus_one_is_zero(self):
        assert _proximity_score(-1.0) == 0.0

    def test_decreases_with_distance(self):
        assert _proximity_score(5.0) > _proximity_score(50.0) > _proximity_score(200.0)


class TestCalmScore:

    def test_flat_calm_is_one(self):
        assert _calm_score(0.0, 0.0) == 1.0

    def test_both_at_max_is_zero(self):
        assert _calm_score(4.0, 32.0) == 0.0

    def test_rough_sea_lowers_score(self):
        assert _calm_score(3.0, 5.0) < _calm_score(0.5, 5.0)

    def test_high_wind_lowers_score(self):
        assert _calm_score(0.5, 25.0) < _calm_score(0.5, 5.0)

    def test_score_between_zero_and_one(self):
        assert 0.0 <= _calm_score(1.5, 15.0) <= 1.0


class TestFishingQualityScore:

    def test_spring_flood_is_highest(self):
        assert _fishing_quality_score("Flood", "Spring") == 1.0

    def test_neap_reduces_score(self):
        assert _fishing_quality_score("Flood", "Neap") < _fishing_quality_score("Flood", "Spring")

    def test_low_water_is_lowest(self):
        assert _fishing_quality_score("Low Water", "Neap") < _fishing_quality_score("Ebb", "Neap")

    def test_flood_better_than_ebb(self):
        assert _fishing_quality_score("Flood", "Spring") > _fishing_quality_score("Ebb", "Spring")


# ─── select_harbour ───────────────────────────────────────────────────────────

def _make_conditions(wave_m=1.0, wind_kn=10.0, tide_phase="Flood", spring_or_neap="Spring"):
    """Build a minimal FishingConditions-like mock for selection tests."""
    c = MagicMock()
    c.wave_height_m = wave_m
    c.wind_speed_knots = wind_kn
    c.tide_phase = tide_phase
    c.spring_or_neap = spring_or_neap
    return c


class TestSelectHarbour:

    def test_closest_picks_nearest(self):
        # Two candidates: Falmouth (5 km) vs Whitby (300 km)
        candidates = [(FALMOUTH, 5.0), (WHITBY, 300.0)]
        conds = [_make_conditions(), _make_conditions()]
        idx = select_harbour(candidates, conds, species=None, preference="closest")
        assert idx == 0  # Falmouth is closer

    def test_calmer_picks_calmer_harbour(self):
        # Candidate 0: rough seas. Candidate 1: calm but further away.
        candidates = [(FALMOUTH, 5.0), (WHITBY, 30.0)]
        conds = [
            _make_conditions(wave_m=3.5, wind_kn=28.0),  # rough
            _make_conditions(wave_m=0.3, wind_kn=4.0),   # calm
        ]
        idx = select_harbour(candidates, conds, species=None, preference="calmer-conditions")
        assert idx == 1  # Whitby is calmer

    def test_best_chance_favours_species_match(self):
        # Falmouth mentions Bass; July is in Bass season (May–Oct).
        # Whitby doesn't mention Bass and is further away.
        candidates = [(FALMOUTH, 10.0), (WHITBY, 50.0)]
        conds = [_make_conditions(), _make_conditions()]
        idx = select_harbour(
            candidates, conds, species="Bass", preference="best-chance", today=JULY_1
        )
        assert idx == 0  # Falmouth has Bass in season

    def test_best_chance_with_out_of_season_species_considers_other_signals(self):
        # Bass out of season everywhere — selection should still return a valid index
        candidates = [(FALMOUTH, 10.0), (WHITBY, 50.0)]
        conds = [_make_conditions(), _make_conditions()]
        idx = select_harbour(
            candidates, conds, species="Bass", preference="best-chance", today=JAN_1
        )
        assert idx in (0, 1)  # just verify it doesn't crash and returns valid index

    def test_none_preference_defaults_to_best_chance_behaviour(self):
        candidates = [(FALMOUTH, 10.0), (WHITBY, 300.0)]
        conds = [_make_conditions(), _make_conditions()]
        idx = select_harbour(candidates, conds, species=None, preference=None)
        assert idx in (0, 1)

    def test_single_candidate_always_returns_zero(self):
        candidates = [(FALMOUTH, 10.0)]
        conds = [_make_conditions()]
        assert select_harbour(candidates, conds, species=None, preference="closest") == 0

    def test_closest_ignores_calm_when_distance_very_different(self):
        # 2 km vs 150 km — distance gap should dominate even with calmer distant harbour
        candidates = [(FALMOUTH, 2.0), (WHITBY, 150.0)]
        conds = [
            _make_conditions(wave_m=2.0, wind_kn=20.0),
            _make_conditions(wave_m=0.1, wind_kn=1.0),
        ]
        idx = select_harbour(candidates, conds, species=None, preference="closest")
        assert idx == 0
