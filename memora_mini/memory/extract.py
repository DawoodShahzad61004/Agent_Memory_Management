"""Stage 1 of memory formation: one LLM call per interaction, JSON array out.

The LLM produces only the fields it can actually judge from the text. Anything
derivable in Python (track, source_paths, timestamps) is filled in here, not
asked for — an 8B model asked for eight fields reliably returns six.
"""
from __future__ import annotations

import logging

from memora_mini import prompts
from memora_mini.config import MAX_CANDIDATES_PER_INTERACTION
from memora_mini.json_fix import parse_list
from memora_mini import llm
from memora_mini.memory.schemas import EpisodicMemory, FailureMemory

logger = logging.getLogger(__name__)


def extract_episodic(interaction: dict) -> list[EpisodicMemory]:
    """Distil an accepted interaction into at most N reusable Q&A lessons."""
    raw = llm.chat(
        prompts.EXTRACT_EPISODIC_SYSTEM.format(max_items=MAX_CANDIDATES_PER_INTERACTION),
        prompts.EXTRACT_EPISODIC_USER.format(
            question=interaction.get("question", ""),
            answer=interaction.get("answer", ""),
            context=(interaction.get("context") or "")[:3000],
        ),
    )
    candidates = parse_list(raw, EpisodicMemory, limit=MAX_CANDIDATES_PER_INTERACTION)
    for candidate in candidates:
        # track is load-bearing: episodic recall filters on track="learned_qa",
        # so a wrong value shows up as a retrieval miss, not silent rot.
        candidate.track = "learned_qa"
        candidate.source_paths = list(interaction.get("source_paths") or [])
    logger.info("extract: %d episodic candidate(s)", len(candidates))
    return candidates


def extract_failure(interaction: dict) -> list[FailureMemory]:
    """Turn a thumbdown into at most N failure records.

    The point of this call is `missing_information`: a short noun phrase naming
    what should have been retrieved. That, not the raw feedback text, is what
    gets injected into later prompts.
    """
    raw = llm.chat(
        prompts.EXTRACT_FAILURE_SYSTEM.format(max_items=MAX_CANDIDATES_PER_INTERACTION),
        prompts.EXTRACT_FAILURE_USER.format(
            question=interaction.get("question", ""),
            answer=interaction.get("answer", ""),
            feedback=interaction.get("feedback", ""),
        ),
    )
    candidates = parse_list(raw, FailureMemory, limit=MAX_CANDIDATES_PER_INTERACTION)
    for candidate in candidates:
        candidate.failed_variants = list(interaction.get("variants") or [])
    logger.info("extract: %d failure candidate(s)", len(candidates))
    return candidates
