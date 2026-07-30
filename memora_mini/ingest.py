"""corpus/*.txt|md -> chunk -> embed -> the `documents` collection.

Plain text only. No PDF ingestion, no document-conversion service - that is an
explicit non-goal for this sandbox.
"""
from __future__ import annotations

import logging
from pathlib import Path

from memora_mini.config import CHUNK_OVERLAP, CHUNK_SIZE, CORPUS_DIR
from memora_mini.graph.nodes import DOCUMENTS_NS

logger = logging.getLogger(__name__)


def chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Paragraph-greedy chunking; splits oversized paragraphs on a char window."""
    chunks: list[str] = []
    buffer = ""
    for paragraph in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(buffer) + len(paragraph) + 2 <= size:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            continue
        if buffer:
            chunks.append(buffer)
        while len(paragraph) > size:
            chunks.append(paragraph[:size])
            paragraph = paragraph[size - overlap :]
        buffer = paragraph
    if buffer:
        chunks.append(buffer)
    return chunks


def ingest(store, corpus_dir: Path | str = CORPUS_DIR, *, verbose: bool = True) -> int:
    corpus_dir = Path(corpus_dir)
    files = sorted([*corpus_dir.glob("*.txt"), *corpus_dir.glob("*.md")])
    if not files:
        raise FileNotFoundError(f"no .txt/.md files in {corpus_dir}")
    total = 0
    for path in files:
        pieces = chunk(path.read_text(encoding="utf-8"))
        for index, piece in enumerate(pieces):
            store.put(
                DOCUMENTS_NS,
                f"{path.stem}::{index}",
                {"text": piece, "source": path.name, "chunk_index": index,
                 "hit_count": 0, "last_hit_at": ""},
            )
        total += len(pieces)
        if verbose:
            print(f"  ingested {path.name}: {len(pieces)} chunk(s)")
    return total
