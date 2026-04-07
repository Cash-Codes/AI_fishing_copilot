# data/loader.py — Typed loading utility for local sample data.
#
# Reads the JSON files bundled alongside this module and returns them as lists
# of validated Pydantic models.  The data is loaded once at import time and
# cached in module-level variables so every caller shares the same objects
# without re-reading the files.
#
# Usage:
#   from app.data.loader import get_harbours, get_species
#   harbours = get_harbours()   # List[Harbour]
#   species  = get_species()    # List[Species]

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

# The directory that contains this file — used to locate the JSON files
# regardless of where the app is launched from.
_DATA_DIR = Path(__file__).parent


# ─── Domain models ────────────────────────────────────────────────────────────

class Harbour(BaseModel):
    """A fishing harbour with location metadata.

    postcode and short_description are optional so harbours sourced from
    the Overpass/OSM API (which don't carry this extra metadata) can be
    represented without dummy sentinel values in the call sites.
    """

    id: str
    name: str
    latitude: float
    longitude: float
    postcode: str = ""
    short_description: str = ""


class Species(BaseModel):
    """A target fish species with seasonal and conditions guidance."""

    species_name: str
    best_season: str
    notes: str
    preferred_conditions: str


# ─── Loaders ──────────────────────────────────────────────────────────────────
# @lru_cache(maxsize=None) caches the return value after the first call.
# Subsequent calls return the cached list without re-reading the file.

@lru_cache(maxsize=None)
def get_harbours() -> List[Harbour]:
    """Load and return all harbours from harbours.json."""
    raw = json.loads((_DATA_DIR / "harbours.json").read_text(encoding="utf-8"))
    return [Harbour(**record) for record in raw]


@lru_cache(maxsize=None)
def get_species() -> List[Species]:
    """Load and return all species from species.json."""
    raw = json.loads((_DATA_DIR / "species.json").read_text(encoding="utf-8"))
    return [Species(**record) for record in raw]


# ─── Lookup helpers ───────────────────────────────────────────────────────────

def get_harbour_by_id(harbour_id: str) -> Optional[Harbour]:
    """Return a single Harbour by its id, or None if not found."""
    return next((h for h in get_harbours() if h.id == harbour_id), None)


def get_species_by_name(name: str) -> Optional[Species]:
    """Return a Species by name (case-insensitive), or None if not found."""
    name_lower = name.lower()
    return next((s for s in get_species() if s.species_name.lower() == name_lower), None)
