"""The semantic namespace's create path — the one lane with no LLM extraction.

Seeding is an upsert over stable keys, so it has to be safe to run on every
startup; `add_fact` is the REPL's write and has to land a fresh, recallable,
active record without disturbing the seeds.
"""
from memora_mini.facts import SEED_FACTS, add_fact, seed_semantic
from memora_mini.memory.recall import recall
from memora_mini.store.namespaces import MEMORY_TYPE, SEMANTIC


def test_seed_semantic_reports_and_writes_every_seed(store):
    assert seed_semantic(store, verbose=False) == len(SEED_FACTS)
    assert store.count(SEMANTIC) == len(SEED_FACTS)


def test_seed_semantic_is_idempotent(store):
    seed_semantic(store, verbose=False)
    seed_semantic(store, verbose=False)
    seed_semantic(store, verbose=False)
    assert store.count(SEMANTIC) == len(SEED_FACTS)


def test_seeded_facts_use_stable_keys(store):
    seed_semantic(store, verbose=False)
    for index, fact in enumerate(SEED_FACTS):
        item = store.get(SEMANTIC, f"seed-{index}")
        assert item is not None
        assert item.value["subject"] == fact.subject


def test_seeded_facts_are_written_active_and_typed(store):
    seed_semantic(store, verbose=False)
    for item in store.search(SEMANTIC, limit=50):
        assert item.value["active"] is True
        assert item.value["memory_type"] == MEMORY_TYPE[SEMANTIC]
        assert item.value["hit_count"] == 0


def test_a_seeded_disambiguation_rule_keeps_its_list(store):
    seed_semantic(store, verbose=False)
    asd = next(i for i in store.search(SEMANTIC, limit=50) if i.value["subject"] == "ASD")
    assert asd.value["disambiguates"] == ["Autism Spectrum Disorder", "Atrial Septal Defect"]


def test_a_seeded_fact_is_recallable_by_its_subject(store):
    seed_semantic(store, verbose=False)
    hits = recall(store, SEMANTIC, "what does ASD stand for", limit=1, bump=False)
    assert hits and hits[0].value["subject"] == "ASD"


def test_add_fact_returns_a_fresh_key_for_every_call(store):
    first = add_fact(store, "beta blockers", "lower heart rate")
    second = add_fact(store, "beta blockers", "lower heart rate")
    assert first != second
    assert store.count(SEMANTIC) == 2


def test_an_added_fact_is_stored_active_and_recallable(store):
    key = add_fact(store, "creatine", "the most studied ergogenic supplement")
    value = store.get(SEMANTIC, key).value
    assert value["subject"] == "creatine"
    assert value["active"] is True
    assert value["memory_type"] == MEMORY_TYPE[SEMANTIC]
    assert value["text"] == "creatine: the most studied ergogenic supplement"

    hits = recall(store, SEMANTIC, "which supplement is best studied", limit=1, bump=False)
    assert [h.key for h in hits] == [key]


def test_add_fact_leaves_the_seeds_alone(store):
    seed_semantic(store, verbose=False)
    add_fact(store, "creatine", "the most studied ergogenic supplement")
    assert store.count(SEMANTIC) == len(SEED_FACTS) + 1
    assert store.get(SEMANTIC, "seed-0").value["subject"] == SEED_FACTS[0].subject


def test_reseeding_after_a_manual_delete_restores_the_seed(store):
    seed_semantic(store, verbose=False)
    store.delete(SEMANTIC, "seed-0")
    assert store.get(SEMANTIC, "seed-0") is None
    seed_semantic(store, verbose=False)
    assert store.get(SEMANTIC, "seed-0").value["subject"] == SEED_FACTS[0].subject
    assert store.count(SEMANTIC) == len(SEED_FACTS)
