"""Reflection orchestration with a stubbed LLM."""
import json

import pytest

from memora_mini.memory import apply as apply_mod
from memora_mini.memory import classify as classify_mod
from memora_mini.memory import extract as extract_mod
from memora_mini.memory.reflect import log_interaction, pending_interactions, reflect
from memora_mini.store.namespaces import EPISODIC, FAILURE


@pytest.fixture(autouse=True)
def audit_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(apply_mod, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")


@pytest.fixture
def canned(monkeypatch):
    """Drive extract + classify from a script instead of a live model."""
    state = {"verdict": "UNRELATED", "episodic": [], "failure": []}

    def fake_chat(system, user, **kwargs):
        if "compare a NEW memory" in system:
            return state["verdict"]
        if "distill reusable" in system:
            return json.dumps(state["episodic"])
        if "summarise why an answer was rejected" in system:
            return json.dumps(state["failure"])
        return ""

    monkeypatch.setattr(extract_mod.llm, "chat", fake_chat)
    monkeypatch.setattr(classify_mod.llm, "chat", fake_chat)
    return state


def _thumbdown(store, question, feedback):
    log_interaction(store, {"question": question, "answer": "a bad answer",
                            "status": "THUMBDOWN", "feedback": feedback, "variants": [question]})


def test_reflect_with_no_interactions_is_a_noop(store, canned):
    assert reflect(store, dry_run=False, verbose=False)["interactions"] == 0


def test_dry_run_leaves_the_store_and_the_queue_untouched(store, canned):
    canned["episodic"] = [{"question": "What is ASD?", "answer": "Autism Spectrum Disorder."}]
    log_interaction(store, {"question": "What is ASD?", "answer": "Autism Spectrum Disorder.",
                            "status": "OK"})
    report = reflect(store, dry_run=True, verbose=False)

    assert report["lanes"]["episodic"]["applied"] == 0
    assert store.count(EPISODIC) == 0
    assert len(pending_interactions(store)) == 1  # still queued for a real run


def test_real_run_populates_episodic_and_consumes_the_queue(store, canned):
    canned["episodic"] = [{"question": "What is ASD?", "answer": "Autism Spectrum Disorder.",
                           "evidence_type": "observational", "confidence": 0.8}]
    log_interaction(store, {"question": "What is ASD?", "answer": "Autism Spectrum Disorder.",
                            "status": "OK", "source_paths": ["asd_autism.md"]})
    reflect(store, dry_run=False, verbose=False)

    assert store.count(EPISODIC) == 1
    item = store.search(EPISODIC, filter={"active": True}, limit=5)[0]
    assert item.value["track"] == "learned_qa"          # filled in Python, not by the LLM
    assert item.value["source_paths"] == ["asd_autism.md"]
    assert pending_interactions(store) == []


def test_thumbdowns_on_one_theme_consolidate_instead_of_accumulating(store, canned):
    canned["failure"] = [{"original_query": "does vitamin D prevent fractures",
                          "bad_answer": "ignored dosing", "user_feedback": "you ignored dosing",
                          "missing_information": "dose schedule differences"}]

    _thumbdown(store, "does vitamin D prevent fractures", "you ignored dosing")
    reflect(store, dry_run=False, verbose=False)
    assert store.count(FAILURE) == 1

    # Three more on the same theme, each judged DUPLICATE against what exists.
    canned["verdict"] = "DUPLICATE"
    for question in ("will vitamin D stop a fracture", "is vitamin D good for bones",
                     "should older adults take vitamin D"):
        _thumbdown(store, question, "still nothing about dosing schedule")
    reflect(store, dry_run=False, verbose=False)

    active = store.search(FAILURE, filter={"active": True}, limit=50)
    assert len(active) == 1, "4 thumbdowns must collapse into 1 failure entry"
    assert active[0].value["hit_count"] == 3  # each duplicate reinforced it


def test_contradicting_candidate_supersedes(store, canned):
    canned["episodic"] = [{"question": "Does vitamin D alone reduce fractures?", "answer": "Yes."}]
    log_interaction(store, {"question": "Does vitamin D alone reduce fractures?", "answer": "Yes.",
                            "status": "OK"})
    reflect(store, dry_run=False, verbose=False)
    original = store.search(EPISODIC, filter={"active": True}, limit=5)[0]

    canned["verdict"] = "CONTRADICTS"
    canned["episodic"] = [{"question": "Does vitamin D alone reduce fractures?", "answer": "No."}]
    log_interaction(store, {"question": "Does vitamin D alone reduce fractures?", "answer": "No.",
                            "status": "OK"})
    reflect(store, dry_run=False, verbose=False)

    superseded = store.get(EPISODIC, original.key).value
    assert superseded["active"] is False
    assert superseded["superseded_by"]
    assert len(store.search(EPISODIC, filter={"active": True}, limit=50)) == 1
    assert store.count(EPISODIC) == 2  # nothing deleted


def test_recurring_failure_theme_proposes_a_prompt_revision(store, canned, monkeypatch):
    from memora_mini.memory.reflect import propose_prompt_revisions
    from memora_mini.memory.schemas import FailureMemory
    from memora_mini.store.namespaces import PROCEDURAL

    monkeypatch.setattr("memora_mini.memory.reflect.PROCEDURAL_PROPOSAL_HITS", 3)
    value = FailureMemory(original_query="q", missing_information="dose schedule differences").to_value()

    store.put(FAILURE, "f0", {**value, "hit_count": 2})
    assert propose_prompt_revisions(store) == []  # not recurrent enough yet

    store.put(FAILURE, "f0", {**value, "hit_count": 3})
    ops = propose_prompt_revisions(store)
    assert len(ops) == 1 and ops[0].action == "insert"
    assert ops[0].new_value["approved"] is False
    apply_mod.apply_ops(store, ops, dry_run=False)

    stored = store.search(PROCEDURAL, limit=5)[0].value
    assert stored["target_prompt"] == "GENERATE_SYSTEM"
    assert stored["approved"] is False
    # Never auto-applied: nothing in the generate path reads this namespace.
    assert propose_prompt_revisions(store) == []  # and never proposed twice


def test_procedural_memory_is_never_injected_into_generation(store, monkeypatch):
    from memora_mini.graph import nodes
    from memora_mini.memory.schemas import PromptRevision
    from memora_mini.store.namespaces import PROCEDURAL

    monkeypatch.setattr(nodes.llm, "chat", lambda *a, **k: "stub")
    store.put(PROCEDURAL, "p0", PromptRevision(
        target_prompt="GENERATE_SYSTEM", proposed_text="NEVER-AUTO-APPLIED-SENTINEL",
    ).to_value())
    store.put(("documents",), "d0", {"text": "some corpus text", "source": "s.md",
                                     "hit_count": 0, "last_hit_at": ""})
    state = nodes.load_memory({"store": store, "question": "anything"})
    state.update(nodes.retrieve({"store": store, "question": "anything", **state}))
    prompt = nodes.generate({"store": store, "question": "anything", **state})["prompt"]
    assert "NEVER-AUTO-APPLIED-SENTINEL" not in prompt


def test_extract_failure_falls_back_cleanly_on_garbage(store, monkeypatch):
    monkeypatch.setattr(extract_mod.llm, "chat", lambda *a, **k: "Sorry, I cannot do that.")
    assert extract_mod.extract_failure({"question": "q", "answer": "a", "feedback": "f"}) == []
