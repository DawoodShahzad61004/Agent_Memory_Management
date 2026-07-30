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

#### 2026-07-29 — MongoDB/store investigation, then `temp_graph/` superseded by native `memora_mini`

* Investigated whether Memora's memory layer could sit behind an officially-supported persistent LangGraph
  `BaseStore` (`PostgresStore`, `MongoDBStore`, `RedisStore`) instead of custom ChromaDB/MongoDB code, with
  `MongoDBStore` the leading candidate since Memora already runs MongoDB. Confirmed a local Community-edition
  `mongod` cannot run `$vectorSearch` (needs the separate `mongot` process); confirmed MongoDB Atlas's free M0
  tier technically *can* run Atlas Vector Search. Decided against it anyway — Atlas is cloud, and the parent
  project's no-data-egress constraint rules out routing memory through any cloud service, free tier or not.
  Decided to keep ChromaDB, and confirmed it already supports full CRUD (add/upsert/update/delete, metadata-only
  update for cheap hit-count bumps) without needing a `BaseStore` wrapper at all. Tracked in: Research.md topics
  5, 6, 8.
* Deep-dived `trustcall`, the library LangMem's `create_memory_manager`/`create_memory_store_manager` depend on
  internally: it does reliable structured output via tool-calling plus JSON-Patch-based repair/update. Confirmed
  every step of that mechanism requires tool-calling, which Memora's actual LLM endpoint does not support (the
  same reason the parent project's own ADR-061 dropped tool-calling from query-variant generation). This makes
  the `langmem` SDK's manager layer categorically unusable here, not just inconvenient. Tracked in: Research.md
  topic 7; Decisions.md ADR-010.
* Set out to build **`memora_mini`**: a from-scratch reimplementation of LangMem's memory taxonomy
  (episodic/semantic/procedural) and its `BaseStore`-shaped four-verb interface, with no `langmem` import
  anywhere, as a sandbox/reference project inside `temp_graph/` (later promoted to repo root — see next entry).
  Followed the prescribed working method: built `config.py`, `embeddings.py`, `store/protocol.py`,
  `store/chroma_store.py`, `memory/recall.py` first, with `tests/test_store.py` + `tests/test_recall.py` green
  (19 tests) before writing any LLM-touching code. Confirmed live, via direct ChromaDB API probing, that pinning
  `hnsw:space="cosine"` on collection creation and asserting it on open works as intended, and that Chroma's
  default space is L2 unless explicitly overridden — the exact failure mode Memora's own collection-creation bug
  had exploited for months.
* Built the LLM layer (`json_fix.py` — fence-strip → `json_repair` → Pydantic validate; `llm.py` — plain
  chat-completions client, no `tools=`/`.bind_tools()` anywhere), then the three-stage memory pipeline
  (`memory/extract.py`, `memory/classify.py`, `memory/apply.py`, `memory/reflect.py`), then the five-node
  `StateGraph` (`graph/state.py`, `nodes.py`, `build.py`), then `ingest.py` plus five `corpus/` fixtures
  (including a deliberate ASD-acronym collision across two documents), then `main.py` (CLI REPL) and `demo.py`
  (scripted end-to-end walkthrough).
* Verified: 56 tests passing after the core build, growing to 58 once semantic-facts seeding and procedural-
  proposal coverage were added. Probed the real LLM endpoint (`CUSTOM_API_BASE`) directly — connection timed out,
  so ran `demo.py` structurally against a fake-model harness instead. That run confirmed all nine of the build
  spec's acceptance-criteria steps end to end: ingest → documents-only answer → dry-run `learn` (writes nothing)
  → live `learn` (episodic populated) → a semantically different rephrasing still recalling the same episodic
  memory → thumbdown-then-reword recalling failure memory with positive redirection in the prompt (the BUG-009
  regression check) → four thumbdowns on one theme consolidating into a single active failure entry → a
  contradicting interaction producing a `CONTRADICTS` verdict, a supersede, and a full audit-log entry → final
  stats showing the active episodic count (4) below the raw candidate count (5).
* Deleted `temp_graph/` entirely (all 12 modules plus its Chroma store, 1,446 lines) as fully superseded.
  Renamed `memora_mini/README.md` → `temp_project_description.md` and `memora_mini/DECISIONS.md` →
  `temp_decision_notedown.md`, pending consolidation into the repo's five-file `docs/` system.
* Tracked in: `memora_mini/` (all ~25 files), `tests/` (6 test modules, 58 tests); Decisions.md ADR-010 through
  ADR-019; Research.md topics 5-8.

---

#### 2026-07-30 — `memora_mini`/`tests` promoted to repo root; documentation consolidated

* Moved `memora_mini/` and `tests/` from being `temp_graph/`-adjacent experiments to first-class top-level
  directories at the repo root, alongside `LangMem/`. Updated `memora_mini/config.py::ENV_PATH` to load the
  repo-root `.env` instead of `LangMem/.env`, and moved the active Python environment from `LangMem/.venv` to a
  root-level `.venv/`. Re-ran the full test suite from the new location: all 58 tests still passed with no
  further code changes needed; the only stale references found were setup commands in
  `temp_project_description.md`, corrected to the new paths. Tracked in: Decisions.md ADR-020.
* Consolidated documentation onto `memora_mini` as the current state of the LangMem evaluation: rewrote
  `docs/Architecture.md`, `docs/Decisions.md`, `docs/Research.md`, `docs/Bugs.md`, and this file, using
  `Chat 33 (July 29).txt`, every current `memora_mini/` module, and `temp_project_description.md`/
  `temp_decision_notedown.md` as source material — the `temp_graph/`-only content these files previously held is
  now marked historical/superseded rather than deleted outright, so the reasoning trail stays intact.
* Fixed BUG-001 for `README.md`: rewrote it from scratch and verified byte-for-byte that it now saves as plain
  UTF-8 (previously UTF-16LE with no BOM). `LangMem/requirements.txt` was left as-is — out of scope, since it
  belongs to now-reference-only tutorial material rather than the active package.
* Deleted `memora_mini/temp_project_description.md` and `memora_mini/temp_decision_notedown.md` once their
  content was folded into `docs/`, leaving a single documentation set. Regenerated `graphify-out/` (repo root
  only) against the updated tree.
* Tracked in: `docs/*.md` (all five updated), `README.md` (rewritten), `graphify-out/` (regenerated).

---
