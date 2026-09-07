import pytest
from datetime import datetime, timedelta, timezone

from memora_mini.memory.recall import recall, recency_decay, strength
from memora_mini.store.protocol import SearchItem

NS = ("memora", "test", "episodic")


def _put(store, key, text, **extra):
    value = {"text": text, "active": True, "hit_count": 0, "last_hit_at": ""}
    value.update(extra)
    store.put(NS, key, value)


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_recency_decay_floors_out():
    assert recency_decay(_iso(0)) == pytest.approx(1.0)
    assert recency_decay(_iso(10000)) == 0.5  # RECENCY_FLOOR
    assert recency_decay("") == 0.5
    assert recency_decay("not-a-date") == 0.5


def test_strength_rewards_hits():
    fresh = SearchItem(NS, "a", {"hit_count": 0, "last_hit_at": _iso(0)}, score=0.5)
    used = SearchItem(NS, "b", {"hit_count": 20, "last_hit_at": _iso(0)}, score=0.5)
    assert strength(used) > strength(fresh)


def test_rerank_puts_low_similarity_high_hit_item_above_high_similarity_stale_one(store):
    # 'a' matches the query better but was last used long ago and never re-hit.
    _put(store, "stale", "insulin regulates blood glucose levels", hit_count=0, last_hit_at=_iso(400))
    _put(store, "hot", "glucose metabolism in the liver", hit_count=200, last_hit_at=_iso(0))

    raw = store.search(NS, query="how does insulin regulate blood glucose", limit=10)
    raw_order = [h.key for h in sorted(raw, key=lambda h: h.score, reverse=True)]
    assert raw_order[0] == "stale", "fixture is wrong: raw similarity should favour 'stale'"

    ranked = recall(store, NS, "how does insulin regulate blood glucose", limit=2, bump=False)
    assert [h.key for h in ranked][0] == "hot"


def test_recall_filters_inactive_by_default(store):
    _put(store, "old", "the capital of France is Paris", active=False)
    _put(store, "new", "the capital of France is Paris", active=True)
    keys = [h.key for h in recall(store, NS, "capital of France", limit=5, bump=False)]
    assert keys == ["new"]


def test_recall_bumps_hit_count_and_timestamp(store):
    _put(store, "a", "photosynthesis converts light to sugar")
    recall(store, NS, "how does photosynthesis work", limit=1)
    value = store.get(NS, "a").value
    assert value["hit_count"] == 1
    assert value["last_hit_at"] != ""
    recall(store, NS, "how does photosynthesis work", limit=1)
    assert store.get(NS, "a").value["hit_count"] == 2


def test_recall_honours_extra_filter(store):
    _put(store, "a", "vitamin D and bone density", track="learned_qa")
    _put(store, "b", "vitamin D and bone density", track="documents")
    keys = [h.key for h in recall(store, NS, "vitamin D", limit=5, filter={"track": "learned_qa"}, bump=False)]
    assert keys == ["a"]


def test_recall_on_empty_namespace_returns_nothing(store):
    assert recall(store, NS, "anything at all", limit=3) == []


def test_recall_overfetches_before_reranking(store, monkeypatch):
    """Re-ranking only works if the candidate pool is wider than the answer."""
    from memora_mini.memory import recall as recall_mod

    seen = {}
    real_search = store.search

    def spy(namespace, **kwargs):
        seen.update(kwargs)
        return real_search(namespace, **kwargs)

    monkeypatch.setattr(store, "search", spy)
    _put(store, "a", "insulin regulates blood glucose")
    recall(store, NS, "insulin", limit=4, bump=False)
    assert seen["limit"] == 4 * recall_mod.OVERFETCH_FACTOR


def test_similarity_floor_drops_weak_hits(store, monkeypatch):
    from memora_mini.memory import recall as recall_mod

    _put(store, "a", "insulin regulates blood glucose")
    assert recall(store, NS, "insulin and glucose", limit=5, bump=False)

    monkeypatch.setattr(recall_mod, "SIMILARITY_FLOOR", 0.99)
    assert recall(store, NS, "the Treaty of Westphalia", limit=5, bump=False) == []


def test_the_similarity_floor_does_not_apply_to_metadata_only_recall(store):
    """With no query every score is 0.0 — flooring there would return nothing."""
    _put(store, "a", "insulin regulates blood glucose")
    keys = [h.key for h in recall(store, NS, None, limit=5, bump=False)]
    assert keys == ["a"]


def test_recall_truncates_to_limit(store):
    for index in range(6):
        _put(store, f"k{index}", f"vitamin D and bone density, note number {index}")
    assert len(recall(store, NS, "vitamin D and bones", limit=2, bump=False)) == 2


def test_active_only_false_includes_superseded_records(store):
    _put(store, "old", "the capital of France is Lyon", active=False, superseded_by="new")
    _put(store, "new", "the capital of France is Paris", active=True)
    keys = {h.key for h in recall(store, NS, "capital of France", limit=5,
                                  active_only=False, bump=False)}
    assert keys == {"old", "new"}


def test_recall_returns_nothing_when_every_record_is_retired(store):
    _put(store, "old", "the capital of France is Lyon", active=False)
    assert recall(store, NS, "capital of France", limit=5, bump=False) == []


def test_bump_false_leaves_the_counters_untouched(store):
    _put(store, "a", "photosynthesis converts light to sugar")
    recall(store, NS, "how does photosynthesis work", limit=1, bump=False)
    value = store.get(NS, "a").value
    assert value["hit_count"] == 0 and value["last_hit_at"] == ""


def test_recall_bumps_only_what_it_returned(store):
    _put(store, "returned", "insulin regulates blood glucose")
    _put(store, "left-behind", "insulin is produced in the pancreas")
    ranked = recall(store, NS, "what does insulin do to blood glucose", limit=1)
    assert len(ranked) == 1
    assert store.get(NS, ranked[0].key).value["hit_count"] == 1
    other = "returned" if ranked[0].key == "left-behind" else "left-behind"
    assert store.get(NS, other).value["hit_count"] == 0


def test_a_bump_does_not_disturb_the_rest_of_the_record(store):
    _put(store, "a", "vitamin D and bone density", track="learned_qa", source_paths=["a.md"],
         confidence=0.7)
    recall(store, NS, "vitamin D", limit=1)
    value = store.get(NS, "a").value
    assert value["text"] == "vitamin D and bone density"
    assert value["track"] == "learned_qa"
    assert value["source_paths"] == ["a.md"]
    assert value["confidence"] == 0.7


def test_recall_combines_the_active_filter_with_a_caller_filter(store):
    _put(store, "a", "vitamin D and bone density", track="learned_qa", active=True)
    _put(store, "b", "vitamin D and bone density", track="learned_qa", active=False)
    _put(store, "c", "vitamin D and bone density", track="documents", active=True)
    keys = [h.key for h in recall(store, NS, "vitamin D", limit=5,
                                  filter={"track": "learned_qa"}, bump=False)]
    assert keys == ["a"]


def test_recall_never_mutates_a_record_it_filtered_out(store):
    _put(store, "hidden", "vitamin D and bone density", active=False)
    recall(store, NS, "vitamin D", limit=5)
    assert store.get(NS, "hidden").value["hit_count"] == 0


def test_strength_is_pure_similarity_for_a_fresh_unhit_memory(store):
    from datetime import datetime as dt

    item = SearchItem(NS, "a", {"hit_count": 0, "last_hit_at": _iso(0)}, score=0.6)
    assert strength(item, dt.now(timezone.utc)) == pytest.approx(0.6)


def test_recency_never_drags_a_memory_below_the_floor():
    stale = SearchItem(NS, "a", {"hit_count": 0, "last_hit_at": _iso(3650)}, score=0.8)
    assert strength(stale) == pytest.approx(0.8 * 0.5)
