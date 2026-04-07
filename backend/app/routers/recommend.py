# routers/recommend.py — The main AI recommendation endpoint.
#
# POST /recommend accepts a location (postcode or place name) and returns
# a fishing recommendation for the harbour that best matches the user's
# stated preference.
#
# Resolution flow:
#   1. Resolve location → (lat, lon) via postcodes.io or Nominatim.
#   2. Find the 5 nearest harbours from Overpass/OSM (+ local fallback).
#   3. Fetch live conditions for every candidate in parallel.
#   4. Select the best harbour for the user's preference:
#        closest           → nearest by distance
#        calmer-conditions → calmest sea/wind
#        best-chance       → species season match + tidal quality
#   5. If location is unknown, fall back to the default harbour.
#   6. Score the selected harbour → confidence score.
#   7. Retrieve relevant corpus notes via FAISS / keyword search.
#   8. Generate an AI explanation (Vertex AI Gemini, or template fallback).

import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter

from app.models.request import RecommendRequest
from app.models.response import RecommendResponse
from app.retrieval.retriever import get_retriever
from app.services.ai_explanation import ExplanationContext, generate_explanation
from app.services.conditions import get_conditions
from app.services.geocoding import resolve_location
from app.services.harbour import MAX_USEFUL_DISTANCE_KM, default_harbour, nearest_harbours
from app.services.scoring import score_recommendation, select_harbour

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Recommend"])

_NUM_CANDIDATES = 5   # how many nearby harbours to evaluate per request


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Get a fishing recommendation",
    description=(
        "Accepts a postcode or place name and optional preferences, "
        "then returns the best harbour for the user's stated preference, "
        "with a tidal window and an AI-generated explanation."
    ),
)
def get_recommendation(body: RecommendRequest) -> RecommendResponse:
    logger.info(
        "Recommendation requested | location=%s | species=%s | preference=%s",
        body.location,
        body.species,
        body.preference,
    )

    # ── Step 1: resolve location ───────────────────────────────────────────────
    coords = resolve_location(body.location)
    used_fallback = coords is None

    if coords is not None:
        lat, lon = coords

        # ── Step 2: find N nearest candidates ─────────────────────────────────
        candidates, out_of_range = nearest_harbours(lat, lon, n=_NUM_CANDIDATES)
        logger.info(
            "Candidates for %s: %s",
            body.location,
            ", ".join(f"{h.name} ({d:.0f} km)" for h, d in candidates),
        )

        # When the location is outside coverage, return immediately with a
        # helpful message rather than silently recommending a harbour thousands
        # of km away.
        if out_of_range:
            logger.warning(
                "Location %r is out of range (nearest harbour %.0f km) — returning early",
                body.location, candidates[0][1],
            )
            retriever = get_retriever()
            return RecommendResponse(
                input_location=body.location,
                nearest_harbour=candidates[0][0].name,
                recommendation_window="N/A — outside coverage",
                confidence_score=0.0,
                explanation=(
                    f"No coastal fishing harbours were found within "
                    f"{MAX_USEFUL_DISTANCE_KM:.0f} km of '{body.location}'. "
                    f"This service covers sea fishing — try a UK coastal town, "
                    f"harbour name, or postcode (e.g. 'Falmouth', 'TR11 3JT')."
                ),
                used_fallback=True,
                out_of_range=True,
                retrieved_notes=[],
                retrieval_method=retriever.retrieval_method,
            )

        # ── Step 3: fetch conditions in parallel ───────────────────────────────
        with ThreadPoolExecutor(max_workers=_NUM_CANDIDATES) as pool:
            all_conditions = list(pool.map(
                lambda hd: get_conditions(hd[0]),
                candidates,
            ))

        # ── Step 4: select best harbour for the preference ────────────────────
        best_idx = select_harbour(
            candidates,
            all_conditions,
            species=body.species,
            preference=body.preference,
        )
        harbour, distance_km = candidates[best_idx]
        conditions = all_conditions[best_idx]

    else:
        logger.warning(
            "Could not resolve location %r — using default harbour",
            body.location,
        )
        harbour, distance_km = default_harbour()
        conditions = get_conditions(harbour)

    # ── Step 5: score the recommendation ──────────────────────────────────────
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

    # ── Step 6: retrieve relevant corpus notes ────────────────────────────────
    # Two-stage retrieval: species-filtered notes (when a species is given) plus
    # a general tidal/conditions note, then deduplicate.  This mirrors production
    # RAG systems that use metadata filtering to pre-restrict the candidate pool
    # before semantic search.
    retriever = get_retriever()

    if body.species:
        # Stage 1: species-specific notes, filtered to species_activity topic
        species_notes = retriever.retrieve_text(
            f"{body.species} feeding season habitat behaviour",
            top_k=2,
            filter_topic="species_activity",
        )
        # Stage 2: tidal/conditions context from full corpus
        tidal_query = " ".join(filter(None, [
            conditions.tide_phase, conditions.spring_or_neap,
            harbour.name, "fishing",
        ]))
        tidal_notes = retriever.retrieve_text(tidal_query, top_k=2)
        # Deduplicate while preserving order (species notes first)
        seen: set = set()
        retrieved_notes = []
        for note in species_notes + tidal_notes:
            if note not in seen:
                seen.add(note)
                retrieved_notes.append(note)
        retrieved_notes = retrieved_notes[:3]
    else:
        # No species: single-stage retrieval across full corpus
        retrieval_query = " ".join(filter(None, [
            harbour.name,
            conditions.tide_phase,
            conditions.spring_or_neap,
            body.preference,
            "fishing",
        ]))
        retrieved_notes = retriever.retrieve_text(retrieval_query, top_k=3)

    logger.info(
        "Retrieved %d notes | method=%s | species_filter=%s",
        len(retrieved_notes),
        retriever.retrieval_method,
        "species_activity" if body.species else "none",
    )

    # ── Step 7: generate AI explanation ───────────────────────────────────────
    ai_ctx = ExplanationContext(
        postcode=body.location,
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

    final_fallback = used_fallback or not ai_result.used_ai
    logger.info(
        "Explanation | used_ai=%s | fallback=%s", ai_result.used_ai, final_fallback
    )

    return RecommendResponse(
        input_location=body.location,
        nearest_harbour=harbour.name,
        recommendation_window=conditions.recommended_time_window,
        confidence_score=score.confidence_score,
        explanation=ai_result.text,
        used_fallback=final_fallback,
        out_of_range=False,
        retrieved_notes=retrieved_notes,
        retrieval_method=retriever.retrieval_method,
        wind_speed_knots=conditions.wind_speed_knots,
        wind_direction=conditions.wind_direction,
        wind_description=conditions.wind_description,
        wave_height_m=conditions.wave_height_m,
        sea_state=conditions.sea_state,
        tide_phase=conditions.tide_phase,
        spring_or_neap=conditions.spring_or_neap,
        conditions_summary=conditions.conditions_summary,
    )
