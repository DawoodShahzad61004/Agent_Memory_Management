"""The six graph nodes. Each is a plain function of state -> partial state."""
from __future__ import annotations

import logging

from memora_mini import prompts
from memora_mini.config import (
    DOCUMENTS_COLLECTION,
    DOCUMENTS_TOP_K,
    EPISODIC_TOP_K,
    MAX_FAILURE_INJECTIONS,
    MAX_ITERATIONS,
    SEMANTIC_TOP_K,
)
from memora_mini.json_fix import parse_enum
from memora_mini import llm
from memora_mini.memory.recall import recall
from memora_mini.memory.reflect import log_interaction
from memora_mini.store.namespaces import EPISODIC, FAILURE, SEMANTIC

logger = logging.getLogger(__name__)

DOCUMENTS_NS = (DOCUMENTS_COLLECTION,)  # not a memory namespace; read-only corpus


def load_memory(state: dict) -> dict:
    """Semantic facts for the query, plus semantically similar prior failures.

    No exact-string matching anywhere — this is the BUG-009 fix. A thumbdown on
    "What is ASD?" has to reach "What is ASD and its main characteristics?".
    """
    store, question = state["store"], state["question"]
    facts = recall(store, SEMANTIC, question, limit=SEMANTIC_TOP_K)
    # Capped by strength score: the parent project hit prompt-bloat problems
    # past ~1,800 tokens against an 8B instruction-following ceiling.
    failures = recall(store, FAILURE, question, limit=MAX_FAILURE_INJECTIONS)
    return {
        "semantic_facts": [f.value for f in facts],
        "failure_memories": [f.value for f in failures],
        "iteration": 0,
    }


def retrieve(state: dict) -> dict:
    """Two tracks, kept separate. They are never merged or co-ranked here."""
    store, question = state["store"], state["question"]
    iteration = state.get("iteration", 0)

    documents = recall(store, DOCUMENTS_NS, question, limit=DOCUMENTS_TOP_K, active_only=False)

    # track is load-bearing: this filter is the retrieval path that depends on
    # it, so a wrong track value produces a visible miss rather than silent rot.
    episodic_filter: dict = {"track": "learned_qa"}
    if iteration > 0:
        # On retry, the first pass was judged insufficient — narrow the learned
        # track to human evidence. This is the retrieval path that makes
        # evidence_type load-bearing too.
        episodic_filter["evidence_type"] = {"$in": ["observational", "rct", "meta_analysis"]}
    learned = recall(store, EPISODIC, question, limit=EPISODIC_TOP_K, filter=episodic_filter)

    return {
        "document_chunks": [d.value for d in documents],
        "learned_qa": [l.value for l in learned],
        "iteration": iteration + 1,
    }


def generate(state: dict) -> dict:
    """The context boundary: the only place the two tracks are combined."""
    facts = state.get("semantic_facts") or []
    failures = state.get("failure_memories") or []

    semantic_block = ""
    if facts:
        semantic_block = prompts.SEMANTIC_BLOCK.format(
            facts="\n".join(f"- {f.get('text', '')}" for f in facts)
        )

    redirection_block = ""
    if failures:
        lines = [
            prompts.REDIRECTION_LINE.format(missing=f.get("missing_information", "").strip())
            for f in failures[:MAX_FAILURE_INJECTIONS]
            if f.get("missing_information")
        ]
        if lines:
            redirection_block = prompts.REDIRECTION_BLOCK.format(redirections="\n".join(lines))

    learned_block = "\n\n".join(l.get("text", "") for l in state.get("learned_qa") or []) or "(none)"
    documents_block = "\n\n".join(
        f"[{d.get('source', '?')}] {d.get('text', '')}" for d in state.get("document_chunks") or []
    ) or "(none)"

    user = prompts.GENERATE_USER.format(
        question=state["question"],
        semantic_block=semantic_block,
        redirection_block=redirection_block,
        learned_block=learned_block,
        documents_block=documents_block,
    )
    answer = llm.chat(prompts.GENERATE_SYSTEM, user, max_tokens=400)
    return {"answer": answer, "prompt": user}


def judge(state: dict) -> dict:
    """One LLM call, one enum token."""
    raw = llm.chat(
        prompts.JUDGE_SYSTEM,
        prompts.JUDGE_USER.format(
            question=state["question"],
            answer=state.get("answer", ""),
            context=(state.get("prompt", ""))[-2000:],
        ),
        max_tokens=6,
    )
    return {"verdict": parse_enum(raw, ("OK", "INSUFFICIENT"), "OK")}


def route_after_judge(state: dict) -> str:
    if state.get("verdict") == "INSUFFICIENT" and state.get("iteration", 0) < MAX_ITERATIONS:
        return "retrieve"
    return "log_interaction"


def log_interaction_node(state: dict) -> dict:
    key = log_interaction(
        state["store"],
        {
            "question": state["question"],
            "answer": state.get("answer", ""),
            "context": state.get("prompt", ""),
            "status": "OK",
            "source_paths": sorted(
                {d.get("source", "") for d in state.get("document_chunks") or [] if d.get("source")}
            ),
        },
    )
    return {"interaction_id": key}
