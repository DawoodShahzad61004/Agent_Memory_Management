"""End-to-end wiring tests with a stubbed LLM — no network, no local server."""
import pytest

from memora_mini import llm
from memora_mini.graph import nodes
from memora_mini.graph.build import ask
from memora_mini.memory.schemas import EpisodicMemory, FailureMemory, SemanticFact
from memora_mini.store.namespaces import EPISODIC, FAILURE, SEMANTIC


@pytest.fixture
def stub_llm(monkeypatch):
    """Replay canned responses; record every prompt the graph builds."""
    calls = []

    def fake_chat(system, user, **kwargs):
        calls.append({"system": system, "user": user})
        if "grade whether an answer" in system:
            return "OK"
        if "compare a NEW memory" in system:
            return "UNRELATED"
        return "A stubbed answer."

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(nodes.llm, "chat", fake_chat)
    return calls


def _seed_documents(store):
    store.put(("documents",), "doc::0",
              {"text": "In cardiology, ASD stands for Atrial Septal Defect.",
               "source": "asd_cardiology.md", "hit_count": 0, "last_hit_at": ""})


def test_graph_runs_and_logs_the_interaction(store, stub_llm):
    _seed_documents(store)
    state = ask(store, "What does ASD stand for?")
    assert state["answer"] == "A stubbed answer."
    assert state["verdict"] == "OK"
    assert state["interaction_id"]
    assert len(state["document_chunks"]) == 1


def test_failure_injection_is_capped_at_max_failure_injections(store, stub_llm, monkeypatch):
    monkeypatch.setattr(nodes, "MAX_FAILURE_INJECTIONS", 2)
    _seed_documents(store)
    for index in range(5):
        store.put(FAILURE, f"f{index}", FailureMemory(
            original_query="does vitamin D prevent fractures",
            missing_information=f"dose schedule detail number {index}",
        ).to_value())

    state = ask(store, "does vitamin D prevent fractures")
    assert len(state["failure_memories"]) == 2

    prompt = state["prompt"]
    injected = sum(1 for i in range(5) if f"dose schedule detail number {i}" in prompt)
    assert injected == 2


def test_failure_injection_is_positive_redirection_not_a_blocklist(store, stub_llm):
    _seed_documents(store)
    store.put(FAILURE, "f0", FailureMemory(
        original_query="does vitamin D prevent fractures",
        user_feedback="You ignored dose schedule entirely, which is unacceptable.",
        missing_information="dose schedule differences",
    ).to_value())

    # Deliberately different wording — this is the BUG-009 behaviour.
    state = ask(store, "will taking vitamin D supplements stop me breaking a bone?")
    prompt = state["prompt"]
    assert len(state["failure_memories"]) == 1
    assert "seek and state dose schedule differences" in prompt
    # The raw complaint is the wrong shape for redirecting retrieval; only the
    # derived missing_information reaches the prompt.
    assert "unacceptable" not in prompt


def test_semantic_facts_are_loaded_into_the_prompt(store, stub_llm):
    _seed_documents(store)
    store.put(SEMANTIC, "s0", SemanticFact(
        subject="ASD", fact="ambiguous acronym: Autism Spectrum Disorder or Atrial Septal Defect",
        disambiguates=["Autism Spectrum Disorder", "Atrial Septal Defect"],
    ).to_value())
    state = ask(store, "what does ASD mean?")
    assert "DOMAIN FACTS" in state["prompt"]
    assert "ambiguous acronym" in state["prompt"]


def test_episodic_track_filter_is_load_bearing(store, stub_llm):
    """A wrong `track` value is a visible retrieval miss, not silent rot."""
    _seed_documents(store)
    good = EpisodicMemory(question="What is an ASD?", answer="Atrial Septal Defect.").to_value()
    rotten = {**good, "track": "documents"}  # wrong value
    store.put(EPISODIC, "good", good)
    state = ask(store, "What is an ASD?")
    assert [l["track"] for l in state["learned_qa"]] == ["learned_qa"]

    store.delete(EPISODIC, "good")
    store.put(EPISODIC, "rotten", rotten)
    state = ask(store, "What is an ASD?")
    assert state["learned_qa"] == []


def test_retry_loop_stops_at_max_iterations(store, monkeypatch):
    _seed_documents(store)
    monkeypatch.setattr(nodes, "MAX_ITERATIONS", 2)

    def always_insufficient(system, user, **kwargs):
        return "INSUFFICIENT" if "grade whether an answer" in system else "A stubbed answer."

    monkeypatch.setattr(nodes.llm, "chat", always_insufficient)
    state = ask(store, "unanswerable question")
    assert state["iteration"] == 2
    assert state["verdict"] == "INSUFFICIENT"
    assert state["interaction_id"]
