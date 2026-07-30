"""Curated semantic memory for the demo corpus.

Semantic memory is the one namespace with no automatic extraction path. That is
deliberate: domain facts and disambiguation rules are the layer you most want a
human to own, and an 8B model asked to mine "facts" from a corpus produces
restatements of whatever chunk it just read. They are seeded here and can be
added at runtime with the REPL's `fact` command.
"""
from __future__ import annotations

from memora_mini.memory.schemas import SemanticFact
from memora_mini.store.namespaces import SEMANTIC

SEED_FACTS = [
    SemanticFact(
        subject="ASD",
        fact=("ambiguous acronym in this corpus. In developmental psychiatry it is Autism "
              "Spectrum Disorder; in cardiology it is Atrial Septal Defect. Ask which domain "
              "is meant, or answer for both and say so."),
        disambiguates=["Autism Spectrum Disorder", "Atrial Septal Defect"],
    ),
    SemanticFact(
        subject="evidence grade",
        fact=("animal-model results describe a mechanism only. Never state them as an effect "
              "in humans; name the study design alongside any claim drawn from this corpus."),
    ),
    SemanticFact(
        subject="dose schedule",
        fact=("for supplement questions, total dose and dose schedule are separate variables. "
              "Daily and large intermittent dosing can point in opposite directions."),
    ),
]


def seed_semantic(store, *, verbose: bool = True) -> int:
    """Idempotent: keys are derived from the subject, and put() is an upsert."""
    for index, fact in enumerate(SEED_FACTS):
        store.put(SEMANTIC, f"seed-{index}", fact.to_value())
    if verbose:
        print(f"  seeded {len(SEED_FACTS)} semantic fact(s)")
    return len(SEED_FACTS)


def add_fact(store, subject: str, fact: str) -> str:
    import uuid

    key = uuid.uuid4().hex[:16]
    store.put(SEMANTIC, key, SemanticFact(subject=subject, fact=fact).to_value())
    return key
