"""Multi-scenario tests for mem_manage.consolidate: passive-decay refresh
and rerank/prune.
"""
from __future__ import annotations

from datetime import timedelta

from mem_manage import config
from mem_manage.consolidate import refresh_decay, rerank_and_prune
from mem_manage.memory import DurableMemory


def _memory(
    frozen_now,
    *,
    importance,
    offset_hours=0,
    last_accessed_offset_hours=None,
    memory_id="m",
):
    created = frozen_now + timedelta(hours=offset_hours)
    last_accessed = (
        created
        if last_accessed_offset_hours is None
        else frozen_now + timedelta(hours=last_accessed_offset_hours)
    )
    return DurableMemory(
        id=memory_id,
        content=f"content {memory_id}",
        tag="t",
        created_at=created,
        last_accessed_at=last_accessed,
        importance=importance,
        provenance="inferred",
        merged_from=[memory_id],
    )


class TestRefreshDecay:
    def test_applies_passive_decay_using_each_memorys_own_clock(self, frozen_now):
        never_touched = _memory(
            frozen_now, importance=0.8, offset_hours=-24 * 400, memory_id="old"
        )
        recently_touched = _memory(
            frozen_now,
            importance=0.8,
            offset_hours=-24 * 400,
            last_accessed_offset_hours=-1,
            memory_id="fresh",
        )
        result = {
            m.id: m for m in refresh_decay([never_touched, recently_touched], now=frozen_now)
        }
        assert result["fresh"].importance > result["old"].importance

    def test_empty_input_returns_empty_list(self, frozen_now):
        assert refresh_decay([], now=frozen_now) == []

    def test_other_fields_are_unchanged(self, frozen_now):
        memory = _memory(frozen_now, importance=0.5, memory_id="x")
        decayed = refresh_decay([memory], now=frozen_now)[0]
        assert decayed.id == memory.id
        assert decayed.content == memory.content
        assert decayed.created_at == memory.created_at
        assert decayed.tag == memory.tag


class TestRerankAndPrune:
    def test_exact_prune_count_at_n_ten(self, frozen_now):
        memories = [_memory(frozen_now, importance=i / 10, memory_id=str(i)) for i in range(10)]
        result = rerank_and_prune(memories, prune_fraction=0.20)
        assert len(result) == 8  # 10 - floor(10 * 0.2)

    def test_prunes_the_lowest_importance_entries(self, frozen_now):
        memories = [_memory(frozen_now, importance=i / 10, memory_id=str(i)) for i in range(10)]
        result = rerank_and_prune(memories, prune_fraction=0.20)
        survivors = {m.id for m in result}
        assert survivors == {"2", "3", "4", "5", "6", "7", "8", "9"}

    def test_result_is_sorted_descending_by_importance(self, frozen_now):
        memories = [
            _memory(frozen_now, importance=0.3, memory_id="a"),
            _memory(frozen_now, importance=0.9, memory_id="b"),
            _memory(frozen_now, importance=0.6, memory_id="c"),
        ]
        result = rerank_and_prune(memories, prune_fraction=0.0)
        assert [m.importance for m in result] == [0.9, 0.6, 0.3]

    def test_small_n_prunes_nothing(self, frozen_now):
        for n in range(1, 5):
            memories = [
                _memory(frozen_now, importance=i / 10, memory_id=str(i)) for i in range(n)
            ]
            result = rerank_and_prune(memories, prune_fraction=0.20)
            assert len(result) == n

    def test_empty_input_returns_empty_list(self, frozen_now):
        assert rerank_and_prune([], prune_fraction=0.20) == []

    def test_ties_break_in_stable_input_order(self, frozen_now):
        memories = [
            _memory(frozen_now, importance=0.5, memory_id="first"),
            _memory(frozen_now, importance=0.5, memory_id="second"),
            _memory(frozen_now, importance=0.5, memory_id="third"),
        ]
        result = rerank_and_prune(memories, prune_fraction=0.0)
        assert [m.id for m in result] == ["first", "second", "third"]

    def test_ties_at_the_boundary_prune_from_the_end_of_stable_order(self, frozen_now):
        memories = [_memory(frozen_now, importance=0.5, memory_id=str(i)) for i in range(10)]
        result = rerank_and_prune(memories, prune_fraction=0.20)
        assert [m.id for m in result] == [str(i) for i in range(8)]

    def test_default_prune_fraction_comes_from_config_read_live(self, frozen_now, monkeypatch):
        monkeypatch.setattr(config, "PRUNE_BOTTOM_PERCENT", 0.5)
        memories = [_memory(frozen_now, importance=i / 10, memory_id=str(i)) for i in range(10)]
        result = rerank_and_prune(memories)
        assert len(result) == 5
