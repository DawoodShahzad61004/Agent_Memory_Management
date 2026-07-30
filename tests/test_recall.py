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
