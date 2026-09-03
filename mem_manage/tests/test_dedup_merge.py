"""Multi-scenario tests for mem_manage.services.dedup_merge: near-duplicate
grouping, the deterministic union, and the LLM-assisted merge path with its
fallback. All offline - FakeEmbedder and SpyLLM stand in for the real
sentence-transformers/LangChain clients (see conftest.py).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from mem_manage import config
from mem_manage.memory import DurableMemory, content_id
from mem_manage.services.dedup_merge import (
    dedupe_and_merge,
    find_near_duplicate_groups,
    merge_group,
)


def _memory(frozen_now, *, content, tag="t", importance=0.5, offset_hours=0, provenance="inferred"):
    created = frozen_now + timedelta(hours=offset_hours)
    memory_id = content_id(f"{content}|{tag}|{offset_hours}")
    return DurableMemory(
        id=memory_id,
        content=content,
        tag=tag,
        created_at=created,
        last_accessed_at=created,
        importance=importance,
        provenance=provenance,
        merged_from=[memory_id],
    )


# --- find_near_duplicate_groups ------------------------------------------------


class TestFindNearDuplicateGroups:
    def test_two_similar_memories_group_together(self, frozen_now, fake_embedder):
        a = _memory(frozen_now, content="This repo uses pytest fixtures for tests.")
        b = _memory(frozen_now, content="This repo uses pytest fixtures for all tests.")
        groups = find_near_duplicate_groups([a, b], fake_embedder, config.MERGE_SIMILARITY_THRESHOLD)
        assert groups == [[0, 1]]

    def test_dissimilar_memories_stay_in_separate_groups(self, frozen_now, fake_embedder):
        a = _memory(frozen_now, content="Deployed the staging server using docker compose.")
        b = _memory(frozen_now, content="Wrote the onboarding guide for new contributors.")
        groups = find_near_duplicate_groups([a, b], fake_embedder, config.MERGE_SIMILARITY_THRESHOLD)
        assert groups == [[0], [1]]

    def test_three_way_group(self, frozen_now, fake_embedder):
        contents = [
            "This repo uses pytest fixtures, not unittest.TestCase, for tests.",
            "This repo uses pytest fixtures, not unittest.TestCase, for all tests.",
            "This repo uses pytest fixtures, not unittest.TestCase, for every test.",
        ]
        memories = [_memory(frozen_now, content=c, offset_hours=i) for i, c in enumerate(contents)]
        groups = find_near_duplicate_groups(memories, fake_embedder, config.MERGE_SIMILARITY_THRESHOLD)
        assert groups == [[0, 1, 2]]

    def test_empty_input_returns_empty_list(self, fake_embedder):
        assert find_near_duplicate_groups([], fake_embedder, 0.9) == []

    def test_threshold_boundary_with_exact_similarity_values(self, frozen_now):
        # Hand-picked similarities, no text-ratio guessing: (0,1) sits exactly
        # at the threshold (must merge), (0,2) sits just below (must not).
        similarities = {frozenset((0, 1)): 0.90, frozenset((0, 2)): 0.8999}

        class MatrixEmbedder:
            def generate_embedding(self, texts):
                return list(range(len(texts)))  # indices double as "vectors"

            def cosine_similarity(self, a, b):
                return similarities[frozenset((a, b))]

        memories = [_memory(frozen_now, content=f"content {i}", offset_hours=i) for i in range(3)]
        groups = find_near_duplicate_groups(memories, MatrixEmbedder(), 0.90)
        assert groups == [[0, 1], [2]]


# --- merge_group: deterministic union -------------------------------------------


class TestDeterministicUnion:
    def test_singleton_passes_through_content_unchanged(self, frozen_now):
        memory = _memory(frozen_now, content="only one entry", importance=0.7)
        merged = merge_group([memory])
        assert merged.content == "only one entry"
        assert merged.merged_from == memory.merged_from

    def test_two_way_merge_unions_fields(self, frozen_now):
        earlier_higher_importance = _memory(
            frozen_now, content="first version of the fact", importance=0.9, offset_hours=0
        )
        later_lower_importance = _memory(
            frozen_now, content="second version of the fact", importance=0.3, offset_hours=5
        )
        merged = merge_group([earlier_higher_importance, later_lower_importance])
        assert "first version of the fact" in merged.content
        assert "second version of the fact" in merged.content
        assert merged.created_at == earlier_higher_importance.created_at
        assert merged.last_accessed_at == later_lower_importance.last_accessed_at
        assert merged.importance == pytest.approx(0.9)
        assert set(merged.merged_from) == {
            earlier_higher_importance.id,
            later_lower_importance.id,
        }

    def test_explicit_provenance_wins_if_any_member_has_it(self, frozen_now):
        inferred = _memory(frozen_now, content="a", provenance="inferred")
        explicit = _memory(frozen_now, content="b", provenance="explicit", offset_hours=1)
        merged = merge_group([inferred, explicit])
        assert merged.provenance == "explicit"

    def test_identical_content_is_not_duplicated_in_merged_text(self, frozen_now):
        a = _memory(frozen_now, content="same text", offset_hours=0)
        b = _memory(frozen_now, content="same text", offset_hours=1)
        merged = merge_group([a, b])
        assert merged.content.count("same text") == 1


# --- merge_group: LLM-assisted path + fallback -----------------------------------


class TestMergeGroupLLMPath:
    def test_llm_merge_accepted_by_judge_replaces_content(self, frozen_now, make_spy_llm, monkeypatch):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", True)
        monkeypatch.setattr(config, "MERGE_VALIDATION_ENABLED", True)
        a = _memory(frozen_now, content="fact stated one way", offset_hours=0)
        b = _memory(frozen_now, content="fact stated another way", offset_hours=1)
        llm_call = make_spy_llm(response="the LLM-synthesized merged fact")
        judge_call = make_spy_llm(response="FAITHFUL")
        merged = merge_group([a, b], llm_call=llm_call, judge_call=judge_call)
        assert merged.content == "the LLM-synthesized merged fact"
        assert llm_call.call_count == 1
        assert judge_call.call_count == 1

    def test_llm_merge_rejected_by_judge_falls_back_to_deterministic(
        self, frozen_now, make_spy_llm, monkeypatch
    ):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", True)
        monkeypatch.setattr(config, "MERGE_VALIDATION_ENABLED", True)
        a = _memory(frozen_now, content="fact one", offset_hours=0)
        b = _memory(frozen_now, content="fact two", offset_hours=1)
        llm_call = make_spy_llm(response="a fabricated merge")
        judge_call = make_spy_llm(response="UNFAITHFUL")
        merged = merge_group([a, b], llm_call=llm_call, judge_call=judge_call)
        assert "fact one" in merged.content and "fact two" in merged.content
        assert "a fabricated merge" not in merged.content

    def test_llm_call_returning_none_falls_back_to_deterministic(
        self, frozen_now, make_spy_llm, monkeypatch
    ):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", True)
        a = _memory(frozen_now, content="fact one", offset_hours=0)
        b = _memory(frozen_now, content="fact two", offset_hours=1)
        llm_call = make_spy_llm(response=None)
        merged = merge_group([a, b], llm_call=llm_call)
        assert "fact one" in merged.content and "fact two" in merged.content

    def test_llm_call_returning_whitespace_only_falls_back(
        self, frozen_now, make_spy_llm, monkeypatch
    ):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", True)
        a = _memory(frozen_now, content="fact one", offset_hours=0)
        b = _memory(frozen_now, content="fact two", offset_hours=1)
        llm_call = make_spy_llm(response="   \n  ")
        merged = merge_group([a, b], llm_call=llm_call)
        assert "fact one" in merged.content and "fact two" in merged.content

    def test_merge_llm_disabled_flag_skips_llm_entirely(
        self, frozen_now, make_spy_llm, monkeypatch
    ):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", False)
        a = _memory(frozen_now, content="fact one", offset_hours=0)
        b = _memory(frozen_now, content="fact two", offset_hours=1)
        llm_call = make_spy_llm(response="should never be used")
        merged = merge_group([a, b], llm_call=llm_call)
        assert llm_call.call_count == 0
        assert "fact one" in merged.content and "fact two" in merged.content

    def test_singleton_group_never_calls_the_llm(self, frozen_now, make_spy_llm, monkeypatch):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", True)
        memory = _memory(frozen_now, content="only one entry")
        llm_call = make_spy_llm(response="should never be used")
        merged = merge_group([memory], llm_call=llm_call)
        assert llm_call.call_count == 0
        assert merged.content == "only one entry"

    def test_no_judge_call_skips_validation_and_trusts_the_llm(
        self, frozen_now, make_spy_llm, monkeypatch
    ):
        monkeypatch.setattr(config, "MERGE_LLM_ENABLED", True)
        a = _memory(frozen_now, content="fact one", offset_hours=0)
        b = _memory(frozen_now, content="fact two", offset_hours=1)
        llm_call = make_spy_llm(response="synthesized text")
        merged = merge_group([a, b], llm_call=llm_call, judge_call=None)
        assert merged.content == "synthesized text"


# --- dedupe_and_merge: the public, top-level function -----------------------------


class TestDedupeAndMerge:
    def test_empty_input_returns_empty_list(self, fake_embedder):
        assert dedupe_and_merge([], embedder=fake_embedder) == []

    def test_use_llm_false_never_touches_llm_call(self, frozen_now, fake_embedder, make_spy_llm):
        a = _memory(frozen_now, content="This repo uses pytest fixtures for tests.", offset_hours=0)
        b = _memory(
            frozen_now, content="This repo uses pytest fixtures for all tests.", offset_hours=1
        )
        llm_call = make_spy_llm(response="should never be used")
        result = dedupe_and_merge([a, b], embedder=fake_embedder, llm_call=llm_call, use_llm=False)
        assert llm_call.call_count == 0
        assert len(result) == 1  # still merges — deterministically

    def test_conflicting_memories_below_threshold_both_survive(self, frozen_now, fake_embedder):
        a = _memory(
            frozen_now,
            content="The user asked to always use tabs for indentation in this project.",
            offset_hours=0,
        )
        b = _memory(
            frozen_now,
            content=(
                "Contradicting an earlier note, the team later switched the whole codebase "
                "over to spaces-only formatting and asked that be followed everywhere going forward."
            ),
            offset_hours=336,
        )
        result = dedupe_and_merge([a, b], embedder=fake_embedder, use_llm=False)
        assert len(result) == 2
        contents = {memory.content for memory in result}
        assert a.content in contents and b.content in contents

    def test_near_duplicates_collapse_to_one(self, frozen_now, fake_embedder):
        contents = [
            "This repo uses pytest fixtures, not unittest.TestCase, for tests.",
            "This repo uses pytest fixtures, not unittest.TestCase, for all tests.",
            "This repo uses pytest fixtures, not unittest.TestCase, for every test.",
        ]
        memories = [_memory(frozen_now, content=c, offset_hours=i) for i, c in enumerate(contents)]
        result = dedupe_and_merge(memories, embedder=fake_embedder, use_llm=False)
        assert len(result) == 1

    def test_default_threshold_comes_from_config(self, frozen_now, fake_embedder, monkeypatch):
        monkeypatch.setattr(config, "MERGE_SIMILARITY_THRESHOLD", 0.0)
        a = _memory(frozen_now, content="Deployed the staging server.", offset_hours=0)
        b = _memory(frozen_now, content="Wrote the onboarding guide.", offset_hours=1)
        result = dedupe_and_merge([a, b], embedder=fake_embedder, use_llm=False)
        assert len(result) == 1  # threshold of 0.0 merges even dissimilar content

    def test_explicit_threshold_overrides_config(self, frozen_now, fake_embedder):
        a = _memory(frozen_now, content="Deployed the staging server.", offset_hours=0)
        b = _memory(frozen_now, content="Wrote the onboarding guide.", offset_hours=1)
        result = dedupe_and_merge([a, b], embedder=fake_embedder, threshold=0.0, use_llm=False)
        assert len(result) == 1
