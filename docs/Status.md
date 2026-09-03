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

#### 2026-07-30 — Mem0 selected as second candidate; `Sample_Coding_Agent/` wired against the hosted Platform client

* Selected **Mem0** as the second candidate to evaluate, per the queued order from Research.md topic 1 / ADR-004,
  now that LangMem/`memora_mini` had reached a stable, tested state (ADR-020).
* Built `Sample_Coding_Agent/main.py`: a single-file LangGraph chatbot with one `chatbot` node that searches
  Mem0 (`mem0.search(..., filters={"user_id": user_id})`), builds a system-prompt context from the results, calls
  the LLM, and writes the turn back via `mem0.add()`. Set up its own `uv`-managed `.venv` (`mem0ai`, `langgraph`,
  `langchain-openai`, `python-dotenv`).
* First run crashed: `httpx.ConnectError: [Errno 11001] getaddrinfo failed` from `MemoryClient()`'s startup auth
  check against `api.mem0.ai` (logged as BUG-002). Diagnosed via `nslookup`/`Get-DnsClientServerAddress`: the
  Wi-Fi adapter's configured DNS resolver is the router's own link-local IPv6 address (`fe80::1`), which is
  intermittently slow/unresponsive (2 of 5 repeated lookups timed out); general connectivity was otherwise fine.
  Not fixed at the network level — left open, since a public-resolver change (8.8.8.8/1.1.1.1) was offered but
  not actioned.
* Also found `.env` wasn't loading: `main.py` called `load_dotenv()` with no path, and the actual `.env` lives at
  the repo root, a level above `Sample_Coding_Agent/` — same layout `temp_graph/` hit (ADR-006). Fixed by
  resolving the repo-root `.env` explicitly by absolute path (BUG-003, now standardized as ADR-023).
* Asked whether self-hosting Mem0 via Docker would resolve the DNS crash: partially — it would remove the
  `api.mem0.ai` dependency specifically, but not `CUSTOM_API_BASE` (the LLM endpoint) or any other external call
  routed through the same flaky resolver. Not acted on yet; `main.py` still uses the hosted `MemoryClient`
  (ADR-022, flagged against the no-cloud-egress precedent from Research.md topic 6).
* Investigated Mem0's actual self-hosted (v3) capabilities in depth after a first-pass answer conflated
  Platform-only features and pre-v3 behavior with the current OSS server. Verified directly against Mem0's
  current source/docs: bundled Postgres+pgvector storage (Neo4j support removed in v3), no built-in
  positive/negative episodic memory type outside the Platform-only Feedback API, write-time consolidation
  reduced to single-pass ADD-only + hash dedup, hybrid semantic+BM25+entity search present but degrading without
  the `nlp` extras, and — contrary to the first answer — **no hard tool-calling requirement** (JSON output
  suffices; `infer=False` is a raw-storage escape hatch). Tracked in Research.md topic 9.
* Captured a live, 5-turn end-to-end conversation (`run_log.txt`) against the hosted Mem0 Platform and a live
  LLM: recall grew across turns (0 → 1 → 3 → 6 → 8 relevant memories found by `mem0.search()`), and the assistant
  correctly recalled cross-turn details (a lasagna complaint, a barista compliment) by the final turn. However,
  every turn's `mem0.add()` logged `0 memories added` despite those same later searches proving new memories were
  in fact written each turn — logged as BUG-004, open, root cause not yet determined.
* Noted, while documenting this pass, that the current `main.py` stores everything in one undifferentiated Mem0
  space (no episodic/semantic/failure split, no accept/reject step) — a thinner mapping onto Memora's four-role
  architecture (ADR-003) than `memora_mini` provides; extending it is the open next step before Mem0 can be
  fairly compared.
* Tracked in: `Sample_Coding_Agent/` (`main.py`, `run_log.txt`, `.venv`); Architecture.md (new Mem0 candidate
  section); Bugs.md BUG-002 through BUG-005; Decisions.md ADR-021 through ADR-023; Research.md topic 9;
  `README.md` updated; `graphify-out/` regenerated.

---

#### 2026-07-30 — Evaluation paused: several candidates lean on tool-calling; local LLM upgrade under consideration

* Paused active evaluation work in this repo. Across the candidates surveyed so far, tool-calling turned out to
  be a recurring dependency — LangMem's SDK layer categorically requires it via `trustcall` (ADR-010), and while
  Mem0's core memory pipeline itself does not (Research.md topic 9), enough of the broader tooling and
  provider-specific behavior in this space assumes it that the constraint keeps resurfacing candidate after
  candidate.
* Upgrading the local LLM server to a tool-calling-capable model is under consideration, which would remove this
  constraint for future candidates — not yet decided.
* No further candidate work (Mem0 or otherwise) planned until that decision is made. `Sample_Coding_Agent/`'s
  Mem0 first pass (BUG-002 through BUG-005) and `memora_mini`'s LangMem reimplementation both remain in their
  current, already-tested states — nothing here needs to be rolled back, just picked back up later.
* Tracked in: Decisions.md ADR-024; `README.md` "Current state" updated to reflect the pause.

---

#### 2026-09-02 — Full paper read-through; contradictory-memory-update procedure designed (not yet implemented)

* Read arXiv:2605.08538v1 ("Human-Inspired Memory Architecture for LLM Agents") in full — the paper
  Architecture.md's Formulae table already draws four equations from — and took notes on mechanics not previously
  captured: consolidation's top/middle/bottom 20/60/20 promote/retain/prune split, the chronological-consistency
  quarantine filter (15-minute TTL against out-of-order/duplicate/causally-inverted events), and the three
  behaviorally distinct zones of the maturation sigmoid (inactive below 0.3, search-only-not-context 0.3-0.5,
  retrievable above 0.5).
* Had a research conversation working through the paper's one acknowledged gap: reconsolidation (§7.2) is
  described only at a high level (60-minute labile window, adaptive blending, outcome reinforcement) with no
  exact contradiction-resolution formula, and the paper itself says the mechanism wasn't meaningfully validated
  because its benchmark has too few cross-session contradictions.
* Produced two design artifacts from that gap: a cache-free graph mechanism for the labile window itself (a
  `ReconsolidationWindow` node plus session-scoped `RETRIEVED`/`OBSERVED` edges standing in for a "recently
  retrieved" cache), and the main deliverable — a full formula set ("versioned semantic reconsolidation with
  bounded access-based inertia") for actually resolving a contradiction: access-based inertia `U_o`, evidence
  strength `E_x`, a sigmoid resolution score `P_new` with supersede/reject/dispute thresholds, a persisted Current
  Belief score `B_x` consumed at retrieval time, and a review-priority score `R_review` for ambiguous cases.
* Flagged explicitly (both in the conversation and in the docs written from it): this procedure is designed but
  untested — it needs to be tried against real traces — and it sits in tension with Architecture.md Principle 4's
  already-decided passive-only conflict handling, which this new procedure would turn into an active, judged
  resolution deferred only to the offline consolidation batch. That tension is unresolved; deciding it needs its
  own ADR before any of this reaches `mem_manage/`.
* Deleted `Handwritten_Notes_Transcription.md` (temp transcription of the paper notes) once its content was
  folded into Research.md topic 10.
* Tracked in: `docs/Research.md` new topic 10; `docs/Architecture.md` § "Formulae" (new row 5) + changelog entry;
  `README.md` updated; `Handwritten_Notes_Transcription.md` deleted.

---

#### 2026-09-03 — `mem_manage/` module implemented: core lifecycle, tests, and CLI verified end-to-end

* Started with a detailed architecture plan (see 2026-09-02's design principles and formulae) and three key
  questions to resolve during implementation: (1) Should the dedup/merge step use an LLM call or deterministic
  Python? (2) How should constants and controls be organized across the module? (3) What test scenarios are
  critical? Working answers: (1) LLM-assisted merge with a deterministic fallback (keeping the low-error-bound
  approach from `memora_mini`, but adding an LLM merge step and a judge to optionally validate it); (2) all
  constants centralized into `mem_manage/config.py`, loaded from the repo-root `.env` per ADR-023 precedent;
  (3) multiple-scenario tests covering parsing, scoring, dedup/merge, decay, pruning, and end-to-end pipelines.
* Built the module with five primary components: (1) **`config.py`** — centralizes IMPORTANCE_WEIGHTS, prune
  percentages, decay constants, merge thresholds, all regex patterns, and env loading; (2) **`importance.py`** —
  five independent scoring functions (recency, frequency, surprise, entity salience, outcome) plus a composite
  weighted sum and the passive-decay formula from the paper; (3) **`memory.py`** — DurableMemory record shape with
  stable content-derived IDs and per-record provenance tracking; (4) **`consolidate.py`** — passive-decay refresh
  and bottom-20%-percentile pruning, controlled via config; (5) **`services/dedup_merge.py`** — rewritten from the
  ground up, replacing the RAG-project's GraphState-based version with one that works over DurableMemory and
  supports: near-duplicate grouping via SequenceMatcher, deterministic Python union for merging, optional
  LLM-assisted merge (with a judge-validated acceptance path), and deterministic fallback on any LLM call failure.
  (6) **`compact.py`** — the public pipeline orchestrator and CLI entry point (`python -m mem_manage.compact <file>`).
* Adapted existing service files to the `mem_manage/` environment: **`embedding_manager.py`** fixed to import config
  from the right path and dropped a dangling tracing hook; **`logger_config.py`** rewritten to drop Langfuse/
  LangSmith/Phoenix tracing (out of scope here) and RAG-pipeline-specific chunking, keeping only the essentials;
  **`llm_setup.py`** trimmed to the two roles actually used (merge and judge); **`llm_caller.py`** left intact per
  the decision to keep the full LangChain/Groq client for robustness.
* Created a comprehensive test suite (108 tests total, 107 passing, 1 skipped pending LLM endpoint): (1) **test_config.py**
  (8 tests) — validates all constants, thresholds, and regex patterns; (2) **test_importance.py** (30 tests) —
  every scoring factor (recency, frequency, surprise, entity extraction, outcome) plus passive decay plus composite
  importance, with edge cases (future timestamps, high-frequency clustering, asymptotic bounds); (3) **test_memory.py**
  (7 tests) — field mapping, ID stability, provenance tracking; (4) **test_consolidate.py** (8 tests) — decay
  application and the exact pruning mathematics (percentile rank, stable sort ties); (5) **test_dedup_merge.py** (18
  tests) — the largest and most involved, covering grouping logic, deterministic union, all LLM-path branches
  (success, judge rejection, LLM failure, disabled flag), fallback chaining; (6) **test_pipeline.py** (7 tests) —
  end-to-end scenarios (duplicate reinforcement, conflict preservation, large-corpus pruning, malformed input
  handling, explicit-provenance edge cases, and both file-based I/O and real-embedding-manager integration). All
  numeric assumptions (SequenceMatcher similarity ratios for near-duplicate thresholds, passive-decay half-life
  math) were verified empirically before locking into the tests, not eyeballed.
* Environment setup and verification: created a fresh Python 3.13 virtual environment via `uv` (matching
  `memora_mini`'s convention), installed all dependencies from a pinned `mem_manage/requirements.txt`, verified all
  imports resolve cleanly (groq, httpx, openai, langchain_openai, sentence_transformers, torch, numpy, dotenv,
  pytest). All 107 tests passed in 17.29 seconds; 1 skipped (the live-LLM integration test, pending a real CUSTOM_API_BASE).
* CLI verification: ran `python -m mem_manage.compact <sample_episodic_log.md>` against a sample 7-entry episodic
  log, observed correct behavior: (1) near-duplicate pair merged successfully via embedding similarity; (2)
  conflicting tabs-vs-spaces entries correctly stayed separate as two versions (similarity below 0.90 threshold);
  (3) LLM merge was attempted (auth failure against non-configured endpoint was caught and logged gracefully);
  (4) fallback to deterministic union executed cleanly; (5) lowest-importance entry (a bare failure with no outcome
  signal) was pruned; final output: 7 records → 5 durable memories, ranked by importance, formatted as Markdown
  headers. This confirmed: parsing, scoring, grouping, merging, decay, pruning, and output all work end to end.
* Knowledge graph updated: ran `graphify update .` to incorporate all new `mem_manage/` modules (and a reflexive
  discovery: `graphify update <subpath>` silently creates a *separate, scoped* graph instead of updating the
  repo-root one — the correct invocation is always `graphify update .` from the repo root, logged for future
  reference in the engineering journal).
* Tracked in: `mem_manage/` (all core and service modules), `mem_manage/tests/` (108 tests), `mem_manage/requirements.txt`
  (pinned to resolved versions); Decisions.md ADR-025 through ADR-030; Architecture.md (updated current state,
  technology stack, changelog); README.md updated; `graphify-out/` regenerated.

---
