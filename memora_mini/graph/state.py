from __future__ import annotations

from typing import Any, TypedDict


class RAGState(TypedDict, total=False):
    question: str
    iteration: int

    # load_memory
    semantic_facts: list[dict]
    failure_memories: list[dict]

    # retrieve — the two tracks stay separate end to end and are combined
    # only in generate(), at the context boundary.
    document_chunks: list[dict]
    learned_qa: list[dict]

    # generate / judge
    prompt: str
    answer: str
    verdict: str

    # log_interaction
    interaction_id: str
    store: Any
