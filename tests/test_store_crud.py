"""Exhaustive CRUD over the store layer.

test_store.py covers the wiring — cosine pinning, the Protocol shape, the
happy-path encode/decode. This file covers the lifecycle each verb actually
has to survive: what it does to neighbouring records, to the *other*
namespaces, and to keys that are not there at all.
"""
from datetime import datetime

import pytest

from memora_mini.store.chroma_store import _NONE, TEXT_KEY

NS = ("memora", "test", "episodic")
OTHER = ("memora", "test", "semantic")


def _val(text, **extra):
    base = {"text": text, "active": True, "hit_count": 0, "last_hit_at": "",
            "superseded_by": None, "contradiction_strikes": 0}
    base.update(extra)
    return base


# --- create -----------------------------------------------------------------

def test_put_rejects_every_shape_of_missing_text(store):
    for value in ({"active": True}, {"text": "", "active": True}, {"text": None, "active": True}):
        with pytest.raises(ValueError, match=TEXT_KEY):
            store.put(NS, "k", value)
    assert store.count(NS) == 0


def test_put_requires_at_least_one_field_besides_text(store):
    # `text` becomes the document, never metadata, so a text-only value leaves
    # Chroma with an empty metadata dict and it refuses. Every real memory goes
    # through MemoryBase.to_value(), which always carries the managed fields.
    with pytest.raises(ValueError):
        store.put(NS, "k", {"text": "nothing but text"})


def test_text_is_stored_as_the_document_not_as_metadata(store):
    store.put(NS, "k1", _val("embedded body text"))
    raw = store.collection(NS).get(ids=["k1"])
    assert TEXT_KEY not in raw["metadatas"][0]
    assert raw["documents"][0] == "embedded body text"
    assert raw["metadatas"][0]["superseded_by"] == _NONE  # None survives as a sentinel
    assert store.get(NS, "k1").value["text"] == "embedded body text"


def test_put_roundtrips_every_scalar_type(store):
    store.put(NS, "k1", _val("scalars", count=7, confidence=0.25, approved=False, note="hi"))
    value = store.get(NS, "k1").value
    assert value["count"] == 7 and isinstance(value["count"], int)
    assert value["confidence"] == 0.25
    assert value["approved"] is False
    assert value["note"] == "hi"


def test_put_roundtrips_nested_containers_and_none(store):
    store.put(NS, "k1", _val("containers", nested={"a": [1, 2]}, tup=("x", "y"), gap=None))
    value = store.get(NS, "k1").value
    assert value["nested"] == {"a": [1, 2]}
    assert value["tup"] == ["x", "y"]  # tuples come back as lists
    assert value["gap"] is None


def test_an_unsupported_value_type_is_coerced_to_its_string_form(store):
    store.put(NS, "k1", _val("has a datetime", when=datetime(2020, 1, 1)))
    assert store.get(NS, "k1").value["when"] == "2020-01-01 00:00:00"


def test_put_roundtrips_unicode_in_text_and_metadata(store):
    store.put(NS, "k1", _val("β-blockers réduisent la tension 血压", subject="β-blocker"))
    value = store.get(NS, "k1").value
    assert value["text"] == "β-blockers réduisent la tension 血压"
    assert value["subject"] == "β-blocker"


def test_put_is_namespace_scoped(store):
    store.put(NS, "same-key", _val("the episodic one"))
    store.put(OTHER, "same-key", _val("the semantic one"))
    assert store.get(NS, "same-key").value["text"] == "the episodic one"
    assert store.get(OTHER, "same-key").value["text"] == "the semantic one"
    assert store.count(NS) == 1 and store.count(OTHER) == 1


def test_reput_merges_metadata_rather_than_replacing_it(store):
    """An upsert is a *merge*: fields absent from the new value survive.

    This is why apply.py writes a supersession to a fresh key instead of
    overwriting the old one — a re-put could never clear a stale field.
    """
    store.put(NS, "k1", _val("first version", track="learned_qa", confidence=0.4))
    store.put(NS, "k1", {"text": "second version", "confidence": 0.9})
    value = store.get(NS, "k1").value
    assert value["text"] == "second version"
    assert value["confidence"] == 0.9
    assert value["track"] == "learned_qa"  # not cleared by the second put
    assert store.count(NS) == 1


def test_reput_replaces_the_embedded_document(store):
    store.put(NS, "k1", _val("insulin regulates blood glucose"))
    store.put(NS, "k1", _val("photosynthesis converts light into sugar"))
    hits = store.search(NS, query="how do plants use sunlight", limit=1)
    assert hits[0].key == "k1"
    assert hits[0].value["text"] == "photosynthesis converts light into sugar"


# --- read -------------------------------------------------------------------

def test_get_returns_none_for_a_missing_key_and_for_the_wrong_namespace(store):
    store.put(NS, "k1", _val("only in episodic"))
    assert store.get(NS, "nope") is None
    assert store.get(OTHER, "k1") is None


def test_reads_on_an_untouched_namespace_are_empty_not_errors(store):
    fresh = ("memora", "test", "never-written")
    assert store.get(fresh, "anything") is None
    assert store.search(fresh, query="anything", limit=5) == []
    assert store.search(fresh, limit=5) == []
    assert store.count(fresh) == 0


def test_search_honours_limit_on_both_code_paths(store):
    for index in range(6):
        store.put(NS, f"k{index}", _val(f"distinct memory number {index}"))
    assert len(store.search(NS, limit=3)) == 3
    assert len(store.search(NS, query="distinct memory", limit=3)) == 3


def test_search_without_a_query_scores_zero(store):
    store.put(NS, "k1", _val("no ranking without a query"))
    assert store.search(NS, limit=5)[0].score == 0.0


def test_search_scores_are_bounded_and_descending(store):
    store.put(NS, "exact", _val("insulin regulates blood glucose"))
    store.put(NS, "loose", _val("the Treaty of Westphalia ended the Thirty Years War"))
    hits = store.search(NS, query="insulin regulates blood glucose", limit=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(-1.0 <= s <= 1.0 for s in scores)
    assert hits[0].key == "exact" and hits[0].score > 0.9


def test_search_combines_two_metadata_conditions(store):
    """More than one condition has to go through Chroma's explicit $and."""
    store.put(NS, "a", _val("alpha", track="learned_qa", active=True))
    store.put(NS, "b", _val("alpha", track="learned_qa", active=False))
    store.put(NS, "c", _val("alpha", track="documents", active=True))
    keys = {h.key for h in store.search(NS, filter={"track": "learned_qa", "active": True}, limit=10)}
    assert keys == {"a"}
    keys = {h.key for h in store.search(NS, query="alpha",
                                        filter={"track": "learned_qa", "active": True}, limit=10)}
    assert keys == {"a"}


def test_search_passes_operator_filters_through(store):
    for key, hits in (("cold", 0), ("warm", 5), ("hot", 10)):
        store.put(NS, key, _val(f"memory {key}", hit_count=hits))
    keys = {h.key for h in store.search(NS, filter={"hit_count": {"$gt": 4}}, limit=10)}
    assert keys == {"warm", "hot"}


def test_a_filter_matching_nothing_returns_nothing(store):
    store.put(NS, "a", _val("alpha", active=True))
    assert store.search(NS, filter={"active": False}, limit=5) == []
    assert store.search(NS, query="alpha", filter={"active": False}, limit=5) == []


def test_count_is_per_namespace(store):
    store.put(NS, "a", _val("one"))
    store.put(NS, "b", _val("two"))
    store.put(OTHER, "a", _val("three"))
    assert store.count(NS) == 2 and store.count(OTHER) == 1


# --- update -----------------------------------------------------------------

def test_update_metadata_on_a_missing_key_is_a_silent_noop(store):
    store.update_metadata(NS, "never-existed", {"hit_count": 9})
    assert store.get(NS, "never-existed") is None
    assert store.count(NS) == 0


def test_update_metadata_merges_and_leaves_untouched_fields_alone(store):
    store.put(NS, "k1", _val("stable text", track="learned_qa", confidence=0.4))
    store.update_metadata(NS, "k1", {"hit_count": 3, "last_hit_at": "2026-01-01T00:00:00+00:00"})
    value = store.get(NS, "k1").value
    assert value["hit_count"] == 3
    assert value["last_hit_at"] == "2026-01-01T00:00:00+00:00"
    assert value["track"] == "learned_qa" and value["confidence"] == 0.4
    assert value["text"] == "stable text"


def test_update_metadata_preserves_list_fields_through_the_reencode(store):
    """The patch is merged into the decoded value and re-encoded wholesale, so
    a list field has to survive a decode/encode cycle it never asked for."""
    store.put(NS, "k1", _val("with lists", source_paths=["a.md", "b.md"], disambiguates=None))
    store.update_metadata(NS, "k1", {"hit_count": 1})
    value = store.get(NS, "k1").value
    assert value["source_paths"] == ["a.md", "b.md"]
    assert value["disambiguates"] is None


def test_update_metadata_can_write_none(store):
    store.put(NS, "k1", _val("supersession undone", superseded_by="other"))
    store.update_metadata(NS, "k1", {"superseded_by": None})
    assert store.get(NS, "k1").value["superseded_by"] is None


def test_update_metadata_changes_neither_the_document_nor_the_count(store):
    store.put(NS, "k1", _val("insulin regulates blood glucose"))
    store.update_metadata(NS, "k1", {"hit_count": 4})
    assert store.count(NS) == 1
    assert store.search(NS, query="insulin regulates blood glucose", limit=1)[0].score > 0.9


def test_update_metadata_touches_only_the_target_key(store):
    store.put(NS, "a", _val("first"))
    store.put(NS, "b", _val("second"))
    store.update_metadata(NS, "a", {"hit_count": 5})
    assert store.get(NS, "a").value["hit_count"] == 5
    assert store.get(NS, "b").value["hit_count"] == 0


def test_update_metadata_is_namespace_scoped(store):
    store.put(NS, "same-key", _val("episodic copy"))
    store.put(OTHER, "same-key", _val("semantic copy"))
    store.update_metadata(NS, "same-key", {"hit_count": 5})
    assert store.get(OTHER, "same-key").value["hit_count"] == 0


def test_repeated_updates_accumulate(store):
    store.put(NS, "k1", _val("bumped repeatedly"))
    for expected in (1, 2, 3):
        current = store.get(NS, "k1").value["hit_count"]
        store.update_metadata(NS, "k1", {"hit_count": current + 1})
        assert store.get(NS, "k1").value["hit_count"] == expected


# --- delete -----------------------------------------------------------------

def test_delete_of_a_missing_key_is_a_silent_noop(store):
    store.delete(NS, "never-existed")  # must not raise
    assert store.count(NS) == 0


def test_delete_is_idempotent(store):
    store.put(NS, "k1", _val("gone soon"))
    store.delete(NS, "k1")
    store.delete(NS, "k1")
    assert store.get(NS, "k1") is None
    assert store.count(NS) == 0


def test_delete_removes_only_the_target_key(store):
    store.put(NS, "a", _val("keep me"))
    store.put(NS, "b", _val("delete me"))
    store.delete(NS, "b")
    assert store.get(NS, "a").value["text"] == "keep me"
    assert store.count(NS) == 1


def test_delete_is_namespace_scoped(store):
    store.put(NS, "same-key", _val("episodic copy"))
    store.put(OTHER, "same-key", _val("semantic copy"))
    store.delete(NS, "same-key")
    assert store.get(NS, "same-key") is None
    assert store.get(OTHER, "same-key").value["text"] == "semantic copy"


def test_a_deleted_record_leaves_search_and_count(store):
    store.put(NS, "a", _val("insulin regulates blood glucose"))
    store.put(NS, "b", _val("photosynthesis converts light into sugar"))
    store.delete(NS, "a")
    keys = {h.key for h in store.search(NS, query="how does insulin work", limit=10)}
    assert keys == {"b"}
    assert store.search(NS, limit=10)[0].key == "b"
    assert store.count(NS) == 1


def test_a_deleted_key_can_be_recreated(store):
    store.put(NS, "k1", _val("first life", track="learned_qa"))
    store.delete(NS, "k1")
    store.put(NS, "k1", _val("second life"))
    value = store.get(NS, "k1").value
    assert value["text"] == "second life"
    assert "track" not in value  # the delete really cleared the old metadata
    assert store.count(NS) == 1
