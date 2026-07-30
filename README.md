# Memory-Management-Tools

Evaluation sandbox for deciding which external memory-management approach should replace or augment the
hand-rolled memory layer used by the main project, **Memora** (sibling directory `../RAG-work`, a self-learning
agentic RAG system).

This is not a product — it's a place to build small, throwaway memory setups with one candidate at a time, each
modeling the same memory roles Memora's real architecture separates memory into, so candidates can be compared
against each other and against Memora's existing implementation on equal footing. See `CLAUDE.md` for the full
working agreement.

## Documentation

Full project history and reasoning lives in `docs/`, following a five-file tracking system:

| File | Answers |
|---|---|
| [`docs/Status.md`](docs/Status.md) | What happened, and when? |
| [`docs/Architecture.md`](docs/Architecture.md) | What does the system look like right now, and how did it get here? |
| [`docs/Decisions.md`](docs/Decisions.md) | Why did we choose X over Y? |
| [`docs/Research.md`](docs/Research.md) | What did we learn by investigating/reading something? |
| [`docs/Bugs.md`](docs/Bugs.md) | What broke, why, and how was it fixed? |

## Current state

**Evaluation is currently paused.** Across the candidates evaluated so far, tool-calling support (or its
absence) keeps resurfacing as a design constraint — a hard blocker for LangMem's SDK layer, and a recurring
soft constraint shaping Mem0's provider/extraction choices even though its core pipeline doesn't strictly
require it (see `docs/Research.md` topic 9). An upgrade to a tool-calling-capable local LLM is under
consideration but not yet decided; no further candidate work is planned until that's resolved (`docs/Decisions.md`
ADR-024). `memora_mini/` (LangMem) and `Customer_Support_Agent/` (Mem0, first pass) are both left in their
current, already-tested states.

**LangMem** was the first candidate evaluated. `LangMem/` holds its environment (tutorial reference material,
`LangMem_Documentation.txt`) and is now reference material only — the active experiment no longer runs out of
that directory.

**`memora_mini/`** is the current implementation: a native reimplementation of LangMem's memory taxonomy
(episodic / semantic / procedural) and its `BaseStore`-shaped four-verb store interface, built with **no
`langmem` dependency and no tool-calling anywhere**. It exists because a first-pass prototype
(`temp_graph/`, since deleted) that called the `langmem` SDK directly ran into a hard blocker: LangMem's memory
managers depend on `trustcall`, which depends on tool-calling, which Memora's actual LLM endpoint doesn't
support. See `docs/Decisions.md` ADR-010 and `docs/Research.md` topic 7 for the full reasoning.

`memora_mini/` implements, natively:

- A four-verb `MemoryStore` protocol (`put`/`get`/`search`/`delete`) backed by ChromaDB, signature-compatible
  with LangGraph's `BaseStore` so a real store could drop in later without touching a caller.
- Four memory namespaces — episodic, semantic, failure (negative-episodic), procedural — each with a
  supersede-not-delete lifecycle, strength-based recall (similarity × hit-count boost × recency decay), and an
  offline extract → classify → apply memory-formation pipeline that consolidates rather than accumulates.
- A five-node LangGraph query graph (`load_memory → retrieve → generate → judge → retry-or-log`) exercising all
  four namespaces plus a read-only source-document collection.

Full detail: `docs/Architecture.md`.

### Running it

```bash
# from the repo root
.venv/Scripts/python.exe memora_mini/demo.py    # scripted end-to-end demo
.venv/Scripts/python.exe memora_mini/main.py     # CLI REPL

# tests need no LLM server and no network
.venv/Scripts/python.exe -m pytest tests/ -q
```

Requires `CUSTOM_API_BASE` / `CUSTOM_API_KEY` / `CUSTOM_API_MODEL_NAME` set in the repo-root `.env` for live LLM
calls (`main.py`, and the live-learning steps of `demo.py`); the test suite and the structural parts of `demo.py`
need neither.

### Mem0 — `Customer_Support_Agent/` (first pass, in progress)

**Mem0** is the second candidate under evaluation: a single-file LangGraph chatbot (`main.py`) that calls Mem0's
hosted Platform client (`mem0.MemoryClient`) directly for `search()`/`add()`, rather than the multi-module,
namespace-separated shape `memora_mini/` uses for LangMem. It's a first-pass wiring check, not yet decomposed
into Memora's four memory roles — everything is stored in one undifferentiated Mem0 space, scoped only by a
hardcoded `user_id`.

A captured run (`run_log.txt`) confirms the read/write round-trip works end-to-end against a live LLM, with two
open issues logged in `docs/Bugs.md`: BUG-002 (an intermittent DNS resolution failure reaching Mem0's hosted API,
traced to the local router's flaky IPv6 resolver, not a code defect) and BUG-004 (`mem0.add()`'s own return value
always claims "0 memories added" even though later searches prove writes are succeeding). Using the *hosted*
Mem0 Platform (rather than Mem0's self-hosted Docker/Postgres+pgvector stack) is a first-pass convenience, not a
settled choice — see `docs/Decisions.md` ADR-022 — since it's the one place in this repo that sends interaction
content to a third-party cloud service, cutting against the no-cloud-egress precedent LangMem's evaluation
otherwise established.

Full detail: `docs/Architecture.md` § "Candidate: Mem0".

Future candidates (Graphiti, Letta, etc.) will each get their own top-level directory the same way, independent
of `LangMem/`, `memora_mini/`, and `Customer_Support_Agent/` — though see "Current state" above: that work is on
hold for now.
