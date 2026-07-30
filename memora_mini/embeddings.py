"""Local sentence-transformers embeddings. There is no remote embeddings API.

Adapted from ../RAG-work/app_workflow/services/embedding_manager.py, trimmed to
what this sandbox needs (normalised vectors, lazy singleton, no encode timeout
thread — the corpus here is a handful of files).
"""
from __future__ import annotations

import logging

from memora_mini.config import EMBEDDING_DIM, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model = None


def _load():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(EMBEDDING_MODEL, device=device)
        dim = _model.get_embedding_dimension()
        if dim != EMBEDDING_DIM:
            raise RuntimeError(f"{EMBEDDING_MODEL} gave {dim}-dim, expected {EMBEDDING_DIM}")
        logger.info("embeddings: %s on %s (%d-dim)", EMBEDDING_MODEL, device, dim)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts into normalised 384-dim vectors."""
    if not texts:
        return []
    vectors = _load().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
