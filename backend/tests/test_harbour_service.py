# tests/test_harbour_service.py — Unit tests for the harbour, postcode, and
# geocoding services.
#
# These tests cover:
#   - haversine_km: formula correctness against known real-world distances
#   - nearest_harbour / nearest_harbours: local fallback dataset (Overpass mocked)
#   - resolve_postcode: API success, API failure, unknown code
#   - resolve_location: postcode vs place-name routing
#   - recommend endpoint: used_fallback flag in the response
#
# All external HTTP calls are mocked — tests never make real network calls.

from unittest.mock import MagicMock, patch

from app.services.harbour import haversine_km, nearest_harbour, nearest_harbours, default_harbour
from app.services.postcode import resolve_postcode, _outward_code
from app.services.geocoding import resolve_location


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


# ─── nearest_harbour / nearest_harbours ──────────────────────────────────────
#
# Overpass is always mocked here so tests are deterministic and offline.
# An empty tuple from Overpass triggers the local dataset fallback.

def _mock_overpass_empty(*args):
    return ()


class TestNearestHarbour:
    """Verify harbour selection falls back to local dataset when Overpass is empty."""

    def test_truro_returns_falmouth(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            harbour, dist = nearest_harbour(50.2632, -5.0510)
        assert harbour.id == "falmouth"
        assert dist < 20

    def test_penzance_returns_newlyn(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            harbour, dist = nearest_harbour(50.1200, -5.5400)
        assert harbour.id == "newlyn"
        assert dist < 5

    def test_whitby_area_returns_whitby(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            harbour, dist = nearest_harbour(54.4877, -0.6140)
        assert harbour.id == "whitby"
        assert dist < 1

    def test_poole_area_returns_poole(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            harbour, dist = nearest_harbour(50.7143, -1.9872)
        assert harbour.id == "poole"
        assert dist < 1

    def test_returns_harbour_and_positive_distance(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            harbour, dist = nearest_harbour(51.5074, -0.1278)  # London
        assert harbour is not None
        assert dist > 0

    def test_distance_is_kilometres(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            _, dist = nearest_harbour(51.5074, -0.1278)
        assert dist > 50

    def test_default_harbour_is_falmouth(self):
        harbour, dist = default_harbour()
        assert harbour.id == "falmouth"
        assert dist == -1.0


class TestNearestHarbours:

    def test_returns_tuple_of_candidates_and_flag(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            result = nearest_harbours(50.2632, -5.0510, n=3)
        assert isinstance(result, tuple) and len(result) == 2

    def test_returns_correct_count(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            candidates, _ = nearest_harbours(50.2632, -5.0510, n=3)
        assert len(candidates) == 3

    def test_sorted_nearest_first(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            candidates, _ = nearest_harbours(50.2632, -5.0510, n=5)
        distances = [d for _, d in candidates]
        assert distances == sorted(distances)

    def test_first_result_matches_nearest_harbour(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            harbour_single, _ = nearest_harbour(50.2632, -5.0510)
            candidates, _ = nearest_harbours(50.2632, -5.0510, n=5)
            harbour_multi, _ = candidates[0]
        assert harbour_single.id == harbour_multi.id

    def test_returns_at_least_one_when_n_exceeds_dataset(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            candidates, _ = nearest_harbours(50.2632, -5.0510, n=9999)
        assert len(candidates) >= 1

    def test_all_elements_are_harbour_distance_tuples(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            candidates, _ = nearest_harbours(50.2632, -5.0510, n=3)
        for harbour, dist in candidates:
            assert hasattr(harbour, "id")
            assert dist >= 0

    def test_uk_location_not_out_of_range(self):
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            _, out_of_range = nearest_harbours(50.2632, -5.0510, n=3)
        assert out_of_range is False

    def test_distant_location_flagged_out_of_range(self):
        # NYC is ~5000 km from any UK harbour — should be flagged
        with patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            _, out_of_range = nearest_harbours(40.7128, -74.0060, n=3)
        assert out_of_range is True


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
        assert _outward_code("TR11AA") == "TR1"

    def test_leading_trailing_whitespace(self):
        assert _outward_code("  BH15 1HJ  ") == "BH15"


class TestResolvePostcode:
    """resolve_postcode: API success, API failure, unknown code."""

    def test_api_success_returns_coords(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {"latitude": 50.2632, "longitude": -5.0510}
        }
        with patch("app.services.postcode.httpx.get", return_value=mock_resp):
            result = resolve_postcode("TR1 1AA")
        assert result == (50.2632, -5.0510)

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


# ─── resolve_location ─────────────────────────────────────────────────────────

class TestResolveLocation:
    """Verify routing: postcodes → postcodes.io, place names → Nominatim."""

    def test_uk_postcode_routes_to_postcodes_io(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"latitude": 50.26, "longitude": -5.05}}
        with patch("app.services.geocoding.httpx.get", return_value=mock_resp) as mock_get:
            result = resolve_location("TR1 1AA")
        call_url = mock_get.call_args[0][0]
        assert "postcodes.io" in call_url
        assert result == (50.26, -5.05)

    def test_place_name_routes_to_nominatim(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"lat": "51.5", "lon": "-0.1", "display_name": "London"}]
        with patch("app.services.geocoding.httpx.get", return_value=mock_resp) as mock_get:
            result = resolve_location("London")
        call_url = mock_get.call_args[0][0]
        assert "nominatim" in call_url
        assert result == (51.5, -0.1)

    def test_unknown_place_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []  # Nominatim returns empty list
        with patch("app.services.geocoding.httpx.get", return_value=mock_resp):
            result = resolve_location("Xyzzy Nonexistent Place")
        assert result is None

    def test_network_error_returns_none(self):
        with patch("app.services.geocoding.httpx.get", side_effect=Exception("timeout")):
            result = resolve_location("Delhi")
        assert result is None

    def test_lowercase_postcode_detected(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"latitude": 50.71, "longitude": -1.99}}
        with patch("app.services.geocoding.httpx.get", return_value=mock_resp) as mock_get:
            resolve_location("bh15 1hj")
        call_url = mock_get.call_args[0][0]
        assert "postcodes.io" in call_url


# ─── Integration: recommend endpoint fallback flag ────────────────────────────

class TestRecommendFallback:
    """Verify the /recommend endpoint sets used_fallback correctly."""

    def test_known_location_fallback_false(self, client):
        # Mock geocoding so no network call needed; mock AI too.
        mock_response = MagicMock()
        mock_response.text = "Great conditions at Falmouth today."
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.geocoding.httpx.get") as mock_geo, \
             patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty), \
             patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model), \
             patch.dict("os.environ", env, clear=False):
            mock_geo.return_value.status_code = 200
            mock_geo.return_value.json.return_value = {
                "result": {"latitude": 50.2632, "longitude": -5.0510}
            }
            resp = client.post("/recommend", json={"location": "TR1 1AA"})
        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is False

    def test_known_location_returns_real_harbour(self, client):
        with patch("app.services.geocoding.httpx.get") as mock_geo, \
             patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            mock_geo.return_value.status_code = 200
            mock_geo.return_value.json.return_value = {
                "result": {"latitude": 50.2632, "longitude": -5.0510}
            }
            resp = client.post("/recommend", json={"location": "TR1 1AA", "preference": "closest"})
        assert resp.json()["nearest_harbour"] == "Falmouth Harbour"

    def test_unknown_location_fallback_true(self, client):
        with patch("app.services.geocoding.httpx.get") as mock_geo, \
             patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            mock_geo.return_value.status_code = 200
            mock_geo.return_value.json.return_value = []  # Nominatim empty — unknown place
            resp = client.post("/recommend", json={"location": "Xyzzy Nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is True

    def test_unknown_location_returns_default_harbour(self, client):
        with patch("app.services.geocoding.httpx.get") as mock_geo, \
             patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            mock_geo.return_value.status_code = 200
            mock_geo.return_value.json.return_value = []
            resp = client.post("/recommend", json={"location": "Xyzzy Nonexistent"})
        assert resp.json()["nearest_harbour"] == "Falmouth Harbour"

    def test_out_of_range_location_sets_fallback_true(self, client):
        # NYC resolves via Nominatim but all UK harbours are >500 km away.
        # used_fallback must be True so the UI shows the coverage warning.
        with patch("app.services.geocoding.httpx.get") as mock_geo, \
             patch("app.services.harbour._fetch_overpass", side_effect=_mock_overpass_empty):
            mock_geo.return_value.status_code = 200
            mock_geo.return_value.json.return_value = [
                {"lat": "40.7128", "lon": "-74.0060", "display_name": "New York"}
            ]
            resp = client.post("/recommend", json={"location": "New York"})
        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is True
