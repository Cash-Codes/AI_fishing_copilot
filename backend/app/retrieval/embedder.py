# retrieval/embedder.py — Local embedding generation via fastembed.
#
# fastembed uses ONNX Runtime under the hood — no PyTorch, no GPU, no API key.
# The model weights (~22 MB) are downloaded on first use and cached in
# ~/.cache/fastembed.  Subsequent process starts are instant.
#
# Model choice: all-MiniLM-L6-v2
#   - 384 dimensions — compact but high-quality for semantic search
#   - ~22 MB download — negligible compared to torch-based alternatives
#   - Strong benchmark performance on sentence similarity tasks
#   - Identical to the model commonly used with sentence-transformers
#
# Swapping models later:
#   Change MODEL_NAME to any fastembed-supported model (e.g. BAAI/bge-small-en)
#   and re-run  python scripts/build_index.py --embed  to rebuild the index.
#   The FAISS dimension is stored in the index so callers don't need to
#   hard-code it.

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSIONS = 384  # documented output size for this model


class Embedder:
    """Generates normalised sentence embeddings using a local ONNX model.

    Embeddings are L2-normalised (unit vectors) so that inner product equals
    cosine similarity.  FAISS IndexFlatIP is then equivalent to cosine search.

    The model is loaded lazily on first call to `embed()` and reused for the
    lifetime of the instance.
    """

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = None   # loaded on first use

    def _load(self) -> None:
        if self._model is None:
            from fastembed import TextEmbedding
            logger.info("Loading embedding model %s (first call only)", self._model_name)
            self._model = TextEmbedding(model_name=self._model_name)

    def embed(self, texts: List[str]) -> np.ndarray:
        """Return an (N, D) float32 array of L2-normalised embeddings.

        Args:
            texts: List of strings to embed.  Empty strings are replaced with
                   a single space to avoid model errors.

        Returns:
            NumPy array of shape (len(texts), DIMENSIONS), dtype float32.
            Vectors are unit-normalised so cosine similarity == inner product.
        """
        self._load()
        # fastembed returns a generator of numpy arrays, one per text
        safe_texts = [t if t.strip() else " " for t in texts]
        raw = np.array(list(self._model.embed(safe_texts)), dtype=np.float32)

        # L2 normalise: divide each row by its Euclidean norm.
        # After this step, inner_product(a, b) == cosine_similarity(a, b).
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)   # guard against zero vectors
        return raw / norms
