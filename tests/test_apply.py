import json

import pytest

from memora_mini.memory import apply as apply_mod
from memora_mini.memory.apply import MemoryOp, apply_ops, plan
from memora_mini.store.protocol import SearchItem

NS = ("memora", "test", "episodic")


@pytest.fixture(autouse=True)
def audit_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(apply_mod, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
    return tmp_path / "audit.jsonl"


def _existing(store, key="old", text="vitamin D prevents fractures", **extra):
    value = {"text": text, "active": True, "hit_count": 0, "last_hit_at": "",
             "superseded_by": None, "contradiction_strikes": 0, "confidence": 0.5}
    value.update(extra)
    store.put(NS, key, value)
    return SearchItem(NS, key, store.get(NS, key).value, score=0.9)


def _candidate(text="vitamin D does not prevent fractures", **extra):
    value = {"text": text, "active": True, "hit_count": 0, "last_hit_at": "",
             "superseded_by": None, "contradiction_strikes": 0, "confidence": 0.9}
    value.update(extra)
    return value


def test_unrelated_inserts(store):
    op = plan(NS, _candidate(), None, "UNRELATED")
    assert op.action == "insert"
    apply_ops(store, [op], dry_run=False)
    assert store.count(NS) == 1


def test_duplicate_bumps_without_inserting(store):
    neighbour = _existing(store)
    op = plan(NS, _candidate(), neighbour, "DUPLICATE")
    assert op.action == "bump"
    apply_ops(store, [op], dry_run=False)
    assert store.count(NS) == 1
    assert store.get(NS, "old").value["hit_count"] == 1


def test_supersede_leaves_exactly_one_active_record(store):
    neighbour = _existing(store)
    op = plan(NS, _candidate(), neighbour, "CONTRADICTS")
    assert op.action == "supersede"
    apply_ops(store, [op], dry_run=False)

    assert store.count(NS) == 2  # nothing is deleted
    old = store.get(NS, "old").value
    assert old["active"] is False
    assert old["superseded_by"] == op.new_key
    active = store.search(NS, filter={"active": True}, limit=10)
    assert len(active) == 1
    assert active[0].key == op.new_key


def test_refines_merges_lists_and_keeps_max_confidence(store):
    neighbour = _existing(store, source_paths=["a.md"], confidence=0.4)
    op = plan(NS, _candidate(source_paths=["b.md"], confidence=0.9), neighbour, "REFINES")
    assert op.action == "supersede"
    assert sorted(op.new_value["source_paths"]) == ["a.md", "b.md"]
    assert op.new_value["confidence"] == 0.9
    assert op.new_value["active"] is True and op.new_value["superseded_by"] is None


def test_contradicts_audit_entry_keeps_both_versions(store, audit_to_tmp):
    neighbour = _existing(store)
    op = plan(NS, _candidate(), neighbour, "CONTRADICTS")
    apply_ops(store, [op], dry_run=False)
    record = json.loads(audit_to_tmp.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert record["verdict"] == "CONTRADICTS"
    assert record["old_text"] == "vitamin D prevents fractures"
    assert record["new_text"] == "vitamin D does not prevent fractures"


def test_dry_run_writes_nothing_but_still_audits(store, audit_to_tmp):
    neighbour = _existing(store)
    ops = [plan(NS, _candidate(), neighbour, "CONTRADICTS"), plan(NS, _candidate("new fact"), None, "UNRELATED")]
    summary = apply_ops(store, ops, dry_run=True)

    assert summary["dry_run"] is True and summary["applied"] == 0
    assert store.count(NS) == 1
    assert store.get(NS, "old").value["active"] is True
    assert len(audit_to_tmp.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_dry_run_default_comes_from_config(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "DRY_RUN_MEMORY_OPS", True)
    apply_ops(store, [plan(NS, _candidate(), None, "UNRELATED")])
    assert store.count(NS) == 0


def test_max_ops_per_run_honoured(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "MAX_OPS_PER_RUN", 3)
    ops = [plan(NS, _candidate(f"distinct fact number {i}"), None, "UNRELATED") for i in range(10)]
    summary = apply_ops(store, ops, dry_run=False)
    assert summary["applied"] == 3
    assert summary["dropped"] == 7
    assert store.count(NS) == 3


def test_op_referencing_a_missing_key_is_dropped(store):
    ghost = SearchItem(NS, "not-in-store", {"hit_count": 0}, score=0.9)
    summary = apply_ops(store, [plan(NS, _candidate(), ghost, "CONTRADICTS")], dry_run=False)
    assert summary["applied"] == 0 and summary["dropped"] == 1
    assert store.count(NS) == 0


def test_protected_entry_survives_a_single_contradiction(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "PROTECTED_HIT_COUNT", 5)
    neighbour = _existing(store, hit_count=50)
    op = plan(NS, _candidate(), neighbour, "CONTRADICTS")
    assert op.action == "skip"
    apply_ops(store, [op], dry_run=False)
    assert store.get(NS, "old").value["active"] is True
    assert store.get(NS, "old").value["contradiction_strikes"] == 1


def test_protected_entry_is_superseded_on_the_second_strike(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "PROTECTED_HIT_COUNT", 5)
    neighbour = _existing(store, hit_count=50, contradiction_strikes=1)
    op = plan(NS, _candidate(), neighbour, "CONTRADICTS")
    assert op.action == "supersede"
    apply_ops(store, [op], dry_run=False)
    assert store.get(NS, "old").value["active"] is False


def test_protected_entry_is_never_destroyed_by_a_refinement(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "PROTECTED_HIT_COUNT", 5)
    neighbour = _existing(store, hit_count=50)
    op = plan(NS, _candidate(), neighbour, "REFINES")
    assert op.action == "insert"


def test_no_op_ever_deletes():
    neighbour = SearchItem(NS, "old", {"hit_count": 0}, score=0.9)
    actions = {plan(NS, _candidate(), neighbour, v).action
               for v in ("DUPLICATE", "REFINES", "CONTRADICTS", "UNRELATED")}
    assert "delete" not in actions
    assert actions <= {"bump", "insert", "supersede", "skip"}


def test_memory_op_is_json_serialisable():
    op = MemoryOp("insert", NS, "UNRELATED", new_key="k", new_value={"text": "t"})
    assert json.loads(json.dumps(op.as_json()))["namespace"] == "memora/test/episodic"
