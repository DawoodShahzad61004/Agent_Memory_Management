"""Near-duplicate grouping (embeddings) and merging (LLM-assisted, with a
deterministic fallback) over DurableMemory records.

Rewritten from the RAG-work sibling project's version, which grouped
LangGraph retrieval chunks (`GraphState`, `nodes.nac._merge_similar_chunks`,
`validators.validate_merge`, `switches`, `timing_tracker`) - none of which
exist here. The grouping *pattern* (embed once, pairwise cosine similarity
against each group's anchor, threshold cutoff) carries over; everything
downstream of it is new, built for DurableMemory instead of retrieval chunks.

merge_group() always computes the deterministic union first - the ADR-014
precedent this repo's own memora_mini established, so a merge can never fail
to produce *something* even if the LLM is disabled, unreachable, or its
output is judged unfaithful. The LLM path, when it succeeds and passes
judge_call, replaces just the merged content.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable, Sequence

from .. import config
from ..memory import DurableMemory, content_id

logger = logging.getLogger(__name__)

LLMCall = Callable[[list[dict]], "str | None"]


def find_near_duplicate_groups(
    memories: Sequence[DurableMemory], embedder, threshold: float
) -> list[list[int]]:
    """Group indices into `memories` by pairwise cosine similarity against
    each group's anchor (the first unclaimed index) - not transitive
    closure, matching the original RAG pattern this was adapted from.
    Singleton groups (no duplicate found) are included too, so callers have
    one uniform list of groups to merge/pass through."""
    if not memories:
        return []
    embeddings = embedder.generate_embedding([m.content for m in memories])
    claimed: set[int] = set()
    groups: list[list[int]] = []
    for i in range(len(memories)):
        if i in claimed:
            continue
        group = [i]
        for j in range(i + 1, len(memories)):
            if j in claimed:
                continue
            similarity = embedder.cosine_similarity(embeddings[i], embeddings[j])
            if similarity >= threshold:
                group.append(j)
                claimed.add(j)
        claimed.add(i)
        groups.append(group)
    return groups


def _deterministic_union(group: Sequence[DurableMemory]) -> DurableMemory:
    """Plain Python union, no LLM: concatenate distinct text, earliest
    created_at, latest last_accessed_at (so a reinforced memory decays
    slower - see consolidate.refresh_decay), max importance, explicit
    provenance wins if any member has it."""
    ordered = sorted(group, key=lambda memory: memory.importance, reverse=True)
    keeper = ordered[0]
    content = "\n---\n".join(dict.fromkeys(memory.content for memory in ordered))
    return DurableMemory(
        id=content_id(content),
        content=content,
        tag=keeper.tag,
        created_at=min(memory.created_at for memory in ordered),
        last_accessed_at=max(memory.last_accessed_at for memory in ordered),
        importance=max(memory.importance for memory in ordered),
        provenance="explicit" if any(memory.provenance == "explicit" for memory in ordered) else "inferred",
        merged_from=[source_id for memory in ordered for source_id in memory.merged_from],
    )


_MERGE_PROMPT = """You are consolidating {count} near-duplicate entries from an agent's episodic \
memory log into a single durable memory. The entries were already judged near-duplicate by \
embedding similarity - your job is to fold them into ONE statement that keeps every distinct fact \
and drops repetition. Do not add anything the entries don't say.

Respond with ONLY the merged text - no preamble, no labels, no surrounding quotes.

Entries:
{entries}"""

_JUDGE_PROMPT = """A memory-consolidation step merged these {count} source entries:
{entries}

into this single merged statement:
{merged}

Does the merged statement preserve every distinct fact from the sources, without inventing \
anything the sources don't say? Respond with exactly one word: FAITHFUL or UNFAITHFUL."""


def _format_entries(group: Sequence[DurableMemory]) -> str:
    return "\n\n".join(f"- {memory.content}" for memory in group)


def _llm_merge_text(group: Sequence[DurableMemory], llm_call: LLMCall) -> str | None:
    prompt = _MERGE_PROMPT.format(count=len(group), entries=_format_entries(group))
    try:
        text = llm_call([{"role": "user", "content": prompt}])
    except Exception:
        logger.exception("[DEDUP_MERGE] LLM merge call raised")
        return None
    return text.strip() if text and text.strip() else None


def _judge_accepts(group: Sequence[DurableMemory], merged_text: str, judge_call: LLMCall) -> bool:
    prompt = _JUDGE_PROMPT.format(
        count=len(group), entries=_format_entries(group), merged=merged_text
    )
    try:
        verdict = judge_call([{"role": "user", "content": prompt}])
    except Exception:
        logger.exception("[DEDUP_MERGE] judge call raised")
        return False
    if not verdict:
        return False
    verdict = verdict.strip().upper()
    if "UNFAITHFUL" in verdict:
        return False
    return "FAITHFUL" in verdict


def merge_group(
    group: Sequence[DurableMemory],
    *,
    llm_call: LLMCall | None = None,
    judge_call: LLMCall | None = None,
) -> DurableMemory:
    base = _deterministic_union(group)
    if len(group) > 1 and llm_call is not None and config.MERGE_LLM_ENABLED:
        text = _llm_merge_text(group, llm_call)
        if text:
            accepted = (
                judge_call is None
                or not config.MERGE_VALIDATION_ENABLED
                or _judge_accepts(group, text, judge_call)
            )
            if accepted:
                return replace(base, content=text, id=content_id(text))
            logger.info("[DEDUP_MERGE] judge rejected LLM merge — using deterministic union")
    return base


def _default_embedder():
    from .embedding_manager import EmbeddingManager

    return EmbeddingManager()


def _default_llm_calls() -> tuple[LLMCall, LLMCall]:
    from . import llm_caller, llm_setup

    def llm_call(messages: list[dict]) -> str | None:
        result = llm_caller.llm_invoke(llm_setup.llm, messages, caller_tag="mem_manage.merge")
        return result.content if result.ok else None

    def judge_call(messages: list[dict]) -> str | None:
        result = llm_caller.llm_invoke(llm_setup.judge_llm, messages, caller_tag="mem_manage.judge")
        return result.content if result.ok else None

    return llm_call, judge_call


def dedupe_and_merge(
    memories: Sequence[DurableMemory],
    *,
    embedder=None,
    threshold: float | None = None,
    llm_call: LLMCall | None = None,
    judge_call: LLMCall | None = None,
    use_llm: bool = True,
) -> list[DurableMemory]:
    """Group near-duplicates by embedding similarity, then merge each group.

    `embedder`/`llm_call`/`judge_call` default to the real services (built
    lazily, imported only here) when omitted; pass fakes to run entirely
    offline, e.g. in tests. `use_llm=False` skips the LLM path outright and
    always uses the deterministic union, without needing to touch
    config.MERGE_LLM_ENABLED.
    """
    if not memories:
        return []
    embedder = embedder or _default_embedder()
    threshold = config.MERGE_SIMILARITY_THRESHOLD if threshold is None else threshold
    groups = find_near_duplicate_groups(memories, embedder, threshold)

    if use_llm:
        if llm_call is None:
            llm_call, judge_call = _default_llm_calls()
    else:
        llm_call, judge_call = None, None

    return [
        merge_group([memories[i] for i in group], llm_call=llm_call, judge_call=judge_call)
        for group in groups
    ]
