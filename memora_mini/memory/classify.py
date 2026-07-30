"""Stage 2: classify a candidate against its nearest existing neighbours.

One LLM call per (candidate, neighbour) pair, each returning a single enum
token. Anything unparseable becomes UNRELATED — fail-safe, because UNRELATED
maps to 'insert as new' and never mutates an existing record.

The model emits classifications only. It never proposes a delete; every
destructive decision is made in apply.py, in Python.
"""
from __future__ import annotations

import logging

from memora_mini import prompts
from memora_mini.config import CLASSIFY_NEIGHBOURS
from memora_mini.json_fix import parse_enum
from memora_mini import llm
from memora_mini.memory.recall import recall
from memora_mini.store.protocol import SearchItem

logger = logging.getLogger(__name__)

VERDICTS = ("DUPLICATE", "CONTRADICTS", "REFINES", "UNRELATED")
DEFAULT_VERDICT = "UNRELATED"

# Strongest verdict wins when neighbours disagree.
PRIORITY = {"CONTRADICTS": 3, "REFINES": 2, "DUPLICATE": 1, "UNRELATED": 0}


def classify_pair(existing_text: str, candidate_text: str) -> str:
    try:
        raw = llm.chat(
            prompts.CLASSIFY_SYSTEM,
            prompts.CLASSIFY_USER.format(existing=existing_text, candidate=candidate_text),
            max_tokens=8,
        )
    except RuntimeError as exc:
        logger.warning("classify: LLM unavailable (%s) — defaulting to %s", exc, DEFAULT_VERDICT)
        return DEFAULT_VERDICT
    return parse_enum(raw, VERDICTS, DEFAULT_VERDICT)


def classify(store, namespace: tuple[str, ...], candidate_text: str) -> list[tuple[SearchItem, str]]:
    """Return [(neighbour, verdict)] for the candidate's top-N neighbours.

    bump=False: reflection is offline bookkeeping and must not inflate the hit
    counts that drive strength-based recall.
    """
    neighbours = recall(store, namespace, candidate_text, limit=CLASSIFY_NEIGHBOURS, bump=False)
    pairs = []
    for neighbour in neighbours:
        verdict = classify_pair(neighbour.value.get("text", ""), candidate_text)
        logger.info("classify: %s vs %s -> %s", candidate_text[:40], neighbour.key, verdict)
        pairs.append((neighbour, verdict))
    return pairs


def strongest(pairs: list[tuple[SearchItem, str]]) -> tuple[SearchItem | None, str]:
    """Pick the verdict that decides the op: CONTRADICTS > REFINES > DUPLICATE."""
    ranked = [p for p in pairs if p[1] != "UNRELATED"]
    if not ranked:
        return None, "UNRELATED"
    neighbour, verdict = max(ranked, key=lambda p: (PRIORITY[p[1]], p[0].score))
    return neighbour, verdict
