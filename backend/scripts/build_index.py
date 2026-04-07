#!/usr/bin/env python3
# scripts/build_index.py — Build or refresh the retrieval index from the corpus.
#
# Usage:
#   python scripts/build_index.py            # keyword-only index (no model needed)
#   python scripts/build_index.py --embed    # include embeddings for FAISS retrieval
#   python scripts/build_index.py --dry-run  # print chunk stats without writing
#
# The --embed flag downloads the embedding model on first run (~22 MB, cached).
# Re-running with --embed is safe and overwrites the existing index.
#
# Call this script whenever corpus files are edited:
#   cd backend && python scripts/build_index.py --embed

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────

_SCRIPT_DIR  = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_CORPUS_DIR  = _BACKEND_DIR / "app" / "corpus"
_INDEX_PATH  = _BACKEND_DIR / "app" / "retrieval" / "index.json"

sys.path.insert(0, str(_BACKEND_DIR))

# ── Chunking configuration ────────────────────────────────────────────────────

MIN_WORDS     = 30
MAX_WORDS     = 180
INDEX_VERSION = "2.0"   # bumped when embedding field added


# ── Chunker (unchanged from v1) ───────────────────────────────────────────────

def _split_sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _chunk_paragraphs(paragraphs: list, max_words: int, min_words: int) -> list:
    chunks = []
    buffer: list = []

    def flush() -> None:
        text = " ".join(buffer).strip()
        if text:
            chunks.append(text)
        buffer.clear()

    for para in paragraphs:
        words = para.split()
        if len(words) > max_words:
            if buffer:
                flush()
            sentences = _split_sentences(para)
            sentence_buf: list = []
            for sentence in sentences:
                sentence_buf.append(sentence)
                if len(" ".join(sentence_buf).split()) >= min_words:
                    chunks.append(" ".join(sentence_buf).strip())
                    sentence_buf = []
            if sentence_buf:
                chunks.append(" ".join(sentence_buf).strip())
        else:
            buffer.extend(words)
            if len(buffer) >= min_words:
                flush()

    if buffer:
        flush()
    return [c for c in chunks if c]


def chunk_markdown(filepath: Path) -> list:
    """Parse one markdown file into annotated chunk dicts."""
    text = filepath.read_text(encoding="utf-8")
    topic = filepath.stem
    chunks = []
    current_heading = topic.replace("_", " ").title()

    lines = text.splitlines()
    paragraphs: list = []
    para_lines: list = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if para_lines:
                paragraphs.append((" ".join(para_lines), current_heading))
                para_lines = []
            current_heading = stripped.lstrip("#").strip()
        elif stripped == "":
            if para_lines:
                paragraphs.append((" ".join(para_lines), current_heading))
                para_lines = []
        else:
            clean = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", stripped)
            clean = re.sub(r"^[-*+]\s+", "", clean)
            if clean:
                para_lines.append(clean)

    if para_lines:
        paragraphs.append((" ".join(para_lines), current_heading))

    heading_groups: dict = {}
    heading_order: list = []
    for para_text, heading in paragraphs:
        if heading not in heading_groups:
            heading_groups[heading] = []
            heading_order.append(heading)
        heading_groups[heading].append(para_text)

    chunk_counter = 1
    for heading in heading_order:
        for chunk_text in _chunk_paragraphs(
            heading_groups[heading], max_words=MAX_WORDS, min_words=MIN_WORDS
        ):
            wc = len(chunk_text.split())
            if wc < 10:
                continue
            chunks.append({
                "chunk_id":   f"{topic}_{chunk_counter:03d}",
                "topic":      topic,
                "heading":    heading,
                "text":       chunk_text,
                "word_count": wc,
                "embedding":  None,
            })
            chunk_counter += 1

    return chunks


# ── Embedding step ────────────────────────────────────────────────────────────

def _embed_chunks(chunks: list) -> list:
    """Add embedding vectors to all chunks in-place and return them.

    Uses the Embedder from app.retrieval.embedder (fastembed / all-MiniLM-L6-v2).
    Vectors are L2-normalised so cosine similarity == inner product.
    """
    from app.retrieval.embedder import Embedder

    embedder = Embedder()
    texts = [c["text"] for c in chunks]

    print(f"\nEmbedding {len(texts)} chunks with all-MiniLM-L6-v2…")
    print("(model downloads ~22 MB on first run, then cached in ~/.cache/fastembed)\n")

    import numpy as np
    vectors: np.ndarray = embedder.embed(texts)   # shape (N, 384)

    for chunk, vec in zip(chunks, vectors):
        chunk["embedding"] = vec.tolist()

    print(f"Embeddings generated | dim={vectors.shape[1]}")
    return chunks


# ── Main ──────────────────────────────────────────────────────────────────────

def build(embed: bool = False, dry_run: bool = False) -> None:
    corpus_files = sorted(_CORPUS_DIR.glob("*.md"))
    if not corpus_files:
        print(f"ERROR: No .md files found in {_CORPUS_DIR}", file=sys.stderr)
        sys.exit(1)

    all_chunks: list = []
    for filepath in corpus_files:
        file_chunks = chunk_markdown(filepath)
        all_chunks.extend(file_chunks)
        print(f"  {filepath.name:<35} {len(file_chunks):>3} chunks")

    print(f"\nTotal chunks: {len(all_chunks)}")

    if dry_run:
        print("\n── Dry run — first 3 chunks ──────────────────────────────────")
        for chunk in all_chunks[:3]:
            print(f"\n[{chunk['chunk_id']}] {chunk['heading']}")
            print(f"  words={chunk['word_count']}")
            print(f"  {chunk['text'][:120]}…")
        return

    if embed:
        all_chunks = _embed_chunks(all_chunks)

    index = {
        "version":    INDEX_VERSION,
        "built_at":   datetime.now(tz=timezone.utc).isoformat(),
        "has_embeddings": embed,
        "chunks":     all_chunks,
    }

    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    mode = "with embeddings" if embed else "keyword-only"
    print(f"\nIndex written ({mode}) → {_INDEX_PATH.relative_to(_BACKEND_DIR)}")
    if not embed:
        print("Tip: run with --embed to enable semantic (FAISS) retrieval.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the fishing corpus retrieval index.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/build_index.py             # fast keyword index\n"
            "  python scripts/build_index.py --embed     # semantic FAISS index\n"
            "  python scripts/build_index.py --dry-run   # stats only\n"
        ),
    )
    parser.add_argument("--embed",   action="store_true", help="Generate and store embeddings.")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing.")
    args = parser.parse_args()

    print(f"Corpus directory : {_CORPUS_DIR}")
    print(f"Output           : {_INDEX_PATH}\n")
    build(embed=args.embed, dry_run=args.dry_run)
