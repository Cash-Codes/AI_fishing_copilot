# services/ai_explanation.py — AI-generated recommendation explanations via Vertex AI.
#
# Configuration is read from app.settings (which sources environment variables):
#   ENABLE_VERTEX_AI       — master on/off switch (default: true)
#   GOOGLE_CLOUD_PROJECT   — GCP project ID (required when AI is enabled)
#   GOOGLE_CLOUD_REGION    — Vertex AI region  (default: "us-central1")
#   VERTEX_AI_MODEL        — Gemini model ID   (default: "gemini-2.5-flash")
#
# Authentication is handled by the Google SDK via Application Default Credentials
# (ADC).  Locally: `gcloud auth application-default login` or set
# GOOGLE_APPLICATION_CREDENTIALS to the path of a service account key file.
# In production on GCP: no extra config needed — the instance identity is used.
#
# If AI is disabled or GOOGLE_CLOUD_PROJECT is unset, or if the Vertex AI call
# fails for any reason, the module returns a template explanation (used_ai=False).
# The recommendation endpoint marks used_fallback=True so the client knows.

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Imported at module level so tests can patch app.services.ai_explanation.vertexai
# and app.services.ai_explanation.GenerativeModel.  The try/except means the rest
# of the app still works when google-cloud-aiplatform is not installed.
try:
    import vertexai
    from vertexai.generative_models import GenerationConfig, GenerativeModel
    _VERTEXAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _VERTEXAI_AVAILABLE = False


# ─── Input / output types ─────────────────────────────────────────────────────

@dataclass
class ExplanationContext:
    """Everything needed to build the prompt and the template fallback."""

    postcode: str
    species: Optional[str]
    preference: Optional[str]
    harbour_name: str
    harbour_description: str   # short_description from harbours.json
    distance_km: float         # -1.0 when unknown
    recommendation_window: str
    confidence_score: float    # 0–1
    conditions_summary: str
    retrieved_notes: List[str]


@dataclass
class ExplanationResult:
    """The generated explanation and how it was produced."""

    text: str
    used_ai: bool   # True = Vertex AI  /  False = template fallback


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_prompt(ctx: ExplanationContext) -> str:
    """Compose the Vertex AI prompt from the recommendation context.

    The prompt is structured so the model has all the facts it needs but is
    not over-constrained — it should sound like a knowledgeable local angler,
    not a data-dump.
    """
    species_str = ctx.species or "general sea fishing"
    preference_str = ctx.preference or "best-chance"

    if ctx.distance_km >= 0:
        dist_str = f"{ctx.distance_km:.0f} km from {ctx.postcode}"
    else:
        dist_str = "your nearest harbour"

    notes_block = "\n".join(f"- {note}" for note in ctx.retrieved_notes) or "None available."

    return f"""\
You are a helpful UK sea fishing assistant giving advice to an angler.
Write a friendly, specific recommendation in exactly 2-3 sentences.
Sound like an experienced local angler — practical, encouraging, and concise.
Do not use markdown, bullet points, or headings. Plain sentences only.

Angler's request
  Postcode: {ctx.postcode}
  Target species: {species_str}
  Preference: {preference_str}

Recommendation
  Nearest harbour: {ctx.harbour_name} ({dist_str})
  Harbour notes: {ctx.harbour_description}
  Best window today: {ctx.recommendation_window}
  Conditions: {ctx.conditions_summary}
  Confidence: {ctx.confidence_score:.0%}

Relevant fishing guidance
{notes_block}

Write the recommendation now (2-3 sentences, no markdown):"""


# ─── Template fallback ────────────────────────────────────────────────────────

def _template_explanation(ctx: ExplanationContext) -> ExplanationResult:
    """Return a deterministic template explanation when AI is unavailable.

    This is always correct, never empty, and requires no external service.
    It is the guaranteed safe path for the recommendation endpoint.
    """
    dist_note = (
        f"{ctx.distance_km:.0f} km from {ctx.postcode}"
        if ctx.distance_km >= 0
        else "your nearest harbour"
    )
    species_str = ctx.species or "general sea fishing"
    text = (
        f"{ctx.harbour_name} is your best match ({dist_note}). "
        f"{ctx.harbour_description} "
        f"Best window today: {ctx.recommendation_window}. "
        f"Targeting {species_str} — confidence {ctx.confidence_score:.0%}."
    )
    return ExplanationResult(text=text, used_ai=False)


# ─── Vertex AI call ───────────────────────────────────────────────────────────

def _vertex_generate(ctx: ExplanationContext) -> ExplanationResult:
    """Call Vertex AI Gemini.  Raises on any failure — caller handles fallback."""
    settings = get_settings()

    vertexai.init(
        project=settings.google_cloud_project,
        location=settings.google_cloud_region,
    )
    model = GenerativeModel(settings.vertex_ai_model)

    prompt = _build_prompt(ctx)
    response = model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.4,      # slightly creative but mostly factual
            max_output_tokens=220,
            candidate_count=1,
        ),
    )

    text = response.text.strip() if response.text else ""
    if not text:
        raise ValueError("Vertex AI returned an empty response")

    logger.info(
        "Vertex AI explanation | model=%s | ~%d words",
        settings.vertex_ai_model, len(text.split()),
    )
    return ExplanationResult(text=text, used_ai=True)


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_explanation(ctx: ExplanationContext) -> ExplanationResult:
    """Generate a recommendation explanation, with automatic fallback.

    Resolution order:
      1. ENABLE_VERTEX_AI=false or GOOGLE_CLOUD_PROJECT unset → template
      2. Call Vertex AI Gemini → return AI text
      3. On any exception → log warning, return template

    The caller is responsible for reflecting used_ai=False as used_fallback=True
    in the API response when that behaviour is desired.
    """
    settings = get_settings()

    if not settings.vertex_ai_ready:
        reason = (
            "ENABLE_VERTEX_AI=false"
            if not settings.enable_vertex_ai
            else "GOOGLE_CLOUD_PROJECT not set"
        )
        logger.debug("Skipping Vertex AI (%s) — using template explanation", reason)
        return _template_explanation(ctx)

    try:
        return _vertex_generate(ctx)
    except Exception as exc:
        logger.warning("Vertex AI explanation failed (%s) — using template", exc)
        return _template_explanation(ctx)
