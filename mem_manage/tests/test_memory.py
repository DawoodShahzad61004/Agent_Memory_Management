"""Tests for mem_manage.memory: DurableMemory field mapping and id stability."""
from __future__ import annotations

from datetime import timedelta

import pytest

from mem_manage.importance import EpisodicRecord, build_entity_index, composite_importance
from mem_manage.memory import build_durable_memories, content_id


class TestBuildDurableMemories:
    def test_one_memory_per_record(self, frozen_now):
        records = [
            EpisodicRecord(frozen_now, "a", "content a"),
            EpisodicRecord(frozen_now, "b", "content b"),
        ]
        memories = build_durable_memories(records, now=frozen_now)
        assert len(memories) == 2

    def test_field_mapping_from_record(self, frozen_now):
        record = EpisodicRecord(frozen_now, "sometag", "some content", provenance="explicit")
        memory = build_durable_memories([record], now=frozen_now)[0]
        assert memory.content == "some content"
        assert memory.tag == "sometag"
        assert memory.created_at == frozen_now
        assert memory.last_accessed_at == frozen_now
        assert memory.provenance == "explicit"
        assert memory.merged_from == [memory.id]

    def test_importance_matches_independently_computed_composite_importance(self, frozen_now):
        records = [
            EpisodicRecord(frozen_now, "a", "content a"),
            EpisodicRecord(frozen_now, "b", "content b"),
        ]
        memories = build_durable_memories(records, now=frozen_now)
        entity_index = build_entity_index(records)
        expected = composite_importance(records[0], records, entity_index, now=frozen_now)
        assert memories[0].importance == pytest.approx(expected)

    def test_empty_input_returns_empty_list(self, frozen_now):
        assert build_durable_memories([], now=frozen_now) == []

    def test_scoring_sees_the_whole_corpus_not_just_earlier_records(self, frozen_now):
        # Regression guard: frequency/surprise/entity-salience must be scored
        # against the full input list, so processing order doesn't change
        # a record's importance.
        records = [
            EpisodicRecord(frozen_now, "dup", "the same thing said twice"),
            EpisodicRecord(frozen_now, "dup", "the same thing said twice"),
        ]
        memories = build_durable_memories(records, now=frozen_now)
        assert memories[0].importance == pytest.approx(memories[1].importance)


class TestContentId:
    def test_same_text_produces_same_id(self):
        assert content_id("hello world") == content_id("hello world")

    def test_different_text_produces_different_id(self):
        assert content_id("hello world") != content_id("goodbye world")

    def test_ids_are_stable_strings(self):
        result = content_id("anything")
        assert isinstance(result, str) and len(result) > 0

    def test_record_ids_differ_by_timestamp_even_with_identical_text(self, frozen_now):
        a = EpisodicRecord(frozen_now, "t", "same content")
        b = EpisodicRecord(frozen_now + timedelta(hours=1), "t", "same content")
        memory_a, memory_b = build_durable_memories([a, b], now=frozen_now)
        assert memory_a.id != memory_b.id
