## Chronological Log

### July 2026 — Sandbox scaffolded, LangMem selected and wired end-to-end (minus a live LLM test)

- **Repo purpose established:** evaluation sandbox to decide which external memory-management library should
  replace/augment Memora's hand-rolled memory layer, comparing candidates one at a time against Memora's own
  four-role memory architecture.
- **LangMem chosen as the first candidate** after a broader survey of open-source agent-memory libraries.
- **First working experiment built:** a two-node LangGraph (`user_input → generate_answer`) backed by two
  persistent ChromaDB collections (`learned_qa`, `failure_lessons`), with LangMem's `create_memory_manager` doing
  the accept/reject → structured-lesson write-back.

---

#### 2026-07-28 — Repo scaffold, candidate survey, and LangMem environment setup

* Set out to decide which memory-management library should augment/replace Memora's custom memory layer, starting
  from a broad survey of options.
* Searched the `Awesome-Memory-for-Agents` GitHub list, shortlisted ~4-5 candidates by stars/recency/issue health,
  then went deeper on six specific options (LangMem, Mem0, Graphiti, Cognee, Letta, LangGraph Store) against
  Memora's actual LangGraph + ChromaDB + MongoDB stack.
* Selected **LangMem** as the first candidate to build a throwaway comparison harness for — native LangGraph
  integration and storage-agnostic extraction (`create_memory_manager`) made it the lowest-friction first pick.
* Ran `/init` to scaffold `CLAUDE.md`, describing the repo as an evaluation sandbox with one top-level directory
  per candidate library, `uv`-managed environments, and Memora's four-layer memory architecture as the fixed
  comparison yardstick.
* Created `LangMem/requirements.txt` (initially a small unpinned draft: `langmem`, `langgraph`, `langchain-core`,
  `langchain-groq`, `sentence-transformers`, `python-dotenv`) and set up `LangMem/.venv` (`uv`, Python 3.13).
  `requirements.txt` was later regenerated as a full pinned freeze of the installed environment (144 packages,
  including `chromadb==1.5.9`, `langmem==0.0.30`, `langgraph==1.2.9`).
* Deep-dived LangMem's actual API surface (hot-path vs. background memory, `create_memory_manager` vs.
  `create_memory_store_manager`, profile vs. collection memory shapes, the 0.0.30/July-2026 maturity caveat) and
  walked through its official tutorial transcript (`LangMem/tutorial_transcript.txt`) to establish the baseline
  extraction pattern before adapting it to Memora's shape.
* Tracked in: `CLAUDE.md`, `LangMem/requirements.txt`; new Research.md topics 1-4; new Decisions.md ADR-001
  through ADR-005.

---

#### 2026-07-29 — `temp_graph/` experiment implemented and smoke-tested

* Set out to build the actual LangMem experiment: copy relevant service files from `../RAG-work/app_workflow/
  services/` into a new `temp_graph/` directory and wire a simple graph (`user_input → generate_answer`) backed by
  two new ChromaDB collections — `learned_qa` for lessons from accepted answers, `failure_lessons` for lessons
  from rejected answers.
* Read the copied files (`embedding_manager.py`, `llm_caller.py`, `llm_setup.py`, `prompts.py`) and Memora's
  `state.py`/`graph.py`/`nodes/generate_answer.py`/`nodes/user_input.py`/`services/vector_store.py`/
  `services/learned_qa_store.py`/`services/self_learner.py` to confirm the collection/config/tracing patterns
  worth mirroring versus the parts (compression, dedup, validation stages) out of scope for this comparison.
* Built `temp_graph/config.py` (loads `LangMem/.env`), adapted `embedding_manager.py`/`llm_caller.py` (repointed
  imports, stripped tracing instrumentation), trimmed `llm_setup.py` to one `ChatOpenAI` instance and `prompts.py`
  to just `_GENERATE_ANSWER_PROMPT`.
* Created `memory_schemas.py` (`LearnedLesson`, `FailureLesson` Pydantic schemas), `memory_store.py`
  (`MemoryCollection` — cosine ChromaDB wrapper with idempotent `add()` and embedding-similarity `search()`),
  `state.py`, `nodes.py`, `graph.py` (the two-node wiring), `learning.py` (LangMem `create_memory_manager` write-
  back for accept/reject), and `main.py` (REPL: ask → answer → accept/reject → write lesson).
* Verified: all 12 modules parse and import cleanly; `build_graph()` runs end-to-end — the embedding model loads
  (CPU, 384-dim) and both ChromaDB collections initialize (0 entries, fresh store) without error.
* Confirmed `CUSTOM_API_BASE`/`CUSTOM_API_KEY` in `LangMem/.env` are still blank, so a live end-to-end answer
  (and therefore a live LangMem extraction call) has not yet been exercised — graph wiring, collection creation,
  and the embedding pipeline are the only parts actually confirmed working so far.
* Updated `CLAUDE.md`'s "Current State" section to describe the built experiment.
* Discovered, while writing this session's documentation, that `README.md` and `LangMem/requirements.txt` are both
  saved as UTF-16LE rather than UTF-8 (logged as BUG-001; not yet fixed, not currently blocking any workflow).
  Rewriting `README.md`'s content while updating it (see below) did not fix the encoding — it came out UTF-16LE
  again — so BUG-001 remains open with an added root-cause note.
* Tracked in: `temp_graph/` (all 12 files), `CLAUDE.md`; new Architecture.md initial version + 2 changelog
  entries; new Decisions.md ADR-006 through ADR-009; new Bugs.md BUG-001.

---

#### 2026-07-29 — Documentation system established

* Set out to backfill the five-file Markdown tracking system (`Architecture.md`, `Bugs.md`, `Decisions.md`,
  `Status.md`, `Research.md`) for everything that happened since repo creation, using the chat transcript
  (`Chat 33 (July 28).txt`), the LangMem tutorial transcript, and the current state of every file in `temp_graph/`
  and `LangMem/` as source material.
* Read every `temp_graph/` module plus `CLAUDE.md`/`README.md`/`.gitignore`/`LangMem/requirements.txt` directly
  (rather than relying solely on the chat transcript) to ground the docs in actual current file contents, since
  some files (e.g. `requirements.txt`) had changed shape since the chat transcript's intermediate drafts.
* Cross-referenced `../RAG-work/docs/Architecture.md` § "Memory Architecture" (sibling project, read-only) to
  verify the three-layer/four-role memory description already summarized in `CLAUDE.md` against the source.
* Tracked in: `docs/Architecture.md`, `docs/Bugs.md`, `docs/Decisions.md`, `docs/Research.md`, `docs/Status.md`
  (all created this session); `README.md` updated next; `graphify-out/` knowledge graph to follow.

---
