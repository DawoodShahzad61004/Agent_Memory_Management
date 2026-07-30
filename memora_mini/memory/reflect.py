"""Memory formation: extract -> classify -> apply, over pending interactions.

Runs offline only — on the `learn` command or every LEARN_EVERY_N successful
interactions. Never in the request path.

Episodic and failure memories go through the same code path; only the
namespace, the extractor and the schema differ. That is what makes ten
thumbdowns on one theme collapse into one entry instead of accumulating ten
near-duplicates: each new failure candidate is classified against the existing
failure memories exactly like an episodic one.
"""
from __future__ import annotations

import logging

from memora_mini.config import PROCEDURAL_PROPOSAL_HITS
from memora_mini.memory import apply as apply_mod
from memora_mini.memory import classify as classify_mod
from memora_mini.memory import extract as extract_mod
from memora_mini.memory.schemas import PromptRevision, utcnow
from memora_mini.store.namespaces import EPISODIC, FAILURE, INTERACTIONS, PROCEDURAL

logger = logging.getLogger(__name__)

# (namespace, extractor) — the two lanes reflection runs over.
LANES = (
    (EPISODIC, extract_mod.extract_episodic, "OK"),
    (FAILURE, extract_mod.extract_failure, "THUMBDOWN"),
)


def pending_interactions(store) -> list[dict]:
    items = store.search(INTERACTIONS, filter={"reflected": False}, limit=100)
    return [{**item.value, "_key": item.key} for item in items]


def mark_reflected(store, interaction: dict) -> None:
    store.update_metadata(INTERACTIONS, interaction["_key"], {"reflected": True, "reflected_at": utcnow()})


def reflect(store, *, dry_run: bool | None = None, verbose: bool = True) -> dict:
    """One reflection run. Returns a summary dict per lane."""
    interactions = pending_interactions(store)
    if not interactions:
        return {"interactions": 0, "lanes": {}}

    report: dict = {"interactions": len(interactions), "lanes": {}}
    for namespace, extractor, wanted_status in LANES:
        lane = [i for i in interactions if i.get("status") == wanted_status]
        ops: list[apply_mod.MemoryOp] = []
        for interaction in lane:
            for candidate in extractor(interaction):
                value = candidate.to_value()
                pairs = classify_mod.classify(store, namespace, value["text"])
                neighbour, verdict = classify_mod.strongest(pairs)
                op = apply_mod.plan(namespace, value, neighbour, verdict)
                if verbose:
                    print(f"    [{namespace[-1]}] {verdict:<11} -> {op.action:<10} {op.reason}")
                ops.append(op)
        summary = apply_mod.apply_ops(store, ops, dry_run=dry_run)
        report["lanes"][namespace[-1]] = summary
        logger.info("reflect: %s -> %s", namespace[-1], summary)

    report["lanes"]["procedural"] = apply_mod.apply_ops(
        store, propose_prompt_revisions(store), dry_run=dry_run
    )

    # Interactions are only consumed once they have actually been written back.
    resolved_dry_run = apply_mod.DRY_RUN_MEMORY_OPS if dry_run is None else dry_run
    if not resolved_dry_run:
        for interaction in interactions:
            mark_reflected(store, interaction)
    return report


def propose_prompt_revisions(store) -> list[apply_mod.MemoryOp]:
    """Deterministic, no LLM: a failure theme that keeps recurring becomes a
    proposed prompt rule. Stored with approved=False and never auto-applied —
    nothing in generate() reads the procedural namespace."""
    ops: list[apply_mod.MemoryOp] = []
    existing = {i.value.get("target_gap") for i in store.search(PROCEDURAL, limit=200)}
    for item in store.search(FAILURE, filter={"active": True}, limit=200):
        gap = (item.value.get("missing_information") or "").strip()
        hits = int(item.value.get("hit_count", 0) or 0)
        if not gap or gap in existing or hits < PROCEDURAL_PROPOSAL_HITS:
            continue
        revision = PromptRevision(
            target_prompt="GENERATE_SYSTEM",
            proposed_text=f"When the question touches this topic, always address {gap}.",
            rationale=f"failure memory {item.key} has recurred {hits} time(s)",
        ).to_value()
        revision["target_gap"] = gap
        ops.append(apply_mod.MemoryOp("insert", PROCEDURAL, "UNRELATED",
                                      new_key=apply_mod._new_key(), new_value=revision,
                                      reason="recurring failure theme"))
        existing.add(gap)
    return ops


def log_interaction(store, record: dict) -> str:
    """Persist one interaction into the pending-reflection buffer."""
    key = record.get("id") or apply_mod._new_key()
    value = {
        "text": record.get("question", "") or "(empty)",
        "question": record.get("question", ""),
        "answer": record.get("answer", ""),
        "context": (record.get("context") or "")[:4000],
        "status": record.get("status", "OK"),
        "feedback": record.get("feedback", ""),
        "variants": list(record.get("variants") or []),
        "source_paths": list(record.get("source_paths") or []),
        "reflected": False,
        "active": True,
        "created_at": utcnow(),
    }
    store.put(INTERACTIONS, key, value)
    return key
