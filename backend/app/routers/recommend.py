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
from app.services.harbour import default_harbour, nearest_harbour
from app.services.postcode import resolve_postcode

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

    # ── Step 2: build response ─────────────────────────────────────────────────
    # The explanation and window are still placeholder text.
    # They will be replaced by a real AI call in a later iteration.

    distance_note = (
        f"{distance_km:.0f} km from {body.postcode}"
        if distance_km >= 0
        else "location could not be determined from postcode"
    )

    explanation = (
        f"{harbour.name} is your nearest harbour ({distance_note}). "
        f"{harbour.short_description} "
        f"Targeting {body.species or 'general sea fishing'} with a preference "
        f'for "{body.preference}".'
    )

    mock_notes = [
        "Spring tide Saturday — strong tidal flow, good for Bass.",
        "SW wind 12 knots — manageable conditions near the headland.",
        "Water temperature 14 °C — Bass actively feeding.",
    ]

    return RecommendResponse(
        input_postcode=body.postcode,
        nearest_harbour=harbour.name,
        recommendation_window="Saturday 06:00 – 10:00",
        confidence_score=0.82,
        explanation=explanation,
        used_fallback=used_fallback,
        retrieved_notes=mock_notes,
    )
