# tests/test_retrieval.py — Unit tests for the corpus retrieval pipeline.
#
# Tests cover:
#   - tokenisation (stop word removal, normalisation)
#   - chunk loading from the built index
#   - keyword scoring (term matching, phrase bonus, empty query)
#   - KeywordRetriever.retrieve() top-k ordering and zero-score exclusion
#   - retrieve_text() returns strings
#   - query relevance: species and tide queries return topic-relevant chunks

from app.retrieval.retriever import (
    Chunk,
    KeywordRetriever,
    _keyword_score,
    get_retriever,
    tokenise,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_chunk(chunk_id: str, topic: str, heading: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        topic=topic,
        heading=heading,
        text=text,
        word_count=len(text.split()),
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


# ─── tokenise ─────────────────────────────────────────────────────────────────

class TestTokenise:

    def test_lowercases(self):
        assert "bass" in tokenise("Bass")

    def test_removes_stop_words(self):
        tokens = tokenise("the fish and the sea")
        assert "the" not in tokens
        assert "and" not in tokens

    def test_removes_punctuation(self):
        tokens = tokenise("flood tide, strong current.")
        assert "flood" in tokens
        assert "tide" in tokens
        # commas and dots stripped
        assert "tide," not in tokens

    def test_removes_single_char_tokens(self):
        assert "i" not in tokenise("I fish every day")

    def test_empty_string_returns_empty(self):
        assert tokenise("") == []

    def test_stop_word_only_returns_empty(self):
        assert tokenise("the and or") == []


# ─── _keyword_score ───────────────────────────────────────────────────────────

class TestKeywordScore:

    def test_zero_for_no_matching_terms(self):
        score = _keyword_score(["narwhal", "unicorn"], BASS_CHUNK)
        assert score == 0.0

    def test_positive_for_matching_term(self):
        score = _keyword_score(["bass"], BASS_CHUNK)
        assert score > 0.0

    def test_higher_score_for_more_matches(self):
        one_match  = _keyword_score(["bass"], BASS_CHUNK)
        two_match  = _keyword_score(["bass", "flood"], BASS_CHUNK)
        assert two_match > one_match

    def test_phrase_bonus_applied(self):
        # "flood tides" appears verbatim in TIDE_CHUNK after stop-word removal
        phrase_score = _keyword_score(["spring", "flood", "tides"], TIDE_CHUNK)
        single_score = _keyword_score(["spring"], TIDE_CHUNK)
        assert phrase_score > single_score

    def test_empty_query_returns_zero(self):
        assert _keyword_score([], BASS_CHUNK) == 0.0

    def test_score_rewards_relevant_topic_chunk(self):
        bass_score = _keyword_score(["bass", "flood", "tide"], BASS_CHUNK)
        harbour_score = _keyword_score(["bass", "flood", "tide"], HARBOUR_CHUNK)
        assert bass_score > harbour_score


# ─── KeywordRetriever ─────────────────────────────────────────────────────────

class TestKeywordRetriever:

    def setup_method(self):
        self.retriever = KeywordRetriever(ALL_CHUNKS)

    def test_returns_list_of_chunks(self):
        result = self.retriever.retrieve("bass fishing")
        assert isinstance(result, list)
        assert all(isinstance(c, Chunk) for c in result)

    def test_top_k_limits_results(self):
        result = self.retriever.retrieve("fishing tide bass harbour", top_k=2)
        assert len(result) <= 2

    def test_empty_query_returns_empty(self):
        assert self.retriever.retrieve("") == []

    def test_zero_score_chunks_excluded(self):
        # "narwhal" appears in none of the chunks
        result = self.retriever.retrieve("narwhal")
        assert result == []

    def test_bass_query_returns_bass_chunk_first(self):
        results = self.retriever.retrieve("bass flood season", top_k=3)
        assert results[0].chunk_id == "species_001"

    def test_tide_query_returns_tide_chunk(self):
        results = self.retriever.retrieve("spring tide current high water", top_k=3)
        topics = [c.topic for c in results]
        assert "tide_basics" in topics

    def test_safety_query_returns_safety_chunk(self):
        results = self.retriever.retrieve("tidal cut-off rocky path flood", top_k=3)
        topics = [c.topic for c in results]
        assert "safety_notes" in topics

    def test_retrieve_text_returns_strings(self):
        texts = self.retriever.retrieve_text("bass fishing", top_k=2)
        assert all(isinstance(t, str) for t in texts)

    def test_retrieve_text_non_empty_for_valid_query(self):
        texts = self.retriever.retrieve_text("spring tide Bass flood")
        assert len(texts) > 0


# ─── Chunk serialisation ──────────────────────────────────────────────────────

class TestChunkSerialisation:

    def test_round_trip(self):
        d = BASS_CHUNK.to_dict()
        restored = Chunk.from_dict(d)
        assert restored.chunk_id == BASS_CHUNK.chunk_id
        assert restored.text == BASS_CHUNK.text
        assert restored.embedding is None

    def test_embedding_field_preserved(self):
        chunk_with_embed = _make_chunk("x", "t", "h", "some text")
        chunk_with_embed.embedding = [0.1, 0.2, 0.3]
        d = chunk_with_embed.to_dict()
        restored = Chunk.from_dict(d)
        assert restored.embedding == [0.1, 0.2, 0.3]


# ─── Live index (integration) ─────────────────────────────────────────────────

class TestLiveIndex:
    """Smoke-tests against the real built index.json."""

    def test_retriever_loads_without_error(self):
        r = get_retriever()
        assert r is not None

    def test_index_has_reasonable_chunk_count(self):
        r = get_retriever()
        assert len(r._chunks) > 20

    def test_bass_query_returns_species_content(self):
        results = get_retriever().retrieve("Bass feeding flood tide season", top_k=3)
        assert len(results) > 0
        combined = " ".join(c.text for c in results).lower()
        assert "bass" in combined

    def test_safety_query_returns_safety_content(self):
        results = get_retriever().retrieve("tidal cut-off safety", top_k=3)
        assert len(results) > 0
        combined = " ".join(c.text for c in results).lower()
        # Should mention tide, water, or safety concepts
        assert any(w in combined for w in ["tide", "water", "safety", "coastguard"])

    def test_retriever_is_singleton(self):
        assert get_retriever() is get_retriever()
