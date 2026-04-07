# tests/test_retrieval.py — Tests for keyword, FAISS, and hybrid retrieval.
#
# FAISS tests use hand-crafted 4-dim embeddings and a mock Embedder so the
# actual fastembed model is never loaded during the unit-test run.
# The live-index tests at the bottom do load the real index (fast — no model
# inference needed for retrieval, only for query embedding).

from unittest.mock import MagicMock

import numpy as np

from app.retrieval.retriever import (
    BaseRetriever,
    Chunk,
    FaissRetriever,
    HybridRetriever,
    KeywordRetriever,
    _keyword_score,
    get_retriever,
    tokenise,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_chunk(chunk_id, topic, heading, text, embedding=None):
    return Chunk(
        chunk_id=chunk_id, topic=topic, heading=heading,
        text=text, word_count=len(text.split()), embedding=embedding,
    )


TIDE_CHUNK = _make_chunk(
    "tide_001", "tide_basics", "Spring Tides",
    "Spring tides occur at new moon and full moon. "
    "They produce stronger currents and higher high waters. "
    "Bass feed aggressively during spring flood tides.",
)
BASS_CHUNK = _make_chunk(
    "species_001", "species_activity", "Bass Activity",
    "Bass are warm-water predators that feed on the flood tide. "
    "Peak Bass season is May to October in the south-west. "
    "They prefer water temperatures above 12 degrees Celsius.",
)
SAFETY_CHUNK = _make_chunk(
    "safety_001", "safety_notes", "Tidal Cut-offs",
    "Never be caught by a rising tide on rocky ground. "
    "Always check the tide table before leaving the car. "
    "Begin your exit at least one hour before the path floods.",
)
HARBOUR_CHUNK = _make_chunk(
    "harbour_001", "harbour_selection", "Choosing a Harbour",
    "Choose a harbour within 30 to 45 minutes of home for a half-day session. "
    "Sheltered harbours are fishable in most weather conditions. "
    "Charter ports offer access to deeper offshore marks.",
)

ALL_CHUNKS = [TIDE_CHUNK, BASS_CHUNK, SAFETY_CHUNK, HARBOUR_CHUNK]


# ─── Tiny 4-dim embeddings ────────────────────────────────────────────────────
# [1,0,0,0] ≈ tides   [0,1,0,0] ≈ bass   [0,0,1,0] ≈ safety   [0,0,0,1] ≈ harbour

def _unit(v):
    a = np.array(v, dtype=np.float32)
    return (a / np.linalg.norm(a)).tolist()


TIDE_VEC    = _unit([1.0, 0.1, 0.0, 0.0])
BASS_VEC    = _unit([0.1, 1.0, 0.0, 0.0])
SAFETY_VEC  = _unit([0.0, 0.0, 1.0, 0.1])
HARBOUR_VEC = _unit([0.0, 0.0, 0.1, 1.0])

EMBEDDED_CHUNKS = [
    _make_chunk("tide_001",    "tide_basics",      "Spring Tides",       TIDE_CHUNK.text,    TIDE_VEC),
    _make_chunk("species_001", "species_activity", "Bass Activity",      BASS_CHUNK.text,    BASS_VEC),
    _make_chunk("safety_001",  "safety_notes",     "Tidal Cut-offs",     SAFETY_CHUNK.text,  SAFETY_VEC),
    _make_chunk("harbour_001", "harbour_selection","Choosing a Harbour", HARBOUR_CHUNK.text, HARBOUR_VEC),
]


def _mock_embedder(vec):
    mock = MagicMock()
    mock.embed.return_value = np.array([vec], dtype=np.float32)
    return mock


# ─── tokenise ─────────────────────────────────────────────────────────────────

class TestTokenise:

    def test_lowercases(self):
        assert "bass" in tokenise("Bass")

    def test_removes_stop_words(self):
        tokens = tokenise("the fish and the sea")
        assert "the" not in tokens and "and" not in tokens

    def test_removes_punctuation(self):
        tokens = tokenise("flood tide, strong current.")
        assert "flood" in tokens and "tide," not in tokens

    def test_removes_single_char_tokens(self):
        assert "i" not in tokenise("I fish every day")

    def test_empty_string_returns_empty(self):
        assert tokenise("") == []

    def test_stop_word_only_returns_empty(self):
        assert tokenise("the and or") == []


# ─── _keyword_score ───────────────────────────────────────────────────────────

class TestKeywordScore:

    def test_zero_for_no_matching_terms(self):
        assert _keyword_score(["narwhal", "unicorn"], BASS_CHUNK) == 0.0

    def test_positive_for_matching_term(self):
        assert _keyword_score(["bass"], BASS_CHUNK) > 0.0

    def test_higher_score_for_more_matches(self):
        assert _keyword_score(["bass", "flood"], BASS_CHUNK) > _keyword_score(["bass"], BASS_CHUNK)

    def test_phrase_bonus_applied(self):
        phrase = _keyword_score(["spring", "flood", "tides"], TIDE_CHUNK)
        single = _keyword_score(["spring"], TIDE_CHUNK)
        assert phrase > single

    def test_empty_query_returns_zero(self):
        assert _keyword_score([], BASS_CHUNK) == 0.0

    def test_score_rewards_relevant_topic(self):
        on_topic  = _keyword_score(["bass", "flood", "tide"], BASS_CHUNK)
        off_topic = _keyword_score(["bass", "flood", "tide"], HARBOUR_CHUNK)
        assert on_topic > off_topic


# ─── KeywordRetriever ─────────────────────────────────────────────────────────

class TestKeywordRetriever:

    def setup_method(self):
        self.r = KeywordRetriever(ALL_CHUNKS)

    def test_implements_base_retriever(self):
        assert isinstance(self.r, BaseRetriever)

    def test_retrieval_method_label(self):
        assert self.r.retrieval_method == "bm25"

    def test_returns_chunks(self):
        assert all(isinstance(c, Chunk) for c in self.r.retrieve("bass"))

    def test_top_k_respected(self):
        assert len(self.r.retrieve("fishing tide bass harbour", top_k=2)) <= 2

    def test_empty_query_returns_empty(self):
        assert self.r.retrieve("") == []

    def test_zero_score_chunks_excluded(self):
        assert self.r.retrieve("narwhal") == []

    def test_bass_query_returns_bass_chunk_first(self):
        assert self.r.retrieve("bass flood season", top_k=3)[0].chunk_id == "species_001"

    def test_tide_query_returns_tide_topic(self):
        topics = [c.topic for c in self.r.retrieve("spring tide current", top_k=3)]
        assert "tide_basics" in topics

    def test_retrieve_text_returns_strings(self):
        assert all(isinstance(t, str) for t in self.r.retrieve_text("bass", top_k=2))

    # ── Metadata filtering ───────────────────────────────────────────────────

    def test_filter_restricts_to_topic(self):
        results = self.r.retrieve("tide bass harbour safety", top_k=4,
                                  filter_topic="species_activity")
        assert all(c.topic == "species_activity" for c in results)

    def test_filter_unknown_topic_returns_empty(self):
        results = self.r.retrieve("fishing", top_k=3, filter_topic="nonexistent_topic")
        assert results == []

    def test_filter_none_searches_all(self):
        topics = {c.topic for c in self.r.retrieve("fishing tide bass", top_k=4, filter_topic=None)}
        assert len(topics) > 1  # results from multiple topics


# ─── FaissRetriever ───────────────────────────────────────────────────────────

class TestFaissRetriever:

    def setup_method(self):
        self.r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))

    def test_implements_base_retriever(self):
        assert isinstance(self.r, BaseRetriever)

    def test_retrieval_method_label(self):
        assert self.r.retrieval_method == "faiss"

    def test_returns_chunks(self):
        assert all(isinstance(c, Chunk) for c in self.r.retrieve("bass fishing"))

    def test_top_k_respected(self):
        assert len(self.r.retrieve("fishing", top_k=2)) <= 2

    def test_bass_query_returns_bass_chunk_first(self):
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        assert r.retrieve("bass season flood", top_k=3)[0].chunk_id == "species_001"

    def test_tide_query_returns_tide_chunk_first(self):
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(TIDE_VEC))
        assert r.retrieve("spring tide current", top_k=3)[0].chunk_id == "tide_001"

    def test_safety_query_returns_safety_chunk_first(self):
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(SAFETY_VEC))
        assert r.retrieve("tidal cut-off rocky path", top_k=3)[0].chunk_id == "safety_001"

    def test_retrieve_text_returns_strings(self):
        assert all(isinstance(t, str) for t in self.r.retrieve_text("bass", top_k=2))

    def test_empty_query_falls_back_gracefully(self):
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder([0.0, 0.0, 0.0, 0.0]))
        assert isinstance(r.retrieve("the and or"), list)

    # ── Metadata filtering ───────────────────────────────────────────────────

    def test_filter_restricts_to_topic(self):
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        results = r.retrieve("bass tide harbour safety", top_k=4,
                              filter_topic="species_activity")
        assert all(c.topic == "species_activity" for c in results)

    def test_filter_unknown_topic_falls_back_to_full_corpus(self):
        # When filter matches nothing, the implementation falls back to full corpus.
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        results = r.retrieve("bass", top_k=2, filter_topic="nonexistent_topic")
        assert len(results) > 0  # graceful fallback, not an empty list

    def test_filter_uses_numpy_path_not_faiss(self):
        # With filter, the query hits the numpy path.
        # Verifiable by confirming results honour the topic constraint.
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(TIDE_VEC))
        results = r.retrieve("spring tide", top_k=3, filter_topic="tide_basics")
        assert all(c.topic == "tide_basics" for c in results)

    def test_filter_none_uses_faiss_index(self):
        r = FaissRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        results = r.retrieve("bass", top_k=2, filter_topic=None)
        assert len(results) <= 2


# ─── HybridRetriever (RRF) ────────────────────────────────────────────────────

class TestHybridRetriever:

    def setup_method(self):
        self.r = HybridRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))

    def test_implements_base_retriever(self):
        assert isinstance(self.r, BaseRetriever)

    def test_retrieval_method_label(self):
        assert self.r.retrieval_method == "hybrid-rrf"

    def test_returns_chunks(self):
        assert all(isinstance(c, Chunk) for c in self.r.retrieve("bass fishing"))

    def test_top_k_respected(self):
        assert len(self.r.retrieve("fishing tide bass harbour", top_k=2)) <= 2

    def test_bass_query_returns_bass_chunk_first(self):
        # FAISS signal is BASS_VEC; keyword signal also favours bass chunk.
        # RRF should confidently rank bass_001 first.
        r = HybridRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        results = r.retrieve("bass season flood", top_k=3)
        assert results[0].chunk_id == "species_001"

    def test_tide_query_returns_tide_chunk_first(self):
        r = HybridRetriever(EMBEDDED_CHUNKS, _mock_embedder(TIDE_VEC))
        results = r.retrieve("spring tide current moon", top_k=3)
        assert results[0].chunk_id == "tide_001"

    def test_rrf_document_appearing_in_both_lists_scores_higher(self):
        # The bass chunk has both keyword matches AND a close FAISS vector.
        # It should appear in the top result because it contributes to both lists.
        r = HybridRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        results = r.retrieve("bass flood tide", top_k=4)
        ids = [c.chunk_id for c in results]
        assert "species_001" in ids
        assert ids.index("species_001") == 0

    def test_retrieve_text_returns_strings(self):
        assert all(isinstance(t, str) for t in self.r.retrieve_text("bass", top_k=2))

    def test_no_duplicates_in_results(self):
        results = self.r.retrieve("fishing", top_k=4)
        ids = [c.chunk_id for c in results]
        assert len(ids) == len(set(ids))

    # ── Metadata filtering via hybrid ────────────────────────────────────────

    def test_filter_restricts_both_signals(self):
        r = HybridRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        results = r.retrieve("bass tide harbour safety", top_k=4,
                              filter_topic="species_activity")
        assert all(c.topic == "species_activity" for c in results)

    def test_filter_none_returns_cross_topic_results(self):
        r = HybridRetriever(EMBEDDED_CHUNKS, _mock_embedder(BASS_VEC))
        topics = {c.topic for c in r.retrieve("bass tide harbour", top_k=4)}
        assert len(topics) > 1


# ─── Chunk serialisation ──────────────────────────────────────────────────────

class TestChunkSerialisation:

    def test_round_trip_no_embedding(self):
        restored = Chunk.from_dict(BASS_CHUNK.to_dict())
        assert restored.chunk_id == BASS_CHUNK.chunk_id
        assert restored.embedding is None

    def test_round_trip_with_embedding(self):
        chunk = _make_chunk("x", "t", "h", "some text", embedding=[0.1, 0.2])
        assert Chunk.from_dict(chunk.to_dict()).embedding == [0.1, 0.2]


# ─── Live index (integration) ─────────────────────────────────────────────────

class TestLiveIndex:
    """Smoke-tests against the built index.json with real embeddings."""

    def test_retriever_loads(self):
        assert get_retriever() is not None

    def test_uses_hybrid_when_embeddings_present(self):
        assert isinstance(get_retriever(), HybridRetriever)

    def test_retrieval_method_is_hybrid_rrf(self):
        assert get_retriever().retrieval_method == "hybrid-rrf"

    def test_singleton(self):
        assert get_retriever() is get_retriever()

    def test_chunk_count_reasonable(self):
        assert len(get_retriever()._chunks) > 20

    def test_bass_query_semantic_relevance(self):
        results = get_retriever().retrieve("Bass feeding flood tide season", top_k=3)
        assert len(results) > 0
        assert "bass" in " ".join(c.text for c in results).lower()

    def test_safety_query_semantic_relevance(self):
        results = get_retriever().retrieve("tidal cut-off danger rocky shore", top_k=3)
        combined = " ".join(c.text for c in results).lower()
        assert any(w in combined for w in ["tide", "water", "safety", "coastguard", "exit"])

    def test_cod_winter_query(self):
        results = get_retriever().retrieve("Cod winter cold water pier", top_k=3)
        assert "cod" in " ".join(c.text for c in results).lower()

    def test_filter_species_activity(self):
        results = get_retriever().retrieve(
            "Bass feeding season", top_k=3, filter_topic="species_activity"
        )
        assert all(c.topic == "species_activity" for c in results)

    def test_filter_tide_basics(self):
        results = get_retriever().retrieve(
            "spring flood neap tides", top_k=3, filter_topic="tide_basics"
        )
        assert all(c.topic == "tide_basics" for c in results)

    def test_two_stage_species_then_tidal(self):
        """Mirrors the two-stage retrieval the recommend router uses."""
        r = get_retriever()
        species_notes = r.retrieve_text(
            "Bass feeding season habitat", top_k=2, filter_topic="species_activity"
        )
        tidal_notes = r.retrieve_text(
            "Flood spring tide Falmouth", top_k=1
        )
        combined = list(dict.fromkeys(species_notes + tidal_notes))
        assert len(combined) >= 1
        assert all(isinstance(n, str) for n in combined)
