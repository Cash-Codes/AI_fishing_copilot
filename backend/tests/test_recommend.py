"""
test_recommend.py — Tests for POST /recommend.

Covers three distinct concerns, kept in separate classes so failures are
easy to locate:

1. Happy path   — valid input produces a well-formed response.
2. Response contract — every field the frontend expects is present and
                       the right type. If a field is renamed or removed
                       here the frontend breaks silently without this test.
3. Validation   — bad input is rejected with 422 before our code runs.
"""

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_geo(lat=50.2632, lon=-5.0510):
    """Return a mock httpx response that resolves to (lat, lon) via postcodes.io."""
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"result": {"latitude": lat, "longitude": lon}}
    return m


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_BODY = {
    "location": "TR11AA",
    "species": "Bass",
    "preference": "best-chance",
}


# ── Happy path ────────────────────────────────────────────────────────────────

class TestRecommendHappyPath:
    def test_returns_200(self, client):
        with patch("app.services.geocoding.httpx.get", return_value=_mock_geo()), \
             patch("app.services.harbour._fetch_overpass", return_value=()):
            response = client.post("/recommend", json=VALID_BODY)
        assert response.status_code == 200

    def test_echoes_input_location(self, client):
        with patch("app.services.geocoding.httpx.get", return_value=_mock_geo()), \
             patch("app.services.harbour._fetch_overpass", return_value=()):
            response = client.post("/recommend", json=VALID_BODY)
        assert response.json()["input_location"] == VALID_BODY["location"]

    def test_omitting_species_still_succeeds(self, client):
        body = {"location": "EX11AA", "preference": "closest"}
        with patch("app.services.geocoding.httpx.get", return_value=_mock_geo(50.72, -3.53)), \
             patch("app.services.harbour._fetch_overpass", return_value=()):
            response = client.post("/recommend", json=body)
        assert response.status_code == 200

    def test_omitting_preference_still_succeeds(self, client):
        body = {"location": "PL11AA"}
        with patch("app.services.geocoding.httpx.get", return_value=_mock_geo(50.37, -4.14)), \
             patch("app.services.harbour._fetch_overpass", return_value=()):
            response = client.post("/recommend", json=body)
        assert response.status_code == 200

    def test_city_name_resolves_and_returns_200(self, client):
        """Place names (not postcodes) should route via Nominatim and work."""
        nominatim_resp = MagicMock()
        nominatim_resp.status_code = 200
        nominatim_resp.json.return_value = [{"lat": "51.5", "lon": "-0.1", "display_name": "London"}]
        with patch("app.services.geocoding.httpx.get", return_value=nominatim_resp), \
             patch("app.services.harbour._fetch_overpass", return_value=()):
            response = client.post("/recommend", json={"location": "London"})
        assert response.status_code == 200


# ── Response contract ─────────────────────────────────────────────────────────

class TestRecommendResponseContract:
    """
    These tests pin the exact shape of the response.

    When the real AI logic is wired in, these tests will still pass as long
    as the field names and types are preserved — which is exactly what we
    need to guarantee frontend compatibility.
    """

    @pytest.fixture(autouse=True)
    def response_body(self, client):
        with patch("app.services.geocoding.httpx.get", return_value=_mock_geo()), \
             patch("app.services.harbour._fetch_overpass", return_value=()):
            self.body = client.post("/recommend", json=VALID_BODY).json()

    def test_has_input_location(self):
        assert "input_location" in self.body
        assert isinstance(self.body["input_location"], str)

    def test_has_nearest_harbour(self):
        assert "nearest_harbour" in self.body
        assert isinstance(self.body["nearest_harbour"], str)
        assert len(self.body["nearest_harbour"]) > 0

    def test_has_recommendation_window(self):
        assert "recommendation_window" in self.body
        assert isinstance(self.body["recommendation_window"], str)

    def test_has_confidence_score_in_range(self):
        score = self.body["confidence_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_has_explanation(self):
        assert "explanation" in self.body
        assert isinstance(self.body["explanation"], str)
        assert len(self.body["explanation"]) > 0

    def test_has_used_fallback_bool(self):
        assert "used_fallback" in self.body
        assert isinstance(self.body["used_fallback"], bool)

    def test_has_retrieved_notes_list(self):
        assert "retrieved_notes" in self.body
        assert isinstance(self.body["retrieved_notes"], list)

    def test_retrieved_notes_are_strings(self):
        notes = self.body["retrieved_notes"]
        assert all(isinstance(note, str) for note in notes)


# ── Validation (422 responses) ────────────────────────────────────────────────

class TestRecommendValidation:
    """
    Pydantic + FastAPI return HTTP 422 automatically when the request body
    fails validation.
    """

    def test_missing_location_returns_422(self, client):
        response = client.post("/recommend", json={"preference": "closest"})
        assert response.status_code == 422

    def test_location_too_short_returns_422(self, client):
        # min_length=2 on the location field
        response = client.post("/recommend", json={"location": "T"})
        assert response.status_code == 422

    def test_location_too_long_returns_422(self, client):
        # max_length=100
        response = client.post("/recommend", json={"location": "A" * 101})
        assert response.status_code == 422

    def test_invalid_preference_returns_422(self, client):
        response = client.post(
            "/recommend",
            json={"location": "TR11AA", "preference": "not-a-valid-option"},
        )
        assert response.status_code == 422

    def test_empty_body_returns_422(self, client):
        response = client.post("/recommend", json={})
        assert response.status_code == 422
