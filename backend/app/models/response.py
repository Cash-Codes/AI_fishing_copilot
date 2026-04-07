# models/response.py — Defines the shape of data the API *returns*.
#
# Pydantic response models:
# - Document what the client can expect to receive.
# - FastAPI uses them to serialise (convert) Python objects → JSON.
# - They also power the automatic /docs page.

from typing import List, Optional

from pydantic import BaseModel, Field


class RecommendResponse(BaseModel):
    """
    Body returned by POST /recommend.

    Example JSON:
        {
            "input_postcode": "TR1 1AA",
            "nearest_harbour": "Falmouth Harbour",
            "recommendation_window": "Saturday 06:00 – 10:00",
            "confidence_score": 0.82,
            "explanation": "Tidal flow peaks Saturday morning …",
            "used_fallback": false,
            "retrieved_notes": ["Spring tide Saturday", "SW wind 12 knots"]
        }
    """

    # The location we received — echoed back so the client can confirm
    input_location: str = Field(description="The postcode or place name that was submitted.")

    # Closest harbour found for that postcode
    nearest_harbour: str = Field(description="Name of the nearest suitable harbour.")

    # Human-readable time window for the best fishing conditions
    recommendation_window: str = Field(
        description="Suggested date/time range, e.g. 'Saturday 06:00 – 10:00'."
    )

    # How confident the AI is in the recommendation (0.0 = low, 1.0 = certain)
    confidence_score: float = Field(
        ge=0.0,  # must be >= 0
        le=1.0,  # must be <= 1
        description="Confidence level between 0.0 and 1.0.",
    )

    # Plain-English reason for the recommendation
    explanation: str = Field(description="AI-generated explanation of the recommendation.")

    # True when live data was unavailable and we fell back to static rules
    used_fallback: bool = Field(
        description="Whether fallback logic was used instead of live AI data."
    )

    # True when the resolved location is > MAX_USEFUL_DISTANCE_KM from any harbour
    out_of_range: bool = Field(
        default=False,
        description="True when the location is outside the service's coverage area.",
    )

    # Short notes pulled from the knowledge base (FAISS / vector store)
    retrieved_notes: List[str] = Field(
        default_factory=list,
        description="Relevant notes retrieved from the knowledge base.",
    )

    # Which retrieval strategy was used — surfaced so callers can confirm
    # semantic search is active ("hybrid-rrf") vs keyword fallback ("bm25").
    retrieval_method: Optional[str] = Field(
        default=None,
        description="Retrieval strategy: 'hybrid-rrf', 'faiss', or 'bm25'.",
    )

    # ── Conditions fields (weather + tides) ───────────────────────────────────
    # All optional so existing tests that build minimal responses don't break.

    wind_speed_knots: Optional[float] = Field(
        default=None,
        description="Current wind speed at the harbour in knots.",
    )
    wind_direction: Optional[str] = Field(
        default=None,
        description="Wind direction as a compass point (e.g. 'SW').",
    )
    wind_description: Optional[str] = Field(
        default=None,
        description="Beaufort plain-English wind description.",
    )
    wave_height_m: Optional[float] = Field(
        default=None,
        description="Significant wave height in metres.",
    )
    sea_state: Optional[str] = Field(
        default=None,
        description="Douglas scale sea-state description (e.g. 'Slight').",
    )
    tide_phase: Optional[str] = Field(
        default=None,
        description="Current tidal phase: Flood, High Water, Ebb, or Low Water.",
    )
    spring_or_neap: Optional[str] = Field(
        default=None,
        description="Whether it is a spring or neap tide.",
    )
    conditions_summary: Optional[str] = Field(
        default=None,
        description="One-sentence summary of current conditions.",
    )


class HealthResponse(BaseModel):
    """Returned by GET /health to confirm the service is running."""

    status: str = Field(examples=["ok"])
    version: Optional[str] = Field(default=None, examples=["0.1.0"])
