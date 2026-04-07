# models/request.py — Defines the shape of data the API *receives*.
#
# Pydantic models act like strict blueprints:
# - FastAPI automatically validates incoming JSON against them.
# - If a required field is missing or the wrong type, FastAPI returns a
#   clear 422 error before our code even runs.

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    """
    Body sent by the client when calling POST /recommend.

    Example JSON:
        {
            "postcode": "TR1 1AA",
            "species": "Bass",
            "preference": "best-chance"
        }
    """

    # The user's UK postcode — required, cannot be empty
    postcode: str = Field(
        ...,  # `...` means the field is required (no default)
        min_length=5,
        max_length=8,
        examples=["TR1 1AA"],
        description="UK postcode used to find the nearest harbour.",
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
