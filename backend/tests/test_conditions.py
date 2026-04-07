# tests/test_conditions.py — Unit tests for weather, tide, and conditions services.
#
# Strategy:
#   - Weather tests patch httpx.get so no real network calls are made.
#   - Tide tests inject `now` for determinism — no mocking needed.
#   - Conditions tests use both strategies via `today` + `now` injection.

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from app.data.loader import get_harbour_by_id
from app.services.tides import (
    TideConditions,
    get_tides,
    lunar_age,
    tidal_coefficient,
    _phase_label,
)
from app.services.weather import (
    WeatherConditions,
    _beaufort_description,
    _degrees_to_compass,
    _douglas_sea_state,
    _mock_weather,
    get_weather,
)
from app.services.conditions import FishingConditions, get_conditions

FALMOUTH = get_harbour_by_id("falmouth")
WHITBY   = get_harbour_by_id("whitby")

# Fixed UTC times for deterministic tide tests
NEW_MOON   = datetime(2000, 1, 6, 12, 0, tzinfo=timezone.utc)   # reference new moon
FULL_MOON  = datetime(2000, 1, 21, 4, 0, tzinfo=timezone.utc)   # ~14.8 days later
FIXED_DATE = date(2025, 6, 15)   # a known date — keeps mock weather stable
FIXED_NOW  = datetime(2025, 6, 15, 8, 0, tzinfo=timezone.utc)


# ─── Weather helpers ──────────────────────────────────────────────────────────

class TestWeatherHelpers:

    def test_degrees_to_compass_north(self):
        assert _degrees_to_compass(0) == "N"
        assert _degrees_to_compass(360) == "N"

    def test_degrees_to_compass_south(self):
        assert _degrees_to_compass(180) == "S"

    def test_degrees_to_compass_southwest(self):
        assert _degrees_to_compass(225) == "SW"

    def test_beaufort_calm(self):
        assert _beaufort_description(0) == "Calm"

    def test_beaufort_gale(self):
        assert _beaufort_description(35) == "Gale"

    def test_beaufort_fresh_breeze(self):
        assert _beaufort_description(18) == "Fresh breeze"

    def test_douglas_slight(self):
        assert _douglas_sea_state(0.8) == "Slight"

    def test_douglas_rough(self):
        assert _douglas_sea_state(3.0) == "Rough"

    def test_douglas_glassy(self):
        assert _douglas_sea_state(0.05) == "Glassy"


# ─── Mock weather ─────────────────────────────────────────────────────────────

class TestMockWeather:

    def test_returns_weather_conditions(self):
        result = _mock_weather(FALMOUTH, FIXED_DATE)
        assert isinstance(result, WeatherConditions)
        assert result.data_source == "mock"

    def test_deterministic_same_harbour_same_date(self):
        a = _mock_weather(FALMOUTH, FIXED_DATE)
        b = _mock_weather(FALMOUTH, FIXED_DATE)
        assert a.wind_speed_knots == b.wind_speed_knots
        assert a.wave_height_m == b.wave_height_m

    def test_different_harbours_different_output(self):
        a = _mock_weather(FALMOUTH, FIXED_DATE)
        b = _mock_weather(WHITBY, FIXED_DATE)
        # Overwhelmingly unlikely to be identical with different seeds
        assert a.wind_speed_knots != b.wind_speed_knots

    def test_different_dates_different_output(self):
        a = _mock_weather(FALMOUTH, FIXED_DATE)
        b = _mock_weather(FALMOUTH, date(2025, 6, 16))
        assert a.wind_speed_knots != b.wind_speed_knots

    def test_wind_speed_in_realistic_range(self):
        result = _mock_weather(FALMOUTH, FIXED_DATE)
        assert 0 < result.wind_speed_knots < 50

    def test_wave_height_positive(self):
        result = _mock_weather(FALMOUTH, FIXED_DATE)
        assert result.wave_height_m > 0


# ─── get_weather: API + fallback ──────────────────────────────────────────────

class TestGetWeather:

    def _mock_wind_response(self, speed=12.0, direction=225.0):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "current": {
                "wind_speed_10m": speed,
                "wind_direction_10m": direction,
            }
        }
        return resp

    def _mock_wave_response(self, height=0.9, period=8.0):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "current": {
                "wave_height": height,
                "wave_period": period,
            }
        }
        return resp

    def test_uses_api_data_when_available(self):
        with patch("app.services.weather.httpx.get") as mock_get:
            mock_get.side_effect = [
                self._mock_wind_response(speed=15.0, direction=270.0),
                self._mock_wave_response(height=1.2),
            ]
            result = get_weather(FALMOUTH)

        assert result.wind_speed_knots == 15.0
        assert result.wind_direction == "W"
        assert result.wave_height_m == 1.2
        assert result.data_source == "open-meteo"

    def test_falls_back_to_mock_when_wind_api_fails(self):
        with patch("app.services.weather.httpx.get") as mock_get:
            mock_get.side_effect = Exception("network error")
            result = get_weather(FALMOUTH, today=FIXED_DATE)
        assert result.data_source == "mock"

    def test_falls_back_when_wave_api_returns_error(self):
        wave_resp = MagicMock()
        wave_resp.status_code = 500
        with patch("app.services.weather.httpx.get") as mock_get:
            mock_get.side_effect = [
                self._mock_wind_response(),
                wave_resp,
            ]
            result = get_weather(FALMOUTH, today=FIXED_DATE)
        assert result.data_source == "mock"

    def test_sea_state_derived_from_wave_height(self):
        with patch("app.services.weather.httpx.get") as mock_get:
            mock_get.side_effect = [
                self._mock_wind_response(),
                self._mock_wave_response(height=0.3),
            ]
            result = get_weather(FALMOUTH)
        assert result.sea_state == "Smooth"


# ─── Tides: lunar calculation ─────────────────────────────────────────────────

class TestLunarAge:

    def test_reference_new_moon_age_is_zero(self):
        assert lunar_age(date(2000, 1, 6)) == 0.0

    def test_age_at_full_moon_is_about_half_cycle(self):
        age = lunar_age(date(2000, 1, 21))
        assert 14.0 < age < 16.0

    def test_age_cycles_back_to_near_zero(self):
        # One full lunar cycle after the reference new moon
        age = lunar_age(date(2000, 2, 5))
        assert age < 1.0

    def test_age_is_non_negative(self):
        for d in [date(2020, 1, 1), date(2024, 6, 15), date(2025, 12, 31)]:
            assert lunar_age(d) >= 0


class TestTidalCoefficient:

    def test_new_moon_is_maximum_spring(self):
        # Lunar age 0 → cos(0) = 1.0
        assert tidal_coefficient(0.0) == 1.0

    def test_full_moon_is_also_spring(self):
        # Age ~14.77 → cos(π) = -1 → |cos| = 1.0
        coeff = tidal_coefficient(14.77)
        assert coeff > 0.95

    def test_quarter_moon_is_neap(self):
        # Age ~7.38 → cos(π/2) = 0
        coeff = tidal_coefficient(7.38)
        assert coeff < 0.1

    def test_coefficient_between_zero_and_one(self):
        for age in [0, 3, 7, 10, 14, 18, 22, 26, 29]:
            c = tidal_coefficient(float(age))
            assert 0.0 <= c <= 1.0


class TestPhaseLabel:

    def test_just_after_hw_is_high_water(self):
        assert _phase_label(0.5) == "High Water"

    def test_ebb(self):
        assert _phase_label(3.0) == "Ebb"

    def test_low_water(self):
        assert _phase_label(6.2) == "Low Water"

    def test_flood(self):
        assert _phase_label(9.0) == "Flood"

    def test_boundary_at_one_hour(self):
        assert _phase_label(1.0) == "Ebb"  # just crosses into Ebb


class TestGetTides:

    def test_returns_tide_conditions(self):
        result = get_tides("falmouth", now=FIXED_NOW)
        assert isinstance(result, TideConditions)

    def test_data_source_is_calculated(self):
        result = get_tides("falmouth", now=FIXED_NOW)
        assert result.data_source == "calculated"

    def test_spring_neap_is_valid(self):
        result = get_tides("falmouth", now=FIXED_NOW)
        assert result.spring_or_neap in ("Spring", "Neap")

    def test_tide_phase_is_valid(self):
        result = get_tides("falmouth", now=FIXED_NOW)
        assert result.tide_phase in ("Flood", "High Water", "Ebb", "Low Water")

    def test_tidal_coefficient_in_range(self):
        result = get_tides("falmouth", now=FIXED_NOW)
        assert 0.0 <= result.tidal_coefficient <= 1.0

    def test_hours_to_next_hw_positive(self):
        result = get_tides("falmouth", now=FIXED_NOW)
        assert result.hours_to_next_hw > 0

    def test_unknown_harbour_uses_default(self):
        # Should not raise — falls back to _DEFAULT_ESTABLISHMENT
        result = get_tides("unknown_port", now=FIXED_NOW)
        assert isinstance(result, TideConditions)

    def test_different_harbours_may_differ(self):
        # Falmouth and Peterhead have very different establishment times
        falmouth = get_tides("falmouth", now=FIXED_NOW)
        peterhead = get_tides("peterhead", now=FIXED_NOW)
        # They might coincidentally be in the same phase but hours_to_next_hw differs
        assert falmouth.hours_to_next_hw != peterhead.hours_to_next_hw


# ─── Combined conditions ──────────────────────────────────────────────────────

class TestGetConditions:

    def test_returns_fishing_conditions(self):
        with patch("app.services.conditions.get_weather") as mock_w, \
             patch("app.services.conditions.get_tides") as mock_t:
            mock_w.return_value = WeatherConditions(
                wind_speed_knots=12.0,
                wind_direction="SW",
                wind_description="Moderate breeze",
                wave_height_m=0.8,
                sea_state="Slight",
                data_source="mock",
            )
            mock_t.return_value = TideConditions(
                tide_phase="Flood",
                spring_or_neap="Spring",
                tidal_coefficient=0.85,
                next_high_water="09:30 UTC",
                hours_to_next_hw=1.5,
                data_source="calculated",
            )
            result = get_conditions(FALMOUTH, today=FIXED_DATE, now=FIXED_NOW)

        assert isinstance(result, FishingConditions)
        assert result.tide_phase == "Flood"
        assert result.wind_direction == "SW"
        assert result.weather_source == "mock"

    def test_time_window_is_non_empty_string(self):
        with patch("app.services.conditions.get_weather") as mock_w, \
             patch("app.services.conditions.get_tides") as mock_t:
            mock_w.return_value = WeatherConditions(
                wind_speed_knots=8.0, wind_direction="N",
                wind_description="Gentle breeze", wave_height_m=0.4,
                sea_state="Smooth", data_source="mock",
            )
            mock_t.return_value = TideConditions(
                tide_phase="Flood", spring_or_neap="Neap",
                tidal_coefficient=0.3, next_high_water="10:00 UTC",
                hours_to_next_hw=2.0, data_source="calculated",
            )
            result = get_conditions(FALMOUTH, today=FIXED_DATE, now=FIXED_NOW)

        assert "UTC" in result.recommended_time_window
        assert "–" in result.recommended_time_window

    def test_rough_conditions_shifts_to_low_water_window(self):
        with patch("app.services.conditions.get_weather") as mock_w, \
             patch("app.services.conditions.get_tides") as mock_t:
            mock_w.return_value = WeatherConditions(
                wind_speed_knots=30.0, wind_direction="W",
                wind_description="Near gale", wave_height_m=3.5,
                sea_state="Rough", data_source="mock",
            )
            mock_t.return_value = TideConditions(
                tide_phase="Flood", spring_or_neap="Spring",
                tidal_coefficient=0.9, next_high_water="10:00 UTC",
                hours_to_next_hw=2.0, data_source="calculated",
            )
            result = get_conditions(FALMOUTH, today=FIXED_DATE, now=FIXED_NOW)

        assert "sheltered" in result.recommended_time_window

    def test_conditions_summary_contains_key_fields(self):
        with patch("app.services.conditions.get_weather") as mock_w, \
             patch("app.services.conditions.get_tides") as mock_t:
            mock_w.return_value = WeatherConditions(
                wind_speed_knots=10.0, wind_direction="NE",
                wind_description="Gentle breeze", wave_height_m=0.5,
                sea_state="Slight", data_source="mock",
            )
            mock_t.return_value = TideConditions(
                tide_phase="Ebb", spring_or_neap="Neap",
                tidal_coefficient=0.2, next_high_water="14:00 UTC",
                hours_to_next_hw=5.0, data_source="calculated",
            )
            result = get_conditions(FALMOUTH, today=FIXED_DATE, now=FIXED_NOW)

        assert "Gentle breeze" in result.conditions_summary
        assert "slight" in result.conditions_summary   # sea_state is lowercased in summary
        assert "neap" in result.conditions_summary
