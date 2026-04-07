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

    # ── Step 4: build response ────────────────────────────────────────────────
    # The explanation text is still template-based.
    # A future iteration will replace this with a real AI-generated narrative.

    distance_note = (
        f"{distance_km:.0f} km from {body.postcode}"
        if distance_km >= 0
        else "location could not be determined from postcode"
    )

    explanation = (
        f"{harbour.name} is your nearest harbour ({distance_note}). "
        f"{harbour.short_description} "
        f"Conditions today: {conditions.conditions_summary} "
        f"Targeting {body.species or 'general sea fishing'} with a preference "
        f'for "{body.preference}".'
    )

    retrieved_notes = [
        f"{conditions.tide_phase} tide ({conditions.spring_or_neap.lower()}, "
        f"coefficient {conditions.tidal_coefficient:.2f}) — "
        + ("strong tidal flow expected." if conditions.tidal_coefficient > 0.7
           else "moderate tidal flow."),
        f"{conditions.wind_description} ({conditions.wind_speed_knots:.0f} kn "
        f"{conditions.wind_direction}) — "
        + ("conditions are challenging." if conditions.wind_speed_knots > 20
           else "manageable conditions near the headland."),
        f"{conditions.sea_state} swell ({conditions.wave_height_m:.1f} m). "
        f"Next high water at {conditions.next_high_water}.",
    ]

    return RecommendResponse(
        input_postcode=body.postcode,
        nearest_harbour=harbour.name,
        recommendation_window=conditions.recommended_time_window,
        confidence_score=score.confidence_score,
        explanation=explanation,
        used_fallback=used_fallback,
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
