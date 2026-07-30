"""Scripted end-to-end demo. Run against a fresh store:

    ../../LangMem/.venv/Scripts/python.exe demo.py

Every acceptance behaviour of the memory layer is exercised in order, with the
console output showing what changed at each step.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memora_mini import config, llm  # noqa: E402
from memora_mini.facts import seed_semantic  # noqa: E402
from memora_mini.graph.build import ask  # noqa: E402
from memora_mini.ingest import ingest  # noqa: E402
from memora_mini.main import print_stats  # noqa: E402
from memora_mini.memory import apply as apply_mod  # noqa: E402
from memora_mini.memory import classify as classify_mod  # noqa: E402
from memora_mini.memory.reflect import log_interaction, reflect  # noqa: E402
from memora_mini.memory.schemas import EpisodicMemory  # noqa: E402
from memora_mini.store.chroma_store import ChromaMemoryStore  # noqa: E402
from memora_mini.store.namespaces import EPISODIC, FAILURE, PROCEDURAL  # noqa: E402

Q1 = "What does ASD mean in developmental psychiatry?"
Q1_REPHRASED = "In psychiatry, which condition do the letters A-S-D refer to?"
Q2 = "Does vitamin D reduce fracture risk?"
Q2_REPHRASED = "Is taking vitamin D supplements effective at preventing broken bones?"
FEEDBACK = ("You ignored dose schedule entirely. High intermittent annual dosing "
            "increased falls and fractures - that is the part that matters here.")
MORE_FEEDBACK = [
    ("Will a vitamin D supplement stop me breaking a bone?",
     "Again nothing about dosing schedule. Daily versus large annual doses is the whole point."),
    ("Should older adults take vitamin D for bone strength?",
     "You left out the dose schedule difference again. Intermittent megadoses are harmful."),
    ("Is vitamin D supplementation good for bone health?",
     "Still no mention of how dose frequency changes the result."),
]


def step(number: int, title: str) -> None:
    print(f"\n{'=' * 78}\nSTEP {number} - {title}\n{'=' * 78}")


def counts(store) -> tuple[int, int]:
    total = store.count(EPISODIC)
    active = len(store.search(EPISODIC, filter={"active": True}, limit=500))
    return total, active


def failure_counts(store) -> tuple[int, int]:
    total = store.count(FAILURE)
    active = len(store.search(FAILURE, filter={"active": True}, limit=500))
    return total, active


def show_answer(state: dict, label: str) -> None:
    print(f"\n  ANSWER ({label}):\n    " + state.get("answer", "").replace("\n", "\n    "))
    print(f"  [docs={len(state.get('document_chunks') or [])} "
          f"learned_qa={len(state.get('learned_qa') or [])} "
          f"failures_injected={len(state.get('failure_memories') or [])} "
          f"verdict={state.get('verdict')} iterations={state.get('iteration')}]")


def main() -> None:  # noqa: C901 - a linear script, read top to bottom
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if not llm.is_reachable():
        sys.exit(f"LLM endpoint {config.LLM_BASE_URL} is unreachable. "
                 "Start the local server (CUSTOM_API_BASE in LangMem/.env) and re-run.")

    step(0, "fresh store")
    shutil.rmtree(config.CHROMA_PATH, ignore_errors=True)
    Path(config.AUDIT_LOG_PATH).unlink(missing_ok=True)
    store = ChromaMemoryStore()
    print(f"  ingesting {config.CORPUS_DIR.name}/ (one acronym, ASD, has two unrelated meanings)")
    print(f"  {ingest(store)} chunk(s) in `documents`")
    seed_semantic(store)

    step(1, "ask with an empty episodic namespace - documents only")
    state = ask(store, Q1)
    show_answer(state, "documents only")
    assert store.count(EPISODIC) == 0, "episodic namespace should still be empty"
    print(f"  semantic facts recalled: "
          f"{[f.get('subject') for f in state.get('semantic_facts') or []]}")
    print(f"  ASD disambiguation reached the prompt: "
          f"{'Atrial Septal Defect' in state.get('prompt', '')}")
    print(f"  episodic total/active: {counts(store)}")

    step(2, "learn in DRY RUN - proposes operations, writes nothing")
    before = counts(store)
    report = reflect(store, dry_run=True)
    print(f"  {json.dumps(report['lanes'], indent=2)}")
    print(f"  episodic total/active before={before} after={counts(store)}  (unchanged)")
    assert counts(store) == before

    step(3, "learn with DRY_RUN_MEMORY_OPS=False - episodic namespace populated")
    report = reflect(store, dry_run=False)
    print(f"  {json.dumps(report['lanes'], indent=2)}")
    print(f"  episodic total/active: {counts(store)}")

    step(4, "semantically different rephrasing - recall is not string matching")
    print(f"  original:  {Q1}\n  rephrased: {Q1_REPHRASED}")
    state = ask(store, Q1_REPHRASED)
    show_answer(state, "should now recall episodic memory")
    print(f"  learned_qa recalled: {[l.get('text', '')[:70] for l in state.get('learned_qa') or []]}")

    step(5, "thumbdown, then a differently-worded question - BUG-009 regression check")
    state = ask(store, Q2)
    show_answer(state, "about to be rejected")
    log_interaction(store, {"question": Q2, "answer": state.get("answer", ""),
                            "context": state.get("prompt", ""), "status": "THUMBDOWN",
                            "feedback": FEEDBACK, "variants": [Q2]})
    print("  thumbdown recorded; consolidating into failure memory ...")
    reflect(store, dry_run=False)
    print(f"  failure total/active: {failure_counts(store)}")
    for item in store.search(FAILURE, filter={"active": True}, limit=5):
        print(f"    missing_information: {item.value.get('missing_information')!r}")

    print(f"\n  now asking a differently-worded version:\n    {Q2_REPHRASED}")
    state = ask(store, Q2_REPHRASED)
    show_answer(state, "failure memory should be injected")
    injected = "RETRIEVAL REDIRECTION" in state.get("prompt", "")
    print(f"  positive redirection present in prompt: {injected}")
    if injected:
        block = state["prompt"].split("(from prior failed attempts) ===")[1].split("===")[0]
        print("  " + block.strip().replace("\n", "\n  "))
    assert injected, "BUG-009 regression: failure memory did not reach the rephrased query"

    step(6, "three more thumbdowns on the same theme - consolidation, not accumulation")
    before_total, before_active = failure_counts(store)
    for question, feedback in MORE_FEEDBACK:
        log_interaction(store, {"question": question, "answer": "(a bad answer)",
                                "status": "THUMBDOWN", "feedback": feedback,
                                "variants": [question]})
    print(f"  raw thumbdowns filed on this theme: {1 + len(MORE_FEEDBACK)}")
    print(f"  failure memory BEFORE consolidation: total={before_total} active={before_active}")
    reflect(store, dry_run=False)
    after_total, after_active = failure_counts(store)
    print(f"  failure memory AFTER  consolidation: total={after_total} active={after_active}")
    print(f"  -> {1 + len(MORE_FEEDBACK)} thumbdowns collapsed into {after_active} active entr"
          f"{'y' if after_active == 1 else 'ies'}")
    proposals = store.search(PROCEDURAL, limit=10)
    print(f"  procedural proposals raised by the recurring theme: {len(proposals)}")
    for proposal in proposals:
        print(f"    approved={proposal.value.get('approved')} (never auto-applied): "
              f"{proposal.value.get('proposed_text')}")

    step(7, "a contradicting memory - supersede, not overwrite")
    seed = EpisodicMemory(
        question="Does vitamin D alone reduce fracture risk in community-dwelling adults?",
        answer="Yes. Vitamin D taken alone clearly reduces fracture rates in community-dwelling adults.",
        evidence_type="meta_analysis", confidence=0.7, source_paths=["vitamin_d.md"],
    ).to_value()
    store.put(EPISODIC, "seed-contradiction", seed)
    print(f"  seeded existing memory: {seed['text'][:90]}...")

    contradiction = EpisodicMemory(
        question="Does vitamin D alone reduce fracture risk in community-dwelling adults?",
        answer="No. Vitamin D taken alone had little effect on fracture rate in community-dwelling adults.",
        evidence_type="meta_analysis", confidence=0.9, source_paths=["vitamin_d.md"],
    ).to_value()
    # Driven through classify -> plan -> apply directly so the step is
    # reproducible; the extract stage is already demonstrated in steps 2-3.
    pairs = classify_mod.classify(store, EPISODIC, contradiction["text"])
    neighbour, verdict = classify_mod.strongest(pairs)
    print(f"  verdict: {verdict} (against {neighbour.key if neighbour else 'nothing'})")
    op = apply_mod.plan(EPISODIC, contradiction, neighbour, verdict)
    print(f"  planned op: {json.dumps(op.as_json(), indent=2)}")
    apply_mod.apply_ops(store, [op], dry_run=False)
    old = store.get(EPISODIC, "seed-contradiction")
    print(f"  old record: active={old.value['active']} superseded_by={old.value['superseded_by']!r}")
    print("  audit log tail:")
    tail = Path(config.AUDIT_LOG_PATH).read_text(encoding="utf-8").strip().splitlines()[-1]
    print("    " + json.dumps(json.loads(tail), indent=2).replace("\n", "\n    "))

    step(8, "final stats")
    print_stats(store)
    total, active = counts(store)
    print(f"  episodic: {active} active of {total} stored - consolidation kept the active "
          f"count below the raw candidate count.")
    print(f"  audit log: {config.AUDIT_LOG_PATH}")


if __name__ == "__main__":
    main()
