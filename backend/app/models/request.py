# models/request.py — Defines the shape of data the API *receives*.

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    """
    Body sent by the client when calling POST /recommend.

    Example JSON:
        {
            "location": "TR1 1AA",
            "species": "Bass",
            "preference": "best-chance"
        }
    """

    # A UK postcode or any place name — required
    location: str = Field(
        ...,
        min_length=2,
        max_length=100,
        examples=["TR1 1AA", "Falmouth", "New York"],
        description="UK postcode or place name used to find nearby harbours.",
    )

    # Which fish the user is targeting — optional, defaults to None
    species: Optional[str] = Field(
        default=None,
        examples=["Bass"],
        description="Target species. If omitted the recommendation is general.",
    )

    # How the user wants results ranked — optional, defaults to best-chance
    preference: Optional[Literal["closest", "best-chance", "calmer-conditions"]] = Field(
        default="best-chance",
        description="Optimisation strategy for the recommendation.",
    )
