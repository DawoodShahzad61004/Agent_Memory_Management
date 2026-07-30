import pytest

from memora_mini.store.chroma_store import ChromaMemoryStore, open_collection
from memora_mini.store.namespaces import ALL_NAMESPACES, collection_name

NS = ("memora", "test", "episodic")


def _val(text, **extra):
    base = {"text": text, "active": True, "hit_count": 0, "last_hit_at": ""}
    base.update(extra)
    return base


def test_collection_name_mapping():
    assert collection_name(("memora", "demo", "episodic")) == "memora__demo__episodic"
    with pytest.raises(ValueError):
        collection_name(())


def test_cosine_pinned_on_every_collection(store):
    for namespace in ALL_NAMESPACES:
        collection = store.collection(namespace)
        assert collection.configuration_json["hnsw"]["space"] == "cosine"


def test_open_collection_rejects_non_cosine(tmp_path):
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path / "c"))
    client.get_or_create_collection(name="legacy-l2-collection")  # default space = l2
    with pytest.raises(RuntimeError, match="expected 'cosine'"):
        open_collection(client, "legacy-l2-collection")


def test_put_get_roundtrip_flattens_and_restores_lists(store):
    store.put(NS, "k1", _val("hello world", source_paths=["a.txt", "b.txt"], superseded_by=None))
    item = store.get(NS, "k1")
    assert item.key == "k1"
    assert item.value["text"] == "hello world"
    assert item.value["source_paths"] == ["a.txt", "b.txt"]
    assert item.value["superseded_by"] is None
    assert store.get(NS, "missing") is None


def test_put_requires_text(store):
    with pytest.raises(ValueError):
        store.put(NS, "k", {"active": True})


def test_put_is_an_upsert(store):
    store.put(NS, "k1", _val("first version"))
    store.put(NS, "k1", _val("second version"))
    assert store.count(NS) == 1
    assert store.get(NS, "k1").value["text"] == "second version"


def test_search_respects_metadata_filter(store):
    store.put(NS, "a", _val("cats are mammals", track="learned_qa"))
    store.put(NS, "b", _val("cats are mammals too", track="documents"))
    hits = store.search(NS, query="cats", filter={"track": "learned_qa"}, limit=10)
    assert [h.key for h in hits] == ["a"]


def test_search_metadata_only_without_query(store):
    store.put(NS, "a", _val("alpha", active=True))
    store.put(NS, "b", _val("beta", active=False))
    hits = store.search(NS, filter={"active": True}, limit=10)
    assert [h.key for h in hits] == ["a"]


def test_search_combines_query_and_filter(store):
    store.put(NS, "a", _val("insulin regulates blood glucose", active=True))
    store.put(NS, "b", _val("insulin regulates blood glucose", active=False))
    hits = store.search(NS, query="what does insulin do", filter={"active": True}, limit=10)
    assert [h.key for h in hits] == ["a"]
    assert 0.0 < hits[0].score <= 1.0


def test_delete_removes_the_record(store):
    store.put(NS, "k1", _val("gone soon"))
    store.delete(NS, "k1")
    assert store.get(NS, "k1") is None


def test_update_metadata_does_not_reembed(store, monkeypatch):
    store.put(NS, "k1", _val("stable text"))

    import memora_mini.store.chroma_store as cs

    monkeypatch.setattr(cs, "embed_one", lambda text: pytest.fail("re-embedded on metadata update"))
    store.update_metadata(NS, "k1", {"hit_count": 7})
    assert store.get(NS, "k1").value["hit_count"] == 7
    assert store.get(NS, "k1").value["text"] == "stable text"


def test_store_satisfies_the_protocol(store):
    import inspect

    from memora_mini.store.protocol import MemoryStore

    assert isinstance(store, MemoryStore)
    # Signature compatibility is the whole point of the Protocol — a future
    # BaseStore subclass has to accept these exact call shapes.
    sig = inspect.signature(ChromaMemoryStore.search)
    assert list(sig.parameters) == ["self", "namespace", "query", "filter", "limit"]
    assert sig.parameters["query"].kind is inspect.Parameter.KEYWORD_ONLY
