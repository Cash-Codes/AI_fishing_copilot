#!/usr/bin/env python3
# scripts/build_index.py — Build or refresh the retrieval index from the corpus.
#
# Usage:
#   python scripts/build_index.py            # build with defaults
#   python scripts/build_index.py --dry-run  # print chunks without writing
#
# Run this script whenever corpus files are added or edited.  It is safe to
# run repeatedly — it overwrites the existing index.json each time.
#
# The script can be invoked from the repo root or from within backend/:
#   cd backend && python scripts/build_index.py
#   python backend/scripts/build_index.py   (from repo root)

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# Resolve the backend root regardless of where the script is called from.

_SCRIPT_DIR  = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_CORPUS_DIR  = _BACKEND_DIR / "app" / "corpus"
_INDEX_PATH  = _BACKEND_DIR / "app" / "retrieval" / "index.json"

# Add backend to sys.path so we can import app modules if needed later
sys.path.insert(0, str(_BACKEND_DIR))

# ── Chunking configuration ────────────────────────────────────────────────────

MIN_WORDS   = 30    # chunks shorter than this are merged with the next
MAX_WORDS   = 180   # chunks longer than this are split at sentence boundaries
INDEX_VERSION = "1.0"


# ── Chunker ───────────────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list:
    """Split text into sentences on '. ', '! ', '? ' boundaries."""
    # Basic sentence splitter — sufficient for well-formatted markdown
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _chunk_paragraphs(paragraphs: list, max_words: int, min_words: int) -> list:
    """Merge short paragraphs upward and split long ones by sentence."""
    chunks = []
    buffer = []

    def flush():
        text = " ".join(buffer).strip()
        if text:
            chunks.append(text)
        buffer.clear()

    for para in paragraphs:
        words = para.split()
        if len(words) > max_words:
            # Long paragraph: flush current buffer, then split by sentence
            if buffer:
                flush()
            sentences = _split_sentences(para)
            sentence_buf = []
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
    """Parse a markdown file into annotated chunks.

    Each chunk is a dict with:
        chunk_id, topic, heading, text, word_count, embedding (None)
    """
    text = filepath.read_text(encoding="utf-8")
    topic = filepath.stem   # e.g. "tide_basics"
    chunks = []
    current_heading = topic.replace("_", " ").title()

    # Split into lines and accumulate paragraphs under headings
    lines = text.splitlines()
    paragraphs = []
    para_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#"):
            # Flush any buffered paragraph lines
            if para_lines:
                paragraphs.append((" ".join(para_lines), current_heading))
                para_lines = []
            # Update heading (strip # characters and whitespace)
            current_heading = stripped.lstrip("#").strip()
        elif stripped == "":
            if para_lines:
                paragraphs.append((" ".join(para_lines), current_heading))
                para_lines = []
        else:
            # Strip markdown formatting (bold, italic, bullet points)
            clean = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", stripped)
            clean = re.sub(r"^[-*+]\s+", "", clean)
            if clean:
                para_lines.append(clean)

    if para_lines:
        paragraphs.append((" ".join(para_lines), current_heading))

    # Group paragraphs by heading and chunk them
    heading_groups: dict = {}
    heading_order = []
    for para_text, heading in paragraphs:
        if heading not in heading_groups:
            heading_groups[heading] = []
            heading_order.append(heading)
        heading_groups[heading].append(para_text)

    chunk_counter = 1
    for heading in heading_order:
        group_chunks = _chunk_paragraphs(
            heading_groups[heading], max_words=MAX_WORDS, min_words=MIN_WORDS
        )
        for chunk_text in group_chunks:
            wc = len(chunk_text.split())
            if wc < 10:
                continue   # skip fragments
            chunks.append({
                "chunk_id":   f"{topic}_{chunk_counter:03d}",
                "topic":      topic,
                "heading":    heading,
                "text":       chunk_text,
                "word_count": wc,
                "embedding":  None,   # populated by a future embed step
            })
            chunk_counter += 1

    return chunks


# ── Main ──────────────────────────────────────────────────────────────────────

def build(dry_run: bool = False) -> None:
    corpus_files = sorted(_CORPUS_DIR.glob("*.md"))
    if not corpus_files:
        print(f"ERROR: No .md files found in {_CORPUS_DIR}", file=sys.stderr)
        sys.exit(1)

    all_chunks = []
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

    index = {
        "version":  INDEX_VERSION,
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "chunks":   all_chunks,
    }

    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nIndex written to {_INDEX_PATH.relative_to(_BACKEND_DIR)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the fishing corpus retrieval index.")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing.")
    args = parser.parse_args()

    print(f"Corpus directory: {_CORPUS_DIR}")
    print(f"Output:           {_INDEX_PATH}\n")
    build(dry_run=args.dry_run)
