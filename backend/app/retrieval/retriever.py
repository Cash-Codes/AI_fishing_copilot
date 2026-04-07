# retrieval/retriever.py — Keyword-based retrieval over the fishing corpus.
#
# Architecture is designed so that the keyword scorer can be replaced with an
# embedding-based scorer (e.g. sentence-transformers, OpenAI text-embedding-3)
# without changing the Chunk model, the index format, or any calling code.
#
# Upgrade path to embeddings:
#   1. Add an `embedding: Optional[List[float]]` field to Chunk (already
#      reserved in the JSON schema).
#   2. Replace _keyword_score() with _cosine_score() that reads chunk.embedding.
#   3. Re-run `scripts/build_index.py --embed` to populate embeddings.
#   4. Swap `KeywordRetriever` for `EmbeddingRetriever` — same interface.
#
# The index is read once at import time and cached in a module-level variable.
# Re-loading requires a server restart, which is acceptable for an MVP where
# the corpus changes rarely.  A more sophisticated system would watch the file
# for changes and reload automatically.

import json
import logging
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).parent / "index.json"

# ── Stop words ────────────────────────────────────────────────────────────────
# Common words that carry little meaning and would flood scores if counted.
# Deliberately minimal — this is not an NLP library.

_STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "that", "this", "these",
    "those", "it", "its", "as", "so", "if", "not", "no", "than", "then",
    "their", "they", "them", "there", "when", "where", "which", "who",
    "what", "how", "also", "up", "out", "into", "over", "after", "before",
    "very", "more", "most", "some", "any", "each", "both", "all", "other",
}


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A retrievable piece of corpus text with metadata.

    The `embedding` field is reserved for a future vector-based upgrade.
    It is stored as None in the current keyword-only index so adding it later
    is backward-compatible: existing chunks simply get the field populated.
    """

    chunk_id: str               # e.g. "tide_basics_003"
    topic: str                  # filename stem: "tide_basics", "safety_notes", …
    heading: str                # nearest ## heading above this chunk
    text: str                   # the raw chunk text shown to the user
    word_count: int
    embedding: Optional[List[float]] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Serialise to a plain dict for JSON storage."""
        return {
            "chunk_id":  self.chunk_id,
            "topic":     self.topic,
            "heading":   self.heading,
            "text":      self.text,
            "word_count": self.word_count,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        return cls(
            chunk_id=data["chunk_id"],
            topic=data["topic"],
            heading=data["heading"],
            text=data["text"],
            word_count=data["word_count"],
            embedding=data.get("embedding"),
        )


# ── Tokenisation ──────────────────────────────────────────────────────────────

def tokenise(text: str) -> List[str]:
    """Lower-case, strip punctuation, remove stop words."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


# ── Scorer — swap this function to upgrade to embeddings ─────────────────────

def _keyword_score(query_tokens: List[str], chunk: Chunk) -> float:
    """BM25-lite keyword score.

    This is the function to replace when moving to embeddings:

        def _embedding_score(query_embedding: List[float], chunk: Chunk) -> float:
            dot = sum(a * b for a, b in zip(query_embedding, chunk.embedding))
            return dot  # vectors are unit-normalised, so dot == cosine similarity

    Scoring:
        - Count each query term's occurrences in the chunk.
        - Normalise by sqrt(word_count) to avoid very long chunks dominating.
        - Boost by 1.5x if the exact query phrase (≥2 words) appears verbatim.
    """
    if not query_tokens:
        return 0.0

    chunk_lower = chunk.text.lower()
    chunk_tokens = tokenise(chunk.text)

    # Term-frequency component
    tf_score = sum(chunk_tokens.count(t) for t in set(query_tokens))
    normalised = tf_score / max(1, math.sqrt(chunk.word_count))

    # Phrase bonus: reward verbatim multi-word matches
    query_phrase = " ".join(query_tokens)
    phrase_bonus = 1.5 if len(query_tokens) >= 2 and query_phrase in chunk_lower else 1.0

    return normalised * phrase_bonus


# ── Retriever ─────────────────────────────────────────────────────────────────

class KeywordRetriever:
    """Retrieve the top-k most relevant corpus chunks for a text query.

    The retriever is stateless after construction — thread-safe and
    suitable for use as a module-level singleton.
    """

    def __init__(self, chunks: List[Chunk]) -> None:
        self._chunks = chunks
        logger.info("KeywordRetriever ready with %d chunks", len(chunks))

    def retrieve(self, query: str, top_k: int = 3) -> List[Chunk]:
        """Return up to `top_k` chunks most relevant to `query`.

        Scores every chunk and returns the highest-scoring ones.
        Chunks with a score of zero are excluded even if fewer than top_k
        results remain — avoids returning irrelevant content.
        """
        query_tokens = tokenise(query)
        if not query_tokens:
            return []

        scored = [
            (chunk, _keyword_score(query_tokens, chunk))
            for chunk in self._chunks
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [chunk for chunk, score in scored[:top_k] if score > 0.0]

    def retrieve_text(self, query: str, top_k: int = 3) -> List[str]:
        """Convenience wrapper: returns chunk text strings directly."""
        return [chunk.text for chunk in self.retrieve(query, top_k=top_k)]


# ── Index loading ─────────────────────────────────────────────────────────────

def _load_index() -> List[Chunk]:
    """Read chunks from index.json.  Raises if the file is missing."""
    if not _INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Retrieval index not found at {_INDEX_PATH}. "
            "Run `python scripts/build_index.py` to build it."
        )
    data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    chunks = [Chunk.from_dict(c) for c in data["chunks"]]
    logger.info(
        "Loaded retrieval index v%s (%d chunks, built %s)",
        data.get("version", "?"),
        len(chunks),
        data.get("built_at", "unknown"),
    )
    return chunks


@lru_cache(maxsize=None)
def get_retriever() -> KeywordRetriever:
    """Return the singleton retriever, loading the index on first call.

    lru_cache ensures the index is read from disk exactly once per process
    lifetime, regardless of how many requests arrive.
    """
    return KeywordRetriever(_load_index())
