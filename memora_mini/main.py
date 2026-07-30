"""CLI REPL.

Commands: <question> | bad <feedback> | learn | stats | quit
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memora_mini import config  # noqa: E402
from memora_mini.facts import add_fact, seed_semantic  # noqa: E402
from memora_mini.graph.build import ask  # noqa: E402
from memora_mini.ingest import ingest  # noqa: E402
from memora_mini.memory.reflect import log_interaction, reflect  # noqa: E402
from memora_mini.store.chroma_store import ChromaMemoryStore  # noqa: E402
from memora_mini.store.namespaces import ALL_COLLECTION_NAMESPACES  # noqa: E402

BANNER = """memora_mini commands:
  <question>            ask
  bad <feedback>        thumb down the last answer, with feedback text
  fact <subject> | <f>  add a semantic fact by hand
  learn                 force a reflection run now
  stats                 per-namespace counts (active / superseded)
  quit
"""


def stats(store) -> dict:
    """Per-namespace counts plus the active/superseded split."""
    out = {}
    for namespace in ALL_COLLECTION_NAMESPACES:
        total = store.count(namespace)
        active = len(store.search(namespace, filter={"active": True}, limit=1000)) if total else 0
        out["/".join(namespace)] = {
            "total": total,
            "active": active,
            "superseded": total - active,
        }
    out["documents"] = {"total": store.count(("documents",)), "active": "-", "superseded": "-"}
    return out


def print_stats(store) -> None:
    print(f"\n  {'namespace':<32} {'total':>6} {'active':>7} {'superseded':>11}")
    for name, row in stats(store).items():
        print(f"  {name:<32} {row['total']:>6} {str(row['active']):>7} {str(row['superseded']):>11}")
    print()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    store = ChromaMemoryStore()
    if store.count(("documents",)) == 0:
        print("documents collection is empty - ingesting corpus/ ...")
        ingest(store)
        seed_semantic(store)

    successes = 0
    last: dict = {}
    print(BANNER)
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break

        if line == "stats":
            print_stats(store)
            continue

        if line == "learn":
            report = reflect(store)
            print(f"  reflection: {report}")
            continue

        if line.startswith("fact "):
            subject, _, fact = line[5:].partition("|")
            if not fact.strip():
                print("  usage: fact <subject> | <the fact>")
                continue
            add_fact(store, subject.strip(), fact.strip())
            print("  semantic fact stored.")
            continue

        if line.startswith("bad"):
            if not last:
                print("  nothing to thumb down yet.")
                continue
            feedback = line[3:].strip()
            log_interaction(store, {**last, "status": "THUMBDOWN", "feedback": feedback,
                                    "variants": [last.get("question", "")]})
            print("  thumbdown recorded. Run `learn` to consolidate it into failure memory.")
            continue

        state = ask(store, line)
        print(f"\n{state.get('answer', '')}\n")
        print(f"  [verdict={state.get('verdict')} iterations={state.get('iteration')} "
              f"docs={len(state.get('document_chunks') or [])} "
              f"learned={len(state.get('learned_qa') or [])} "
              f"failures_injected={len(state.get('failure_memories') or [])}]")
        last = {"question": line, "answer": state.get("answer", ""), "context": state.get("prompt", "")}
        successes += 1
        if successes % config.LEARN_EVERY_N == 0:
            print(f"  ({config.LEARN_EVERY_N} interactions - running reflection)")
            print(f"  reflection: {reflect(store)}")


if __name__ == "__main__":
    main()
