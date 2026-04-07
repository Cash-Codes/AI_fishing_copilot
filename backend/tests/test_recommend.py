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

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

# A minimal valid request body — reused across tests.
VALID_BODY = {
    "postcode": "TR11AA",
    "species": "Bass",
    "preference": "best-chance",
}


# ── Happy path ────────────────────────────────────────────────────────────────

class TestRecommendHappyPath:
    def test_returns_200(self, client):
        response = client.post("/recommend", json=VALID_BODY)
        assert response.status_code == 200

    def test_echoes_input_postcode(self, client):
        """
        The frontend displays input_postcode to confirm which postcode was used.
        Verifying the echo here catches any accidental normalisation that would
        confuse the user.
        """
        response = client.post("/recommend", json=VALID_BODY)
        assert response.json()["input_postcode"] == VALID_BODY["postcode"]

    def test_omitting_species_still_succeeds(self, client):
        """species is optional — the endpoint must not 422 when it's absent."""
        body = {"postcode": "EX11AA", "preference": "closest"}
        response = client.post("/recommend", json=body)
        assert response.status_code == 200

    def test_omitting_preference_still_succeeds(self, client):
        """preference has a server-side default — omitting it must not 422."""
        body = {"postcode": "PL11AA"}
        response = client.post("/recommend", json=body)
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
        # autouse=True means this fixture runs automatically for every test in
        # this class. We store the parsed body on self so each test can access it.
        self.body = client.post("/recommend", json=VALID_BODY).json()

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
    fails validation. These tests prove our Field() constraints are correct —
    they catch the case where someone accidentally removes a constraint.
    """

    def test_missing_postcode_returns_422(self, client):
        response = client.post("/recommend", json={"preference": "closest"})
        assert response.status_code == 422

    def test_postcode_too_short_returns_422(self, client):
        # min_length=5 on the postcode field
        response = client.post("/recommend", json={"postcode": "TR1"})
        assert response.status_code == 422

    def test_postcode_too_long_returns_422(self, client):
        # max_length=8
        response = client.post("/recommend", json={"postcode": "TR1 1AA EXTRA"})
        assert response.status_code == 422

    def test_invalid_preference_returns_422(self, client):
        # preference must be one of the three Literal values
        response = client.post(
            "/recommend",
            json={"postcode": "TR11AA", "preference": "not-a-valid-option"},
        )
        assert response.status_code == 422

    def test_empty_body_returns_422(self, client):
        response = client.post("/recommend", json={})
        assert response.status_code == 422

    def test_422_body_contains_detail(self, client):
        """
        FastAPI's 422 response always includes a `detail` array describing
        which fields failed — useful for debugging and for the frontend to
        surface actionable error messages.
        """
        response = client.post("/recommend", json={})
        assert "detail" in response.json()
