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


# --- what each action actually writes ---------------------------------------

def test_insert_writes_the_candidate_verbatim_under_a_fresh_key(store):
    candidate = _candidate("a brand new lesson", track="learned_qa")
    op = plan(NS, candidate, None, "UNRELATED")
    apply_ops(store, [op], dry_run=False)
    value = store.get(NS, op.new_key).value
    assert value["text"] == "a brand new lesson"
    assert value["track"] == "learned_qa"
    assert value["active"] is True and value["superseded_by"] is None


def test_two_inserts_never_collide_on_a_key(store):
    ops = [plan(NS, _candidate(f"distinct lesson {i}"), None, "UNRELATED") for i in range(5)]
    assert len({op.new_key for op in ops}) == 5
    apply_ops(store, ops, dry_run=False)
    assert store.count(NS) == 5


def test_bump_is_repeatable_and_stamps_last_hit_at(store):
    neighbour = _existing(store)
    for expected in (1, 2, 3):
        current = SearchItem(NS, "old", store.get(NS, "old").value, score=0.9)
        apply_ops(store, [plan(NS, _candidate(), current, "DUPLICATE")], dry_run=False)
        value = store.get(NS, "old").value
        assert value["hit_count"] == expected
        assert value["last_hit_at"] != ""
    assert store.count(NS) == 1  # a duplicate never adds a record
    assert neighbour.value["text"] == store.get(NS, "old").value["text"]  # text untouched


def test_supersede_writes_the_new_record_and_retires_the_old_one_in_place(store):
    _existing(store)
    op = plan(NS, _candidate(), SearchItem(NS, "old", store.get(NS, "old").value, score=0.9),
              "CONTRADICTS")
    apply_ops(store, [op], dry_run=False)

    new = store.get(NS, op.new_key).value
    old = store.get(NS, "old").value
    assert new["text"] == "vitamin D does not prevent fractures"
    assert new["active"] is True and new["superseded_by"] is None
    assert old["text"] == "vitamin D prevents fractures"  # the old record is kept, not rewritten
    assert old["active"] is False and old["superseded_by"] == op.new_key


def test_a_supersession_chain_still_leaves_exactly_one_active_record(store):
    _existing(store)
    keys = []
    for text in ("vitamin D helps only with calcium", "vitamin D helps nobody"):
        target = store.search(NS, filter={"active": True}, limit=5)[0]
        op = plan(NS, _candidate(text), target, "CONTRADICTS")
        apply_ops(store, [op], dry_run=False)
        keys.append(op.new_key)

    active = store.search(NS, filter={"active": True}, limit=50)
    assert [item.key for item in active] == [keys[-1]]
    assert store.count(NS) == 3  # every generation is still on disk
    assert store.get(NS, keys[0]).value["superseded_by"] == keys[-1]


def test_refines_merge_appends_the_older_text_when_it_is_not_contained(store):
    neighbour = _existing(store, text="vitamin D prevents fractures")
    op = plan(NS, _candidate("calcium co-supplementation is what matters"), neighbour, "REFINES")
    assert op.new_value["text"] == ("calcium co-supplementation is what matters\n"
                                   "vitamin D prevents fractures")


def test_refines_merge_drops_the_older_text_when_it_is_already_contained(store):
    neighbour = _existing(store, text="vitamin D prevents fractures")
    op = plan(NS, _candidate("vitamin D prevents fractures in adults over 70"), neighbour, "REFINES")
    assert op.new_value["text"] == "vitamin D prevents fractures in adults over 70"


def test_refines_merge_carries_the_neighbours_usage_forward(store):
    neighbour = _existing(store, hit_count=4, contradiction_strikes=1)
    op = plan(NS, _candidate(), neighbour, "REFINES")
    assert op.new_value["hit_count"] == 4  # the refined record inherits the earned strength
    apply_ops(store, [op], dry_run=False)
    assert store.get(NS, op.new_key).value["hit_count"] == 4


def test_refines_merge_deduplicates_the_unioned_lists(store):
    neighbour = _existing(store, source_paths=["a.md", "b.md"])
    op = plan(NS, _candidate(source_paths=["b.md", "c.md"]), neighbour, "REFINES")
    assert op.new_value["source_paths"] == ["a.md", "b.md", "c.md"]


def test_skip_records_a_strike_and_writes_nothing_else(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "PROTECTED_HIT_COUNT", 5)
    _existing(store, hit_count=50)
    before = store.get(NS, "old").value
    op = plan(NS, _candidate(), SearchItem(NS, "old", before, score=0.9), "CONTRADICTS")
    apply_ops(store, [op], dry_run=False)

    after = store.get(NS, "old").value
    assert store.count(NS) == 1
    assert after["contradiction_strikes"] == 1
    assert after["hit_count"] == 50 and after["text"] == before["text"]
    assert after["active"] is True


# --- batch behaviour and guards ---------------------------------------------

def test_an_empty_batch_is_a_clean_noop(store):
    summary = apply_ops(store, [], dry_run=False)
    assert summary == {"planned": 0, "applied": 0, "dropped": 0, "dry_run": False, "by_action": {}}
    assert store.count(NS) == 0


def test_the_summary_tallies_every_action(store):
    _existing(store, key="dup", text="already known fact")
    _existing(store, key="con", text="contradicted fact")
    ops = [
        plan(NS, _candidate("something new"), None, "UNRELATED"),
        plan(NS, _candidate(), SearchItem(NS, "dup", store.get(NS, "dup").value, score=0.9),
             "DUPLICATE"),
        plan(NS, _candidate(), SearchItem(NS, "con", store.get(NS, "con").value, score=0.9),
             "CONTRADICTS"),
    ]
    summary = apply_ops(store, ops, dry_run=False)
    assert summary["planned"] == 3 and summary["applied"] == 3 and summary["dropped"] == 0
    assert summary["by_action"] == {"insert": 1, "bump": 1, "supersede": 1}


def test_a_dropped_op_is_neither_applied_nor_audited(store, audit_to_tmp):
    ghost = SearchItem(NS, "not-in-store", {"hit_count": 0}, score=0.9)
    good = plan(NS, _candidate("a genuinely new lesson"), None, "UNRELATED")
    summary = apply_ops(store, [plan(NS, _candidate(), ghost, "DUPLICATE"), good], dry_run=False)

    assert summary["applied"] == 1 and summary["dropped"] == 1
    lines = audit_to_tmp.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["new_key"] == good.new_key


def test_a_target_deleted_between_plan_and_apply_is_dropped(store):
    neighbour = _existing(store)
    op = plan(NS, _candidate(), neighbour, "CONTRADICTS")
    store.delete(NS, "old")  # operator cleanup lands in the gap
    summary = apply_ops(store, [op], dry_run=False)
    assert summary["applied"] == 0 and summary["dropped"] == 1
    assert store.count(NS) == 0  # the replacement is not written half-way


def test_an_insert_is_never_dropped_for_having_no_target(store):
    op = plan(NS, _candidate(), None, "UNRELATED")
    assert op.target_key is None
    assert apply_ops(store, [op], dry_run=False)["dropped"] == 0


def test_the_cap_keeps_the_first_ops_and_drops_the_tail(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "MAX_OPS_PER_RUN", 2)
    ops = [plan(NS, _candidate(f"distinct fact number {i}"), None, "UNRELATED") for i in range(5)]
    apply_ops(store, ops, dry_run=False)
    assert {op.new_key for op in ops[:2]} == {item.key for item in store.search(NS, limit=10)}


def test_no_action_ever_reaches_store_delete(store, monkeypatch):
    """The lifecycle invariant, enforced at the store boundary."""
    _existing(store)
    monkeypatch.setattr(store, "delete",
                        lambda *a, **k: pytest.fail("apply_ops called store.delete"))
    for verdict in ("DUPLICATE", "REFINES", "CONTRADICTS", "UNRELATED"):
        neighbour = store.search(NS, filter={"active": True}, limit=1)
        target = neighbour[0] if neighbour else None
        apply_ops(store, [plan(NS, _candidate(f"a {verdict} candidate"), target, verdict)],
                  dry_run=False)
    assert store.count(NS) >= 1


def test_dry_run_leaves_every_counter_untouched(store, monkeypatch):
    monkeypatch.setattr(apply_mod, "PROTECTED_HIT_COUNT", 5)
    _existing(store, hit_count=50)
    before = store.get(NS, "old").value
    target = SearchItem(NS, "old", before, score=0.9)
    ops = [plan(NS, _candidate(), target, "DUPLICATE"), plan(NS, _candidate(), target, "CONTRADICTS")]
    summary = apply_ops(store, ops, dry_run=True)

    after = store.get(NS, "old").value
    assert summary["applied"] == 0 and summary["by_action"] == {"bump": 1, "skip": 1}
    assert after["hit_count"] == before["hit_count"]
    assert after["contradiction_strikes"] == before["contradiction_strikes"]
    assert store.count(NS) == 1
