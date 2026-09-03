"""Shared fixtures for mem_manage's test suite.

Deliberately stdlib-only by default so the whole suite runs without
sentence-transformers/torch/langchain_openai/groq installed - real-dependency
paths get their own pytest.importorskip/reachability-guarded tests instead of
being on the critical path for "does the logic work".

Fixture text similarity ratios (SequenceMatcher, which FakeEmbedder is built
on) were checked empirically against config.MERGE_SIMILARITY_THRESHOLD
(0.90) before being written here - see the near-duplicate vs. conflicting
fixtures below, which are deliberately worded to land clearly on the
intended side of that threshold rather than by eyeball.
"""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

import pytest


@pytest.fixture
def frozen_now() -> datetime:
    return datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)


class FakeEmbedder:
    """Stands in for services.embedding_manager.EmbeddingManager: 'embeddings'
    are just the input strings themselves, and cosine_similarity is really a
    stdlib text ratio - enough to exercise dedup_merge's grouping logic
    without a real model."""

    def generate_embedding(self, texts):
        return list(texts)

    def cosine_similarity(self, a, b):
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


class SpyLLM:
    """A fake llm_call/judge_call: returns a fixed response and records every
    call it received, so tests can assert both the outcome and whether the
    LLM was invoked at all."""

    def __init__(self, response: "str | None" = "MERGED"):
        self.response = response
        self.calls: list[list[dict]] = []

    def __call__(self, messages: list[dict]) -> "str | None":
        self.calls.append(messages)
        return self.response

    @property
    def call_count(self) -> int:
        return len(self.calls)


@pytest.fixture
def make_spy_llm():
    return SpyLLM


# --- sample episodic markdown -------------------------------------------------
# Header shape: '## YYYY-MM-DD HH:MM:SSZ - tag', per importance.parse_episodic_md.

# Pairwise SequenceMatcher ratios: (0,1)=0.970 (0,2)=0.948 (1,2)=0.935 - all
# comfortably above MERGE_SIMILARITY_THRESHOLD, so the whole corpus collapses
# to one durable memory regardless of which entry lands as the group anchor.
NEAR_DUPLICATE_MD = """\
## 2026-08-01 09:00:00Z - conventions
This repo uses pytest fixtures, not unittest.TestCase, for tests.

## 2026-08-02 09:00:00Z - conventions
This repo uses pytest fixtures, not unittest.TestCase, for all tests.

## 2026-08-03 09:00:00Z - conventions
This repo uses pytest fixtures, not unittest.TestCase, for every test.
"""

# Same topic, genuinely different content (ratio 0.215) - below threshold on
# purpose, so both survive as separate "versions" per Architecture.md
# Principle 4, rather than merging.
CONFLICTING_MD = """\
## 2026-08-01 09:00:00Z - style
The user asked to always use tabs for indentation in this project.

## 2026-08-15 09:00:00Z - style
Contradicting an earlier note, the team later switched the whole codebase \
over to spaces-only formatting and asked that be followed everywhere going \
forward.
"""

MALFORMED_MD = """\
## 2026-08-01 09:00:00Z - good-one
A perfectly well-formed entry.

## incomplete-header
Too few tokens in the header - should be skipped without crashing.

## 2026-08-02 99:99:99Z - bad-timestamp
Header shape matches but the timestamp itself doesn't parse.

## 2026-08-03 09:00:00Z - another-good-one
Another well-formed entry that should survive parsing.
"""

STRAY_PREAMBLE_MD = """\
# Episodic Log

## 2026-08-01 09:00:00Z - entry-one
Some content here.
"""

EMPTY_MD = ""

# Ten mutually-distinct entries (max pairwise SequenceMatcher ratio 0.529,
# empirically checked - well under MERGE_SIMILARITY_THRESHOLD) so dedup/merge
# never collapses any of them: prune-boundary tests can assert an exact
# N -> N - floor(N * 0.20) count without also having to account for merges.
_LARGE_CORPUS_TOPICS = [
    ("infra", "Deployed the staging server using docker compose."),
    ("bugfix", "Fixed the off-by-one error in the pagination helper."),
    ("research", "Compared three embedding models for retrieval quality."),
    ("infra", "Rotated the database credentials after the audit."),
    ("bugfix", "The login flow failed with a null pointer on empty input."),
    ("research", "Benchmarked the new caching layer under load."),
    ("docs", "Wrote the onboarding guide for new contributors."),
    ("bugfix", "Test suite passed after fixing the flaky timeout."),
    ("infra", "Migrated the CI pipeline to the new runner image."),
    ("docs", "Updated the API reference for the v2 endpoints."),
]


def _build_large_corpus_md() -> str:
    lines: list[str] = []
    for day, (tag, content) in enumerate(_LARGE_CORPUS_TOPICS, start=1):
        lines.append(f"## 2026-08-{day:02d} 09:00:00Z - {tag}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


LARGE_CORPUS_MD = _build_large_corpus_md()
