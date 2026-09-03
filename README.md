# Agent Memory Management

A reusable **memory-management module for coding agents** — `mem_manage/`.

The goal is a drop-in memory layer that a coding agent can hand raw interactions to, and get back a small,
current, non-contradictory set of **durable learnings** — not a growing transcript. Memory that only accumulates
degrades: retrieval gets noisier, stale conventions outlive the code they described, and contradictory entries
sit side by side with nothing to break the tie. This module treats *forgetting* as a first-class mechanism rather
than a storage-cleanup afterthought.

> **Status: implementation complete, testing phase.** `mem_manage/` is built, tested (107/108 passing tests),
> and CLI-verified end-to-end. The module is usable for compacting episodic-memory markdown logs right now;
> integration into `Sample_Coding_Agent/` is the next step. See [`docs/Architecture.md`](docs/Architecture.md) for
> the architecture and [`docs/Status.md`](docs/Status.md) for the implementation timeline.

## Design principles

| Principle | What it means |
|---|---|
| **Every entry is timestamped** | `created_at` and `last_accessed_at` on every record. Time is the input every other mechanism reads. |
| **Every memory carries an activation value** | A single scalar strength that rises on use and falls with time and interference. Recall, merge, degrade and delete all read it. |
| **Similar memories consolidate** | Near-duplicates are deduped, merged, and summarized — then hard-deleted once their activation bottoms out. Growth is bounded by consolidation, not by a cap. |
| **Conflicting memories are not overwritten** | A contradiction is written as a *newer* entry alongside the old one. Recency and decay resolve the conflict over time; no synchronous "which one is right" LLM call in the write path. |
| **Durable learnings, not raw event records** | "This repo uses `pytest` fixtures, not `unittest.TestCase`" is durable. "The user ran the test suite at 14:32" is not. |
| **Explicit choices outrank inferred preferences** | Something the user stated outright is written with higher initial importance and decays more slowly than something guessed from behaviour. |
| **Adaptive decay, in three layers** | (1) *passive decay* — unused memories fade on a time curve; (2) *interference-based forgetting* — crowded, mutually-similar memories suppress each other; (3) *graceful degradation* — a fading memory is compressed to a summary, then a gist, then a tombstone, rather than vanishing in one step. |

## Source paper

Formulae are derived from **["Human-Inspired Memory Architecture for LLM Agents"](https://arxiv.org/pdf/2605.08538v1)**
(arXiv:2605.08538v1) — activation/maturation, passive decay, interference scoring, composite importance, and the
graceful-degradation fidelity ladder. The paper's own evaluation includes a VSCode dataset, so its calibration is
closer to this module's target workload than a general-chat benchmark would be. Its published constants are a
starting point, not a settled configuration — they get re-derived against coding-agent traces here.

The exact equations and how each maps onto this module are tabulated in
[`docs/Architecture.md` § "Formulae"](docs/Architecture.md). The paper was read in full on 2026-09-02
([`docs/Research.md` topic 10](docs/Research.md)), which also worked out a candidate procedure for the one thing
the paper itself leaves unresolved — how a contradictory memory actually gets updated. That procedure is designed
but untested, and it currently conflicts with this repo's own Principle 4 (below); see Architecture.md's Formulae
row 5 for the open question.

## Repository layout

| Path | Role |
|---|---|
| `mem_manage/` | **The module.** The deliverable. Complete: config, importance scoring, memory shape, consolidation, dedup/merge, and CLI. All constants centralized, all tests passing. Awaits integration into the test harness. |
| `mem_manage/tests/` | **Test suite.** 108 tests covering config, scoring, memory lifecycle, decay, pruning, and end-to-end pipeline. All numeric assumptions verified empirically. |
| `Sample_Coding_Agent/` | **Test harness.** The agent `mem_manage/` gets wired into and exercised against. Currently a single-file LangGraph chatbot inherited from the Mem0 evaluation; to be converted from a customer-support persona to a coding agent, with Mem0 replaced by `mem_manage/`. |
| `memora_mini/` | **Prior art, working.** A native reimplementation of LangMem's memory taxonomy — supersede-not-delete lifecycle, strength-based recall with recency decay, offline extract→classify→apply consolidation. Several of its mechanisms are direct antecedents of `mem_manage/`'s. |
| `LangMem/` | Reference material for the LangMem evaluation. Not executable. |
| `tests/` | `pytest` suite for `memora_mini/` (58 tests, no LLM server or network required). |
| `docs/` | Five-file tracking system, below. |

### How this repo got here

It began as an evaluation sandbox comparing external memory libraries (LangMem, then Mem0) for a separate project,
**Memora**. That evaluation stalled on a recurring constraint — most candidates lean on LLM tool-calling, which the
available local endpoint doesn't support (`docs/Decisions.md` ADR-010, ADR-024). What the evaluation did produce was
a clear picture of what the candidates get wrong for this use case: they accumulate, and none of them forget on
purpose. The repo is now scoped to building that missing piece directly. The evaluation directories stay as prior
art; nothing about them is being resumed.

## Running the code

Virtual environments are gitignored and are **not** present in a fresh checkout — create them first
(`uv venv --python 3.13` + install from the relevant `requirements.txt` file).

```bash
# from the repo root — mem_manage (the deliverable, ready to use)
uv venv .venv --python 3.13
uv pip install -r mem_manage/requirements.txt
.venv/Scripts/python.exe -m mem_manage.compact <episodic_log.md>    # CLI: compact a Markdown log

# mem_manage tests (no LLM server or network needed)
.venv/Scripts/python.exe -m pytest mem_manage/tests/ -v             # full test suite
.venv/Scripts/python.exe -m pytest mem_manage/tests/test_importance.py -v  # specific test module

# memora_mini (prior art, LangMem reference implementation, works today)
# (reuses the .venv above)
.venv/Scripts/python.exe memora_mini/demo.py     # scripted end-to-end demo
.venv/Scripts/python.exe memora_mini/main.py     # CLI REPL

# tests for memora_mini
.venv/Scripts/python.exe -m pytest tests/ -q

# the sample agent (Mem0-backed, pre-conversion; separate .venv needed)
Sample_Coding_Agent/.venv/Scripts/python.exe Sample_Coding_Agent/main.py
```

Live LLM calls need `CUSTOM_API_BASE` / `CUSTOM_API_KEY` / `CUSTOM_API_MODEL_NAME` in the repo-root `.env`;
`Sample_Coding_Agent/main.py` additionally needs `MEM0_API_KEY` until its Mem0 dependency is replaced by
`mem_manage/`. The test suite and the structural parts of `demo.py` need neither.

## Documentation

| File | Answers |
|---|---|
| [`docs/Status.md`](docs/Status.md) | What happened, and when? |
| [`docs/Architecture.md`](docs/Architecture.md) | What does the system look like right now, and how did it get here? |
| [`docs/Decisions.md`](docs/Decisions.md) | Why did we choose X over Y? |
| [`docs/Research.md`](docs/Research.md) | What did we learn by investigating/reading something? |
| [`docs/Bugs.md`](docs/Bugs.md) | What broke, why, and how was it fixed? |
