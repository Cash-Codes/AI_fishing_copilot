# tests/test_ai_explanation.py — Tests for the AI explanation service.
#
# Vertex AI is always mocked — tests never make real GCP calls.
# Environment variables are patched per-test so the module state is isolated.

import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai_explanation import (
    ExplanationContext,
    ExplanationResult,
    _build_prompt,
    _template_explanation,
    _vertex_generate,
    generate_explanation,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

CTX = ExplanationContext(
    postcode="TR1 1AA",
    species="Bass",
    preference="best-chance",
    harbour_name="Falmouth Harbour",
    harbour_description="Sheltered deep-water harbour on the Fal estuary.",
    distance_km=8.0,
    recommendation_window="06:30–09:30 UTC (flood into high water)",
    confidence_score=0.84,
    conditions_summary="Moderate breeze (14 kn SW), slight swell (0.8 m), spring flood tide.",
    retrieved_notes=[
        "Bass feed aggressively on the flood tide over shallow rocky ground.",
        "Spring tides produce stronger currents — ideal for Bass near headlands.",
    ],
)

CTX_NO_SPECIES = ExplanationContext(
    postcode="BH15 1HJ",
    species=None,
    preference="closest",
    harbour_name="Poole Quay",
    harbour_description="Second-largest natural harbour in the world.",
    distance_km=2.0,
    recommendation_window="08:00–11:00 UTC (flood into high water)",
    confidence_score=0.61,
    conditions_summary="Light breeze (6 kn NE), smooth swell (0.3 m), neap flood tide.",
    retrieved_notes=[],
)

CTX_FALLBACK = ExplanationContext(
    postcode="ZZ9 9ZZ",
    species=None,
    preference=None,
    harbour_name="Falmouth Harbour",
    harbour_description="Sheltered deep-water harbour on the Fal estuary.",
    distance_km=-1.0,
    recommendation_window="07:00–10:00 UTC",
    confidence_score=0.30,
    conditions_summary="Gentle breeze, slight swell.",
    retrieved_notes=[],
)


# ─── _build_prompt ────────────────────────────────────────────────────────────

class TestBuildPrompt:

    def test_contains_postcode(self):
        assert "TR1 1AA" in _build_prompt(CTX)

    def test_contains_harbour_name(self):
        assert "Falmouth Harbour" in _build_prompt(CTX)

    def test_contains_species(self):
        assert "Bass" in _build_prompt(CTX)

    def test_contains_time_window(self):
        assert "06:30–09:30" in _build_prompt(CTX)

    def test_contains_confidence_score(self):
        prompt = _build_prompt(CTX)
        assert "84%" in prompt

    def test_contains_conditions_summary(self):
        assert "Moderate breeze" in _build_prompt(CTX)

    def test_contains_retrieved_notes(self):
        prompt = _build_prompt(CTX)
        assert "flood tide" in prompt.lower()

    def test_no_species_uses_general_fishing(self):
        assert "general sea fishing" in _build_prompt(CTX_NO_SPECIES)

    def test_unknown_distance_uses_nearest_harbour_phrase(self):
        prompt = _build_prompt(CTX_FALLBACK)
        assert "nearest harbour" in prompt

    def test_no_notes_shows_fallback_text(self):
        prompt = _build_prompt(CTX_NO_SPECIES)
        assert "None available" in prompt


# ─── _template_explanation ────────────────────────────────────────────────────

class TestTemplateExplanation:

    def test_returns_explanation_result(self):
        result = _template_explanation(CTX)
        assert isinstance(result, ExplanationResult)

    def test_used_ai_is_false(self):
        assert _template_explanation(CTX).used_ai is False

    def test_text_contains_harbour_name(self):
        assert "Falmouth Harbour" in _template_explanation(CTX).text

    def test_text_contains_species(self):
        assert "Bass" in _template_explanation(CTX).text

    def test_text_contains_time_window(self):
        assert "06:30" in _template_explanation(CTX).text

    def test_unknown_distance_uses_nearest_harbour(self):
        result = _template_explanation(CTX_FALLBACK)
        assert "nearest harbour" in result.text

    def test_no_species_uses_general_fishing(self):
        result = _template_explanation(CTX_NO_SPECIES)
        assert "general sea fishing" in result.text

    def test_text_is_non_empty(self):
        assert len(_template_explanation(CTX).text) > 20


# ─── _vertex_generate ────────────────────────────────────────────────────────

class TestVertexGenerate:

    def _mock_vertexai(self, response_text: str = "Excellent Bass conditions today."):
        """Return a context manager that patches vertexai and GenerativeModel."""
        mock_response = MagicMock()
        mock_response.text = response_text

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        mock_gm_class = MagicMock(return_value=mock_model)

        return (
            patch("app.services.ai_explanation.vertexai"),
            patch("app.services.ai_explanation.GenerativeModel", mock_gm_class),
            mock_model,
        )

    def test_returns_ai_text(self):
        init_patch = patch("app.services.ai_explanation.vertexai")
        model_response = MagicMock()
        model_response.text = "Head to Falmouth for excellent Bass on the flood."
        mock_model = MagicMock()
        mock_model.generate_content.return_value = model_response
        gm_patch = patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model)

        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with init_patch, gm_patch, patch.dict(os.environ, env, clear=False):
            result = _vertex_generate(CTX)

        assert "Falmouth" in result.text
        assert result.used_ai is True

    def test_used_ai_is_true(self):
        mock_response = MagicMock()
        mock_response.text = "Good conditions."
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model), \
             patch.dict(os.environ, env, clear=False):
            result = _vertex_generate(CTX)

        assert result.used_ai is True

    def test_empty_response_raises(self):
        mock_response = MagicMock()
        mock_response.text = ""
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model), \
             patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValueError, match="empty response"):
                _vertex_generate(CTX)

    def test_uses_project_from_env(self):
        mock_init = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Good fishing."
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        env = {
            "GOOGLE_CLOUD_PROJECT": "my-project-123",
            "GOOGLE_CLOUD_REGION": "europe-west2",
        }
        with patch("app.services.ai_explanation.vertexai") as mock_vtx, \
             patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model), \
             patch.dict(os.environ, env, clear=False):
            mock_vtx.init = mock_init
            _vertex_generate(CTX)

        mock_init.assert_called_once_with(
            project="my-project-123", location="europe-west2"
        )

    def test_uses_model_from_env(self):
        mock_response = MagicMock()
        mock_response.text = "Good fishing."
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_gm_class = MagicMock(return_value=mock_model_instance)

        env = {
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "VERTEX_AI_MODEL": "gemini-2.5-flash-lite",
        }
        with patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel", mock_gm_class), \
             patch.dict(os.environ, env, clear=False):
            _vertex_generate(CTX)

        mock_gm_class.assert_called_once_with("gemini-2.5-flash-lite")


# ─── generate_explanation (public API) ────────────────────────────────────────

class TestGenerateExplanation:

    def test_returns_template_when_project_unset(self):
        # Ensure GOOGLE_CLOUD_PROJECT is absent
        env = {k: v for k, v in os.environ.items() if k != "GOOGLE_CLOUD_PROJECT"}
        with patch.dict(os.environ, env, clear=True):
            result = generate_explanation(CTX)
        assert result.used_ai is False

    def test_returns_ai_result_when_project_set(self):
        mock_response = MagicMock()
        mock_response.text = "Excellent Bass today at Falmouth."
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model), \
             patch.dict(os.environ, env, clear=False):
            result = generate_explanation(CTX)

        assert result.used_ai is True
        assert "Falmouth" in result.text

    def test_falls_back_on_vertex_exception(self):
        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel",
                   side_effect=Exception("quota exceeded")), \
             patch.dict(os.environ, env, clear=False):
            result = generate_explanation(CTX)

        assert result.used_ai is False
        assert len(result.text) > 10   # template always returns something

    def test_falls_back_on_network_error(self):
        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel",
                   side_effect=ConnectionError("network unreachable")), \
             patch.dict(os.environ, env, clear=False):
            result = generate_explanation(CTX)

        assert result.used_ai is False

    def test_template_fallback_is_non_empty(self):
        env = {k: v for k, v in os.environ.items() if k != "GOOGLE_CLOUD_PROJECT"}
        with patch.dict(os.environ, env, clear=True):
            result = generate_explanation(CTX_FALLBACK)
        assert result.text.strip() != ""


# ─── Integration: recommend endpoint reflects used_fallback ───────────────────

class TestRecommendAiFallback:
    """Verify the endpoint sets used_fallback correctly based on AI outcome."""

    def _mock_geo_success(self):
        """Returns a mock httpx response that resolves TR1 1AA → Truro coords."""
        m = MagicMock()
        m.status_code = 200
        m.json.return_value = {"result": {"latitude": 50.2632, "longitude": -5.0510}}
        return m

    def test_used_fallback_false_when_ai_succeeds(self, client):
        mock_response = MagicMock()
        mock_response.text = "Great Bass conditions at Falmouth today."
        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.geocoding.httpx.get", return_value=self._mock_geo_success()), \
             patch("app.services.harbour._fetch_overpass", return_value=()), \
             patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel", return_value=mock_model), \
             patch.dict(os.environ, env, clear=False):
            resp = client.post("/recommend", json={"location": "TR1 1AA", "species": "Bass"})

        assert resp.status_code == 200
        data = resp.json()
        # used_fallback is False only when location resolved AND AI succeeded
        assert data["used_fallback"] is False
        assert data["explanation"] == "Great Bass conditions at Falmouth today."

    def test_used_fallback_true_when_ai_fails(self, client):
        env = {"GOOGLE_CLOUD_PROJECT": "test-project"}
        with patch("app.services.geocoding.httpx.get", return_value=self._mock_geo_success()), \
             patch("app.services.harbour._fetch_overpass", return_value=()), \
             patch("app.services.ai_explanation.vertexai"), \
             patch("app.services.ai_explanation.GenerativeModel",
                   side_effect=Exception("auth error")), \
             patch.dict(os.environ, env, clear=False):
            resp = client.post("/recommend", json={"location": "TR1 1AA"})

        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is True

    def test_used_fallback_true_when_project_unset(self, client):
        env = {k: v for k, v in os.environ.items() if k != "GOOGLE_CLOUD_PROJECT"}
        with patch("app.services.geocoding.httpx.get", return_value=self._mock_geo_success()), \
             patch("app.services.harbour._fetch_overpass", return_value=()), \
             patch.dict(os.environ, env, clear=True):
            resp = client.post("/recommend", json={"location": "TR1 1AA"})
        assert resp.status_code == 200
        assert resp.json()["used_fallback"] is True
