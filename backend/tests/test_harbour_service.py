# tests/test_harbour_service.py — Unit tests for the harbour and postcode services.
#
# These tests cover:
#   - haversine_km: formula correctness against known real-world distances
#   - nearest_harbour: picks the right harbour for given coordinates
#   - resolve_postcode: seed map lookup, API success, API failure, unknown code
#   - recommend endpoint: used_fallback flag in the response
#
# The postcodes.io API is always mocked — tests never make real network calls.

from unittest.mock import MagicMock, patch

from app.services.harbour import haversine_km, nearest_harbour, default_harbour
from app.services.postcode import resolve_postcode, _outward_code


# ─── haversine_km ─────────────────────────────────────────────────────────────

class TestHaversineKm:
    """Verify the Haversine formula against known real-world distances."""

    def test_same_point_is_zero(self):
        assert haversine_km(50.0, -5.0, 50.0, -5.0) == 0.0

    def test_falmouth_to_newlyn_approx(self):
        # Falmouth (50.1528, -5.0664) to Newlyn (50.1013, -5.5454)
        # Real road distance ~25 km; straight-line should be ~35 km
        dist = haversine_km(50.1528, -5.0664, 50.1013, -5.5454)
        assert 30 < dist < 45, f"Expected ~35 km, got {dist:.1f}"

    def test_falmouth_to_whitby_approx(self):
        # Falmouth (50.15, -5.07) to Whitby (54.49, -0.61)
        # North–south distance across England, roughly 600 km
        dist = haversine_km(50.1528, -5.0664, 54.4877, -0.6140)
        assert 550 < dist < 650, f"Expected ~600 km, got {dist:.1f}"

    def test_symmetry(self):
        # Distance A→B must equal B→A
        d_ab = haversine_km(50.1528, -5.0664, 54.4877, -0.6140)
        d_ba = haversine_km(54.4877, -0.6140, 50.1528, -5.0664)
        assert abs(d_ab - d_ba) < 0.001

    def test_north_south_one_degree(self):
        # One degree of latitude ≈ 111 km everywhere (latitude-independent)
        dist = haversine_km(50.0, 0.0, 51.0, 0.0)
        assert 110 < dist < 112, f"Expected ~111 km, got {dist:.1f}"


# ─── nearest_harbour ──────────────────────────────────────────────────────────

class TestNearestHarbour:
    """Verify the harbour selection logic for known geographic positions."""

    def test_truro_returns_falmouth(self):
        # Truro (50.26, -5.05) — Falmouth Harbour is the closest
        harbour, dist = nearest_harbour(50.2632, -5.0510)
        assert harbour.id == "falmouth"
        assert dist < 20

    def test_penzance_returns_newlyn(self):
        # Penzance (50.12, -5.54) — Newlyn Harbour is next door
        harbour, dist = nearest_harbour(50.1200, -5.5400)
        assert harbour.id == "newlyn"
        assert dist < 5

    def test_whitby_area_returns_whitby(self):
        # Scarborough (54.28, -0.40) is slightly closer to Whitby than Bridlington
        harbour, dist = nearest_harbour(54.4877, -0.6140)
        assert harbour.id == "whitby"
        assert dist < 1  # queried Whitby's own coordinates

    def test_poole_area_returns_poole(self):
        harbour, dist = nearest_harbour(50.7143, -1.9872)
        assert harbour.id == "poole"
        assert dist < 1

    def test_returns_harbour_and_positive_distance(self):
        harbour, dist = nearest_harbour(51.5074, -0.1278)  # London
        assert harbour is not None
        assert dist > 0

    def test_distance_is_kilometres(self):
        # London is >50 km from any of our harbours
        _, dist = nearest_harbour(51.5074, -0.1278)
        assert dist > 50

    def test_default_harbour_is_falmouth(self):
        harbour, dist = default_harbour()
        assert harbour.id == "falmouth"
        assert dist == -1.0  # sentinel for "not a real measurement"


# ─── resolve_postcode ─────────────────────────────────────────────────────────

class TestOutwardCode:
    """Verify outward-code extraction handles common UK postcode formats."""

    def test_standard_with_space(self):
        assert _outward_code("TR1 1AA") == "TR1"

    def test_long_outward_with_space(self):
        assert _outward_code("TR11 3JT") == "TR11"

    def test_lowercase_normalised(self):
        assert _outward_code("sw1a 2aa") == "SW1A"

    def test_no_space_format(self):
        # "TR11AA" → outward is everything except last 3 chars → "TR1"
        assert _outward_code("TR11AA") == "TR1"

    def test_leading_trailing_whitespace(self):
        assert _outward_code("  BH15 1HJ  ") == "BH15"


class TestResolvePostcode:
    """resolve_postcode: seed map, API success/failure, unknown code."""

    def test_seed_map_hit_returns_coords(self):
        # TR1 is in the seed map — no network call expected
        result = resolve_postcode("TR1 1AA")
        assert result is not None
        lat, lon = result
        assert 50.0 < lat < 51.0
        assert -6.0 < lon < -4.0

    def test_seed_map_case_insensitive(self):
        result = resolve_postcode("tr1 1aa")
        assert result is not None

    def test_unknown_postcode_falls_back_to_api(self):
        # "ZZ99 9ZZ" is not in the seed map — should attempt the API
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {"latitude": 51.5, "longitude": -0.1}
        }
        with patch("app.services.postcode.httpx.get", return_value=mock_resp) as mock_get:
            result = resolve_postcode("ZZ99 9ZZ")
        mock_get.assert_called_once()
        assert result == (51.5, -0.1)

    def test_api_404_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("app.services.postcode.httpx.get", return_value=mock_resp):
            result = resolve_postcode("ZZ99 9ZZ")
        assert result is None

    def test_api_network_error_returns_none(self):
        with patch("app.services.postcode.httpx.get", side_effect=Exception("timeout")):
            result = resolve_postcode("ZZ99 9ZZ")
        assert result is None

    def test_seed_map_never_calls_api(self):
        # Seed hit must not touch the network at all
        with patch("app.services.postcode.httpx.get") as mock_get:
            resolve_postcode("TR1 1AA")
        mock_get.assert_not_called()


# ─── Integration: recommend endpoint fallback flag ────────────────────────────

class TestRecommendFallback:
    """Verify the /recommend endpoint sets used_fallback correctly."""

    def test_known_postcode_fallback_false(self, client):
        # TR1 1AA is in the seed map — no fallback needed
        resp = client.post("/recommend", json={"postcode": "TR1 1AA"})
        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is False

    def test_known_postcode_returns_real_harbour(self, client):
        resp = client.post("/recommend", json={"postcode": "TR1 1AA"})
        assert resp.json()["nearest_harbour"] == "Falmouth Harbour"

    def test_unknown_postcode_fallback_true(self, client):
        # Patch both seed lookup and API so the postcode truly cannot be resolved
        with patch("app.services.postcode.httpx.get") as mock_get:
            mock_get.return_value.status_code = 404
            resp = client.post("/recommend", json={"postcode": "ZZ9 9ZZ"})
        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is True

    def test_unknown_postcode_returns_default_harbour(self, client):
        with patch("app.services.postcode.httpx.get") as mock_get:
            mock_get.return_value.status_code = 404
            resp = client.post("/recommend", json={"postcode": "ZZ9 9ZZ"})
        assert resp.json()["nearest_harbour"] == "Falmouth Harbour"
