# routers/recommend.py — The main AI recommendation endpoint.
#
# POST /recommend receives the user's postcode + preferences and returns
# a fishing recommendation with the *nearest real harbour* to their location.
#
# Resolution flow:
#   1. Resolve postcode → (lat, lon) via local seed map or postcodes.io API.
#   2. Find nearest harbour using Haversine distance.
#   3. If postcode is unknown, fall back to the default harbour and set
#      used_fallback=True so the client can show a notice.
#
# TODO: Replace the mock explanation with real AI logic:
#   1. Query the FAISS vector store for relevant fishing notes.
#   2. Call the Vertex AI / Gemini model with the notes as context.
#   3. Parse and return the model's structured response.

import logging

from fastapi import APIRouter

from app.models.request import RecommendRequest
from app.models.response import RecommendResponse
from app.retrieval.retriever import get_retriever
from app.services.ai_explanation import ExplanationContext, generate_explanation
from app.services.conditions import get_conditions
from app.services.harbour import default_harbour, nearest_harbour
from app.services.postcode import resolve_postcode
from app.services.scoring import score_recommendation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Recommend"])


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Get a fishing recommendation",
    description=(
        "Accepts a postcode and optional preferences, "
        "then returns the nearest harbour, best time window, "
        "and an AI-generated explanation."
    ),
)
def get_recommendation(body: RecommendRequest) -> RecommendResponse:
    """
    Core recommendation endpoint.

    FastAPI automatically:
      - Reads the JSON body and validates it against RecommendRequest.
      - Returns HTTP 422 if validation fails (e.g. postcode too short).
      - Serialises our return value to JSON using RecommendResponse.
    """
    logger.info(
        "Recommendation requested | postcode=%s | species=%s | preference=%s",
        body.postcode,
        body.species,
        body.preference,
    )

    # ── Step 1: resolve postcode ───────────────────────────────────────────────
    coords = resolve_postcode(body.postcode)
    used_fallback = coords is None

    if coords is not None:
        lat, lon = coords
        harbour, distance_km = nearest_harbour(lat, lon)
        logger.info(
            "Nearest harbour: %s (%.1f km from %s)",
            harbour.name,
            distance_km,
            body.postcode,
        )
    else:
        logger.warning(
            "Could not resolve postcode %s — using default harbour",
            body.postcode,
        )
        harbour, distance_km = default_harbour()

    # ── Step 2: fetch live conditions (weather + tides) ───────────────────────
    conditions = get_conditions(harbour)

    # ── Step 3: score the recommendation ──────────────────────────────────────
    score = score_recommendation(
        distance_km=distance_km,
        harbour=harbour,
        species=body.species,
        preference=body.preference,
    )
    logger.info(
        "Score | dist=%.2f species=%.2f weights=(%.2f, %.2f) → confidence=%.4f",
        score.distance_score,
        score.species_score,
        score.distance_weight,
        score.species_weight,
        score.confidence_score,
    )

    # ── Step 4: retrieve relevant corpus notes ────────────────────────────────
    # Build a natural-language query from the request context so the retriever
    # can find the most relevant guidance snippets.
    retrieval_query = " ".join(filter(None, [
        body.species,
        harbour.name,
        conditions.tide_phase,
        conditions.spring_or_neap,
        body.preference,
        "fishing",
    ]))
    retrieved_notes = get_retriever().retrieve_text(retrieval_query, top_k=3)
    logger.info("Retrieved %d notes for query: %r", len(retrieved_notes), retrieval_query)

    # ── Step 5: generate AI explanation ──────────────────────────────────────
    ai_ctx = ExplanationContext(
        postcode=body.postcode,
        species=body.species,
        preference=body.preference,
        harbour_name=harbour.name,
        harbour_description=harbour.short_description,
        distance_km=distance_km,
        recommendation_window=conditions.recommended_time_window,
        confidence_score=score.confidence_score,
        conditions_summary=conditions.conditions_summary,
        retrieved_notes=retrieved_notes,
    )
    ai_result = generate_explanation(ai_ctx)

    # used_fallback is True if either the postcode lookup OR the AI call fell back
    final_fallback = used_fallback or not ai_result.used_ai
    logger.info(
        "Explanation | used_ai=%s | fallback=%s", ai_result.used_ai, final_fallback
    )

    return RecommendResponse(
        input_postcode=body.postcode,
        nearest_harbour=harbour.name,
        recommendation_window=conditions.recommended_time_window,
        confidence_score=score.confidence_score,
        explanation=ai_result.text,
        used_fallback=final_fallback,
        retrieved_notes=retrieved_notes,
        # Conditions fields
        wind_speed_knots=conditions.wind_speed_knots,
        wind_direction=conditions.wind_direction,
        wind_description=conditions.wind_description,
        wave_height_m=conditions.wave_height_m,
        sea_state=conditions.sea_state,
        tide_phase=conditions.tide_phase,
        spring_or_neap=conditions.spring_or_neap,
        conditions_summary=conditions.conditions_summary,
    )
