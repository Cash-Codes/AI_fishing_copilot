# retrieval/retriever.py — Corpus retrieval: keyword fallback + FAISS semantic search.
#
# Two concrete retrievers share the same interface (BaseRetriever):
#
#   KeywordRetriever  — BM25-lite scorer, no dependencies beyond stdlib.
#                       Always available; used when embeddings are absent.
#
#   FaissRetriever    — Cosine similarity via FAISS IndexFlatIP.
#                       Used when the index contains embedding vectors.
#                       Falls back to KeywordRetriever if faiss/fastembed
#                       are not importable (e.g. stripped-down CI image).
#
# Retriever selection is automatic: get_retriever() inspects the index to
# decide which implementation to return.  Callers never need to know which
# one they got.
#
# Embedding-upgrade checklist (already done):
#   [x] Chunk.embedding field in data model + JSON schema
#   [x] _keyword_score() isolated — can be replaced without touching callers
#   [x] FaissRetriever uses same BaseRetriever interface as KeywordRetriever
#   [ ] Run: python scripts/build_index.py --embed  to populate embeddings

import json
import logging
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).parent / "index.json"

# ── Stop words ────────────────────────────────────────────────────────────────

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
    """A retrievable piece of corpus text.

    The embedding field holds a pre-computed unit-normalised vector generated
    by scripts/build_index.py --embed.  It is None in keyword-only indexes.
    """

    chunk_id: str
    topic: str
    heading: str
    text: str
    word_count: int
    embedding: Optional[List[float]] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "chunk_id":   self.chunk_id,
            "topic":      self.topic,
            "heading":    self.heading,
            "text":       self.text,
            "word_count": self.word_count,
            "embedding":  self.embedding,
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


# ── Shared interface ──────────────────────────────────────────────────────────

class BaseRetriever(ABC):
    """Common interface for all retriever implementations.

    Any class that satisfies this interface can be returned by get_retriever()
    and used by the recommendation endpoint without modification.
    """

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 3) -> List[Chunk]:
        """Return up to top_k chunks most relevant to the query."""

    def retrieve_text(self, query: str, top_k: int = 3) -> List[str]:
        """Convenience wrapper: returns the text of each chunk."""
        return [chunk.text for chunk in self.retrieve(query, top_k=top_k)]


# ── Tokenisation (shared by both retrievers) ──────────────────────────────────

def tokenise(text: str) -> List[str]:
    """Lower-case, strip punctuation, remove stop words."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


# ── Keyword retriever ─────────────────────────────────────────────────────────

def _keyword_score(query_tokens: List[str], chunk: Chunk) -> float:
    """BM25-lite keyword score.

    Swap this function (and nothing else) to use a different scoring formula.
    The equivalent embedding scorer would be:

        def _cosine_score(query_vec: np.ndarray, chunk: Chunk) -> float:
            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            return float(np.dot(query_vec, chunk_vec))
            # Vectors are unit-normalised, so dot == cosine similarity.
    """
    if not query_tokens:
        return 0.0

    chunk_lower = chunk.text.lower()
    chunk_tokens = tokenise(chunk.text)

    tf_score = sum(chunk_tokens.count(t) for t in set(query_tokens))
    normalised = tf_score / max(1, math.sqrt(chunk.word_count))

    query_phrase = " ".join(query_tokens)
    phrase_bonus = 1.5 if len(query_tokens) >= 2 and query_phrase in chunk_lower else 1.0

    return normalised * phrase_bonus


class KeywordRetriever(BaseRetriever):
    """BM25-lite retriever — no external dependencies."""

    def __init__(self, chunks: List[Chunk]) -> None:
        self._chunks = chunks
        logger.info("KeywordRetriever ready with %d chunks", len(chunks))

    def retrieve(self, query: str, top_k: int = 3) -> List[Chunk]:
        query_tokens = tokenise(query)
        if not query_tokens:
            return []
        scored = [
            (chunk, _keyword_score(query_tokens, chunk))
            for chunk in self._chunks
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [chunk for chunk, score in scored[:top_k] if score > 0.0]


# ── FAISS retriever ───────────────────────────────────────────────────────────

class FaissRetriever(BaseRetriever):
    """Cosine-similarity retriever using an in-memory FAISS IndexFlatIP.

    Embeddings are read from Chunk.embedding (pre-computed unit vectors).
    Query embeddings are generated on the fly by the injected Embedder.

    Why IndexFlatIP (inner product)?
      Chunks and query vectors are L2-normalised so inner product == cosine
      similarity.  IndexFlatIP is exact (no approximation), appropriate for
      a corpus of < 10 000 chunks.  For larger corpora, swap to IndexIVFFlat
      or IndexHNSWFlat for approximate-but-faster search.
    """

    def __init__(self, chunks: List[Chunk], embedder: object) -> None:
        import faiss
        import numpy as np

        embeddings = np.array(
            [c.embedding for c in chunks], dtype=np.float32
        )
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)
        self._chunks = chunks
        self._embedder = embedder
        logger.info(
            "FaissRetriever ready | %d chunks | dim=%d", len(chunks), dim
        )

    def retrieve(self, query: str, top_k: int = 3) -> List[Chunk]:
        query_vec = self._embedder.embed([query])   # shape (1, D)
        k = min(top_k, len(self._chunks))
        scores, indices = self._index.search(query_vec, k)

        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx >= 0 and score > 0.0:
                results.append(self._chunks[idx])
        return results


# ── Index loading ─────────────────────────────────────────────────────────────

def _load_index() -> List[Chunk]:
    if not _INDEX_PATH.exists():
        raise FileNotFoundError(
            f"Retrieval index not found at {_INDEX_PATH}. "
            "Run  python scripts/build_index.py  to build it."
        )
    data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    chunks = [Chunk.from_dict(c) for c in data["chunks"]]
    has_embeddings = any(c.embedding is not None for c in chunks)
    logger.info(
        "Loaded index v%s | %d chunks | embeddings=%s | built %s",
        data.get("version", "?"),
        len(chunks),
        has_embeddings,
        data.get("built_at", "unknown"),
    )
    return chunks


@lru_cache(maxsize=None)
def get_retriever() -> BaseRetriever:
    """Return the best available retriever for the current index.

    Decision logic:
      1. Load index.json.
      2. If any chunk has a non-None embedding → try FaissRetriever.
         - If faiss / fastembed are importable → return FaissRetriever.
         - If import fails → warn and fall through.
      3. Return KeywordRetriever.

    lru_cache ensures the index is read and the FAISS index is built
    exactly once per process — safe for concurrent requests.
    """
    chunks = _load_index()
    has_embeddings = any(c.embedding is not None for c in chunks)

    if has_embeddings:
        try:
            import faiss  # noqa: F401  — check importable before constructing
            from app.retrieval.embedder import Embedder
            embedder = Embedder()
            return FaissRetriever(chunks, embedder)
        except ImportError as exc:
            logger.warning(
                "faiss/fastembed not available (%s) — using keyword retrieval",
                exc,
            )

    logger.info("Using KeywordRetriever (no embeddings in index)")
    return KeywordRetriever(chunks)
