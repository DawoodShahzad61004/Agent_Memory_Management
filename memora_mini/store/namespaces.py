"""Namespace constants and the one namespace -> collection-name mapping."""
from __future__ import annotations

from memora_mini.config import DOMAIN

EPISODIC = ("memora", DOMAIN, "episodic")
SEMANTIC = ("memora", DOMAIN, "semantic")
FAILURE = ("memora", "global", "failure")
PROCEDURAL = ("memora", "global", "procedural")

ALL_NAMESPACES = (EPISODIC, SEMANTIC, FAILURE, PROCEDURAL)

# Not a memory namespace: a pending-reflection buffer of raw interactions.
# It lives in Chroma because Chroma is the only datastore, but nothing recalls
# from it and it is never injected into a prompt.
INTERACTIONS = ("memora", DOMAIN, "interactions")

ALL_COLLECTION_NAMESPACES = ALL_NAMESPACES + (INTERACTIONS,)

# LangMem memory type per namespace — kept explicit so `memory_type` on a
# record can never disagree with where the record lives.
MEMORY_TYPE = {
    EPISODIC: "episodic",
    SEMANTIC: "semantic",
    FAILURE: "episodic_negative",
    PROCEDURAL: "procedural",
}


def collection_name(namespace: tuple[str, ...]) -> str:
    """Deterministic namespace -> Chroma collection name."""
    if not namespace or not all(isinstance(p, str) and p for p in namespace):
        raise ValueError(f"invalid namespace: {namespace!r}")
    return "__".join(namespace)
