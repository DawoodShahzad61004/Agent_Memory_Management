"""Stage 3: turn verdicts into memory writes. Pure Python, no LLM call.

This is the only module in the package that writes to a memory namespace.

Verdict -> operation is a fixed table:
    DUPLICATE   -> no-op; bump the existing entry's hit_count
    REFINES     -> supersede the existing entry with a merged record
    CONTRADICTS -> supersede, and append both versions to the audit log
    UNRELATED   -> insert as new

`delete` is never emitted. The lifecycle is supersede: the old record stays,
flipped to active=False with superseded_by pointing at its replacement.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from memora_mini.config import (
    AUDIT_LOG_PATH,
    CONTRADICTION_STRIKES_REQUIRED,
    DRY_RUN_MEMORY_OPS,
    MAX_OPS_PER_RUN,
    PROTECTED_HIT_COUNT,
)
from memora_mini.memory.schemas import utcnow
from memora_mini.store.protocol import SearchItem

logger = logging.getLogger(__name__)


@dataclass
class MemoryOp:
    action: str  # insert | supersede | bump | skip
    namespace: tuple[str, ...]
    verdict: str
    target_key: str | None = None  # existing record, for bump/supersede
    new_key: str | None = None
    new_value: dict[str, Any] = field(default_factory=dict)
    old_value: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def as_json(self) -> dict:
        record = {
            "action": self.action,
            "namespace": "/".join(self.namespace),
            "verdict": self.verdict,
            "target_key": self.target_key,
            "new_key": self.new_key,
            "new_text": self.new_value.get("text", ""),
            "reason": self.reason,
        }
        # A CONTRADICTS supersede must leave both versions in the audit trail.
        if self.verdict == "CONTRADICTS":
            record["old_text"] = self.old_value.get("text", "")
        return record


def _merge(existing: dict, candidate: dict) -> dict:
    """Deterministic REFINES merge — union, no LLM. Newer wins on scalars."""
    merged = {**existing, **candidate}
    for key in ("source_paths", "failed_variants", "disambiguates"):
        left, right = existing.get(key) or [], candidate.get(key) or []
        if left or right:
            merged[key] = list(dict.fromkeys([*left, *right]))
    left_text, right_text = existing.get("text", ""), candidate.get("text", "")
    merged["text"] = right_text if left_text in right_text else f"{right_text}\n{left_text}"
    merged["confidence"] = max(
        float(existing.get("confidence", 0) or 0), float(candidate.get("confidence", 0) or 0)
    )
    merged["hit_count"] = int(existing.get("hit_count", 0) or 0)
    merged["active"] = True
    merged["superseded_by"] = None
    merged["created_at"] = utcnow()
    return merged


def plan(
    namespace: tuple[str, ...], candidate: dict, neighbour: SearchItem | None, verdict: str
) -> MemoryOp:
    """One candidate + its strongest verdict -> one operation. No side effects."""
    if neighbour is None or verdict == "UNRELATED":
        return MemoryOp("insert", namespace, "UNRELATED", new_key=_new_key(), new_value=candidate,
                        reason="no related neighbour")
    hits = int(neighbour.value.get("hit_count", 0) or 0)
    protected = hits > PROTECTED_HIT_COUNT

    if verdict == "DUPLICATE":
        return MemoryOp("bump", namespace, verdict, target_key=neighbour.key,
                        reason="already known; reinforcing existing entry")

    if verdict == "REFINES":
        if protected:
            # Never destroy a heavily-used entry on a mere refinement.
            return MemoryOp("insert", namespace, verdict, new_key=_new_key(), new_value=candidate,
                            reason=f"neighbour protected (hit_count={hits}); inserting alongside")
        return MemoryOp("supersede", namespace, verdict, target_key=neighbour.key,
                        new_key=_new_key(), new_value=_merge(neighbour.value, candidate),
                        reason="merged into refined record")

    # CONTRADICTS
    strikes = int(neighbour.value.get("contradiction_strikes", 0) or 0)
    if protected and strikes + 1 < CONTRADICTION_STRIKES_REQUIRED:
        return MemoryOp("skip", namespace, verdict, target_key=neighbour.key,
                        reason=f"protected (hit_count={hits}); strike {strikes + 1} recorded, "
                               f"need {CONTRADICTION_STRIKES_REQUIRED}")
    return MemoryOp("supersede", namespace, verdict, target_key=neighbour.key,
                    new_key=_new_key(), new_value=candidate, old_value=neighbour.value,
                    reason="contradicted by newer evidence")


def apply_ops(store, ops: list[MemoryOp], *, dry_run: bool | None = None) -> dict:
    """Execute (or, in dry-run, only log) a planned batch. Guards live here."""
    dry_run = DRY_RUN_MEMORY_OPS if dry_run is None else dry_run
    summary = {"planned": len(ops), "applied": 0, "dropped": 0, "dry_run": dry_run,
               "by_action": {}}

    if len(ops) > MAX_OPS_PER_RUN:
        logger.warning("apply: capping %d ops at MAX_OPS_PER_RUN=%d", len(ops), MAX_OPS_PER_RUN)
        summary["dropped"] += len(ops) - MAX_OPS_PER_RUN
        ops = ops[:MAX_OPS_PER_RUN]

    for op in ops:
        # Guard: never act on a key that is not actually in the store.
        if op.target_key and store.get(op.namespace, op.target_key) is None:
            logger.warning("apply: dropping %s — target %s not in store", op.action, op.target_key)
            summary["dropped"] += 1
            continue
        _audit(op, dry_run)
        summary["by_action"][op.action] = summary["by_action"].get(op.action, 0) + 1
        if dry_run:
            continue
        _execute(store, op)
        summary["applied"] += 1
    return summary


def _execute(store, op: MemoryOp) -> None:
    if op.action == "bump":
        existing = store.get(op.namespace, op.target_key).value
        store.update_metadata(op.namespace, op.target_key,
                              {"hit_count": int(existing.get("hit_count", 0) or 0) + 1,
                               "last_hit_at": utcnow()})
    elif op.action == "insert":
        store.put(op.namespace, op.new_key, op.new_value)
    elif op.action == "supersede":
        store.put(op.namespace, op.new_key, op.new_value)
        store.update_metadata(op.namespace, op.target_key,
                              {"active": False, "superseded_by": op.new_key})
    elif op.action == "skip":
        existing = store.get(op.namespace, op.target_key).value
        store.update_metadata(op.namespace, op.target_key,
                              {"contradiction_strikes": int(existing.get("contradiction_strikes", 0) or 0) + 1})


def _audit(op: MemoryOp, dry_run: bool) -> None:
    record = {"ts": utcnow(), "dry_run": dry_run, **op.as_json()}
    logger.info("memory_op %s", json.dumps(record))
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _new_key() -> str:
    return uuid.uuid4().hex[:16]
