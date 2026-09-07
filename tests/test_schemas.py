"""The record shape every write goes through, and the namespace it belongs to.

`to_value()` is the only way a memory becomes a store value, so the fields it
guarantees — the store-managed base, the rendered `text` — are the contract the
CRUD layer relies on.
"""
from datetime import datetime

import pytest

from memora_mini.memory.schemas import (
    SCHEMA_REGISTRY,
    EpisodicMemory,
    FailureMemory,
    MemoryBase,
    PromptRevision,
    SemanticFact,
    utcnow,
)
from memora_mini.store.namespaces import (
    ALL_COLLECTION_NAMESPACES,
    ALL_NAMESPACES,
    EPISODIC,
    FAILURE,
    MEMORY_TYPE,
    PROCEDURAL,
    SEMANTIC,
    collection_name,
)

SCHEMA_FOR_NAMESPACE = {
    EPISODIC: EpisodicMemory,
    SEMANTIC: SemanticFact,
    FAILURE: FailureMemory,
    PROCEDURAL: PromptRevision,
}

ROUNDTRIP_CASES = [
    ("episodic", EPISODIC, lambda: EpisodicMemory(
        question="What is ASD?", answer="Depends on the domain.",
        evidence_type="observational", source_paths=["asd_autism.md", "asd_cardiology.md"],
        confidence=0.8)),
    ("failure", FAILURE, lambda: FailureMemory(
        original_query="does vitamin D prevent fractures",
        missing_information="dose schedule differences",
        failed_variants=["vitamin D fractures", "vitamin D bones"])),
    ("semantic", SEMANTIC, lambda: SemanticFact(
        subject="ASD", fact="ambiguous acronym in this corpus",
        disambiguates=["Autism Spectrum Disorder", "Atrial Septal Defect"])),
    ("semantic-no-list", SEMANTIC, lambda: SemanticFact(
        subject="dose schedule", fact="total dose and schedule are separate variables")),
    ("procedural", PROCEDURAL, lambda: PromptRevision(
        target_prompt="GENERATE_SYSTEM", proposed_text="always name the study design",
        rationale="recurring failure theme")),
]


def test_to_value_carries_the_rendered_text(store):
    for _, _, factory in ROUNDTRIP_CASES:
        memory = factory()
        assert memory.to_value()["text"] == memory.to_text()
        assert memory.to_text().strip()  # never an empty document


def test_store_managed_defaults_are_present_and_not_the_llms_to_set():
    for _, _, factory in ROUNDTRIP_CASES:
        value = factory().to_value()
        assert value["hit_count"] == 0
        assert value["last_hit_at"] == ""
        assert value["active"] is True
        assert value["superseded_by"] is None
        assert value["contradiction_strikes"] == 0
        assert value["created_at"]


def test_created_at_is_a_parseable_utc_timestamp():
    stamp = utcnow()
    parsed = datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None
    assert datetime.fromisoformat(EpisodicMemory(question="q", answer="a").to_value()["created_at"])


def test_memory_type_agrees_with_the_namespace_the_record_lives_in():
    """A record can never disagree with where it is stored."""
    for namespace, schema in SCHEMA_FOR_NAMESPACE.items():
        assert schema.model_fields["memory_type"].default == MEMORY_TYPE[namespace]


@pytest.mark.parametrize("label,namespace,factory", ROUNDTRIP_CASES,
                         ids=[case[0] for case in ROUNDTRIP_CASES])
def test_every_memory_type_survives_a_put_get_roundtrip(store, label, namespace, factory):
    memory = factory()
    original = memory.to_value()
    store.put(namespace, label, original)
    restored = store.get(namespace, label).value

    assert restored["text"] == memory.to_text()
    assert restored["memory_type"] == MEMORY_TYPE[namespace]
    for field, value in original.items():
        assert restored[field] == value, f"{field} did not survive the roundtrip"


@pytest.mark.parametrize("label,namespace,factory", ROUNDTRIP_CASES,
                         ids=[case[0] for case in ROUNDTRIP_CASES])
def test_every_memory_type_is_searchable_after_it_is_written(store, label, namespace, factory):
    memory = factory()
    store.put(namespace, label, memory.to_value())
    hits = store.search(namespace, query=memory.to_text(), filter={"active": True}, limit=5)
    assert [h.key for h in hits] == [label]
    assert hits[0].score > 0.9


def test_memorybase_refuses_to_render_itself():
    with pytest.raises(NotImplementedError):
        MemoryBase().to_text()


def test_schema_registry_covers_every_stored_memory_type():
    assert set(SCHEMA_FOR_NAMESPACE.values()) <= set(SCHEMA_REGISTRY.values())
    for name, schema in SCHEMA_REGISTRY.items():
        assert schema.__name__ == name


def test_every_namespace_maps_to_its_own_collection():
    names = [collection_name(namespace) for namespace in ALL_COLLECTION_NAMESPACES]
    assert len(set(names)) == len(names)
    assert all(name.count("__") == 2 for name in names)


def test_every_memory_namespace_has_a_declared_memory_type():
    assert set(MEMORY_TYPE) == set(ALL_NAMESPACES)


def test_collection_name_rejects_malformed_namespaces():
    for bad in ((), ("",), ("memora", ""), ("memora", None), ("memora", 3)):
        with pytest.raises(ValueError):
            collection_name(bad)
