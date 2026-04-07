# routers/recommend.py — The main AI recommendation endpoint.
#
# POST /recommend receives the user's postcode + preferences and returns
# a fishing recommendation. Right now it returns hardcoded mock data.
#
# TODO: Replace the mock response with real logic:
#   1. Look up the nearest harbour from the postcode.
#   2. Query the FAISS vector store for relevant fishing notes.
#   3. Call the Vertex AI / Gemini model with the notes as context.
#   4. Parse and return the model's response.

import logging

from fastapi import APIRouter

from app.models.request import RecommendRequest
from app.models.response import RecommendResponse

# Standard Python logger — messages appear in the terminal when you run the server
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
    # Log the incoming request so we can see activity in the terminal
    logger.info(
        "Recommendation requested | postcode=%s | species=%s | preference=%s",
        body.postcode,
        body.species,
        body.preference,
    )

    # ── Mock response ──────────────────────────────────────────────────────────
    # This is placeholder data. Replace this entire block once the real
    # harbour lookup, vector search, and AI call are implemented.

    mock_notes = [
        "Spring tide Saturday — strong tidal flow, good for Bass.",
        "SW wind 12 knots — manageable conditions near the headland.",
        "Water temperature 14 °C — Bass actively feeding.",
    ]

    mock_explanation = (
        f"Based on your postcode ({body.postcode}) and a preference for "
        f'"{body.preference}", Falmouth Harbour is the closest match. '
        f"Tidal flow peaks Saturday morning with light south-westerly winds "
        f"and a 0.8 m swell — ideal conditions for "
        f"{body.species or 'general sea fishing'}."
    )

    return RecommendResponse(
        input_postcode=body.postcode,
        nearest_harbour="Falmouth Harbour",
        recommendation_window="Saturday 06:00 – 10:00",
        confidence_score=0.82,
        explanation=mock_explanation,
        used_fallback=False,
        retrieved_notes=mock_notes,
    )
    # ── End mock response ──────────────────────────────────────────────────────
