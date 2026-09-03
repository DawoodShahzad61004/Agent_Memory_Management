import logging
import time
from state import GraphState
from app_workflow.services.llm_setup import llm, judge_llm
from app_workflow.services.services import embedding_manager
from app_workflow.services.validators import validate_merge
from app_workflow.services.timing_tracker import timing_tracker
from app_workflow.services.switches import get_switches
from app_workflow.config import MERGE_SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def _run_dedup_merge(
    track_name: str,
    input_chunks: list[dict],
    switches: dict,
    config=None,
) -> tuple[list[dict], list[dict]]:
    """Deduplicate and merge near-duplicate chunks within one track.

    Returns (result_chunks, merge_pairs).  When ENABLE_RETRIEVAL_DEDUP_MERGE
    is False the input is returned unchanged and merge_pairs is empty.
    """
    if not input_chunks:
        logger.debug("[DEDUP_MERGE_%s] no chunks — skipping", track_name.upper())
        return [], []

    if not switches["ENABLE_RETRIEVAL_DEDUP_MERGE"]:
        logger.debug(
            "[DEDUP_MERGE_%s] disabled — passing through %d chunk(s)",
            track_name.upper(), len(input_chunks),
        )
        return list(input_chunks), []

    # Embed every chunk for pairwise cosine comparison
    chunks_with_emb: list[dict] = []
    for c in input_chunks:
        content = (c.get("content") or "").strip()
        if not content:
            continue
        emb = embedding_manager.generate_embedding(content)
        chunks_with_emb.append({**c, "embedding": emb})

    # Identify near-duplicate groups
    claimed: set[int] = set()
    merge_groups: list[list[int]] = []
    for i in range(len(chunks_with_emb)):
        if i in claimed:
            continue
        group = [i]
        for j in range(i + 1, len(chunks_with_emb)):
            if j in claimed:
                continue
            sim = embedding_manager.cosine_similarity(
                chunks_with_emb[i]["embedding"],
                chunks_with_emb[j]["embedding"],
            )
            if sim >= MERGE_SIMILARITY_THRESHOLD:
                group.append(j)
                claimed.add(j)
        if len(group) > 1:
            claimed.add(i)
            merge_groups.append(group)

    logger.debug(
        "[DEDUP_MERGE_%s] %d chunk(s) → %d merge group(s) (threshold=%.2f)",
        track_name.upper(), len(chunks_with_emb), len(merge_groups), MERGE_SIMILARITY_THRESHOLD,
    )

    # Lazy import avoids circular dependency at module load time
    from nodes.nac import _merge_similar_chunks

    merge_pairs: list[dict] = []
    indices_to_drop: set[int] = set()

    for group in merge_groups:
        keeper_idx = group[0]
        source_chunks = [chunks_with_emb[i] for i in group]
        merged = _merge_similar_chunks(
            source_chunks,
            llm,
            embedding_manager,
            output_fix_enabled=switches["ENABLE_RETRIEVAL_DEDUP_MERGE_OUTPUT_FIX"],
            switches=switches,
            config=config,
        )
        chunks_with_emb[keeper_idx] = merged
        merge_pairs.append({"source_chunks": source_chunks, "merged": merged})
        indices_to_drop.update(group[1:])
        logger.info(
            "[DEDUP_MERGE_%s] merged %d near-duplicate chunk(s) from: %s",
            track_name.upper(), len(group),
            [chunks_with_emb[i].get("source", "?") for i in group],
        )

    result_chunks: list[dict] = []
    for i, c in enumerate(chunks_with_emb):
        if i in indices_to_drop:
            continue
        clean: dict = {"content": c["content"], "source": c["source"]}
        if "similarity_score" in c:
            clean["similarity_score"] = c["similarity_score"]
        if isinstance(c.get("chunk_seq"), int):
            clean["chunk_seq"] = c["chunk_seq"]
        result_chunks.append(clean)

    saved = len(chunks_with_emb) - len(result_chunks)
    logger.info(
        "[DEDUP_MERGE_%s] %d → %d chunk(s) (%d merged/eliminated)",
        track_name.upper(), len(chunks_with_emb), len(result_chunks), saved,
    )
    return result_chunks, merge_pairs


# ── Per-track dedup-merge nodes (run in parallel) ────────────────────────────

def dedup_merge_documents(state: GraphState, config=None) -> dict:
    """Dedup-merge the documents track.

    Runs in parallel with dedup_merge_learned_qa after validate_document_retrieval
    completes.
    """
    _t0 = time.perf_counter()
    input_chunks = state.get("validated_document_chunks") or []
    result, pairs = _run_dedup_merge("documents", input_chunks, get_switches(state), config=config)
    timing_tracker.record("Total Merge Time for Retrieved Chunks", time.perf_counter() - _t0)
    return {
        "dedup_merged_document_chunks": result,
        "dedup_merge_document_pairs": pairs,
    }


def dedup_merge_learned_qa(state: GraphState, config=None) -> dict:
    """Dedup-merge the learned_qa track.

    Runs in parallel with dedup_merge_documents after validate_learned_qa_retrieval
    completes.
    """
    _t0 = time.perf_counter()
    input_chunks = state.get("validated_learned_qa_chunks") or []
    result, pairs = _run_dedup_merge("learned_qa", input_chunks, get_switches(state), config=config)
    timing_tracker.record("Total Merge Time for Retrieved Chunks", time.perf_counter() - _t0)
    return {
        "dedup_merged_learned_qa_chunks": result,
        "dedup_merge_learned_qa_pairs": pairs,
    }


# ── Per-track dedup-merge validators (run in parallel) ───────────────────────

def validate_dedup_merge_documents(state: GraphState, config=None) -> dict:
    """Validate merged document chunks for faithfulness.

    Pass-through (no-op) when ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION is False.
    Runs in parallel with validate_dedup_merge_learned_qa.
    """
    _t0 = time.perf_counter()
    sw = get_switches(state)
    if not sw["ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION"]:
        timing_tracker.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t0)
        return {}
    pairs: list[dict] = state.get("dedup_merge_document_pairs") or []
    if not pairs:
        logger.debug("[VALIDATE_DEDUP_MERGE_DOCUMENTS] no merge pairs to validate")
        timing_tracker.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t0)
        return {}
    for i, pair in enumerate(pairs):
        check = validate_merge(pair["source_chunks"], pair["merged"], judge_llm, config=config, switches=sw)
        logger.info(
            "[VALIDATE_DEDUP_MERGE_DOCUMENTS] pair %d: verdict=%s  fabricated=%d  dropped=%d",
            i, check["verdict"],
            len(check.get("fabricated_claims", [])),
            len(check.get("dropped_claims", [])),
        )
    timing_tracker.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t0)
    return {}


def validate_dedup_merge_learned_qa(state: GraphState, config=None) -> dict:
    """Validate merged learned_qa chunks for faithfulness.

    Pass-through (no-op) when ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION is False.
    Runs in parallel with validate_dedup_merge_documents.
    """
    _t0 = time.perf_counter()
    sw = get_switches(state)
    if not sw["ENABLE_RETRIEVAL_DEDUP_MERGE_VALIDATION"]:
        timing_tracker.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t0)
        return {}
    pairs: list[dict] = state.get("dedup_merge_learned_qa_pairs") or []
    if not pairs:
        logger.debug("[VALIDATE_DEDUP_MERGE_LEARNED_QA] no merge pairs to validate")
        timing_tracker.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t0)
        return {}
    for i, pair in enumerate(pairs):
        check = validate_merge(pair["source_chunks"], pair["merged"], judge_llm, config=config, switches=sw)
        logger.info(
            "[VALIDATE_DEDUP_MERGE_LEARNED_QA] pair %d: verdict=%s  fabricated=%d  dropped=%d",
            i, check["verdict"],
            len(check.get("fabricated_claims", [])),
            len(check.get("dropped_claims", [])),
        )
    timing_tracker.record("Total Validation Time for Merged Chunks", time.perf_counter() - _t0)
    return {}


from services.operation_tracing import instrument_namespace as _instrument_namespace
_instrument_namespace(globals(), "Deduplication and Merge", exclude={"dedup_merge_documents", "dedup_merge_learned_qa", "validate_dedup_merge_documents", "validate_dedup_merge_learned_qa"})
