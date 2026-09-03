"""End-to-end scenarios for mem_manage.compact: markdown text/file in,
compacted durable memories out. Exercises the full parse -> score ->
dedupe/merge -> decay -> prune chain together, on top of the stage-level
unit tests in the other test files.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mem_manage import config
from mem_manage.compact import compact_markdown, compact_markdown_file
from mem_manage.consolidate import rerank_and_prune
from mem_manage.importance import EpisodicRecord
from mem_manage.memory import build_durable_memories
from mem_manage.services.dedup_merge import dedupe_and_merge

from .conftest import (
    CONFLICTING_MD,
    EMPTY_MD,
    LARGE_CORPUS_MD,
    MALFORMED_MD,
    NEAR_DUPLICATE_MD,
    STRAY_PREAMBLE_MD,
)


class TestCompactMarkdownScenarios:
    def test_duplicate_reinforcement_pulls_last_accessed_at_forward(self, frozen_now, fake_embedder):
        result = compact_markdown(NEAR_DUPLICATE_MD, now=frozen_now, embedder=fake_embedder, use_llm=False)
        assert len(result) == 1
        merged = result[0]
        # The merge should reflect the *latest* contributing entry (day 3),
        # not the earliest (day 1) - this is what lets a reinforced memory
        # decay less than an unreinforced one from this point on (see
        # test_consolidate.py for the decay-magnitude side of this).
        assert merged.last_accessed_at == datetime(2026, 8, 3, 9, 0, 0, tzinfo=timezone.utc)
        assert merged.created_at == datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc)
        assert len(merged.merged_from) == 3

    def test_same_topic_conflict_survives_as_two_versions(self, frozen_now, fake_embedder):
        result = compact_markdown(CONFLICTING_MD, now=frozen_now, embedder=fake_embedder, use_llm=False)
        assert len(result) == 2
        contents = {memory.content for memory in result}
        assert "tabs" in "".join(contents)
        assert "spaces-only" in "".join(contents)

    def test_large_corpus_loses_its_bottom_twenty_percent(self, frozen_now, fake_embedder):
        result = compact_markdown(LARGE_CORPUS_MD, now=frozen_now, embedder=fake_embedder, use_llm=False)
        assert len(result) == 8  # 10 mutually-distinct entries, none merge; floor(10*0.2)=2 pruned

    def test_malformed_markdown_skips_bad_entries_without_crashing(self, frozen_now, fake_embedder):
        result = compact_markdown(MALFORMED_MD, now=frozen_now, embedder=fake_embedder, use_llm=False)
        assert len(result) == 2  # the two well-formed entries survive

    def test_empty_markdown_produces_an_empty_result_without_crashing(self, frozen_now, fake_embedder):
        assert compact_markdown(EMPTY_MD, now=frozen_now, embedder=fake_embedder, use_llm=False) == []

    def test_stray_preamble_before_first_header_is_ignored_end_to_end(self, frozen_now, fake_embedder):
        result = compact_markdown(STRAY_PREAMBLE_MD, now=frozen_now, embedder=fake_embedder, use_llm=False)
        assert len(result) == 1
        assert result[0].tag == "entry-one"

    def test_compact_markdown_file_reads_from_disk(self, frozen_now, fake_embedder, tmp_path):
        path = tmp_path / "episodic_log.md"
        path.write_text(LARGE_CORPUS_MD, encoding="utf-8")
        result = compact_markdown_file(path, now=frozen_now, embedder=fake_embedder, use_llm=False)
        assert len(result) == 8


class TestExplicitProvenanceBoundary:
    def test_explicit_provenance_survives_a_prune_boundary_an_inferred_twin_would_not(
        self, frozen_now, fake_embedder
    ):
        # 3 high-scoring "padding" records (each mentions a unique salient
        # entity and a success marker -> composite score saturates at 1.0),
        # plus an explicit/inferred pair with otherwise-neutral, no-entity
        # content so provenance is the only thing separating them. All 5
        # timestamps are identical (frozen_now), removing recency as a
        # variable. Pairwise text similarity was checked empirically to stay
        # well under MERGE_SIMILARITY_THRESHOLD, so nothing here merges.
        records = [
            EpisodicRecord(frozen_now, "pad-1", "Deployed the Widget service and all smoke tests passed."),
            EpisodicRecord(frozen_now, "pad-2", "Fixed the Gadget regression; the fix works correctly."),
            EpisodicRecord(frozen_now, "pad-3", "Resolved the Sprocket timeout issue successfully."),
            EpisodicRecord(
                frozen_now,
                "pref-explicit",
                "the team stated explicitly that trailing whitespace should always be stripped",
                provenance="explicit",
            ),
            EpisodicRecord(
                frozen_now,
                "pref-inferred",
                "trailing whitespace appears to usually be stripped based on observed commits",
                provenance="inferred",
            ),
        ]
        memories = build_durable_memories(records, now=frozen_now)
        memories = dedupe_and_merge(memories, embedder=fake_embedder, use_llm=False)
        assert len(memories) == 5  # confirms nothing accidentally merged

        pruned = rerank_and_prune(memories)  # default 20% of 5 -> floor(1) pruned
        surviving_tags = {memory.tag for memory in pruned}
        assert len(pruned) == 4
        assert "pref-explicit" in surviving_tags
        assert "pref-inferred" not in surviving_tags


# --- Optional integration tests: real dependencies, skip cleanly if absent --------


def test_real_embedding_manager_dedup_merge_integration(frozen_now):
    pytest.importorskip("sentence_transformers")
    from mem_manage.services.embedding_manager import EmbeddingManager

    embedder = EmbeddingManager()
    result = compact_markdown(NEAR_DUPLICATE_MD, now=frozen_now, embedder=embedder, use_llm=False)
    assert len(result) == 1


def test_real_llm_merge_integration(frozen_now, fake_embedder):
    pytest.importorskip("langchain_openai")
    httpx = pytest.importorskip("httpx")

    if not config.CUSTOM_API_BASE:
        pytest.skip("CUSTOM_API_BASE not configured in .env")
    try:
        httpx.get(config.CUSTOM_API_BASE, timeout=config.LLM_REACHABILITY_TIMEOUT_SECONDS)
    except Exception:
        pytest.skip("CUSTOM_API_BASE not reachable")

    result = compact_markdown(NEAR_DUPLICATE_MD, now=frozen_now, embedder=fake_embedder, use_llm=True)
    assert len(result) == 1
