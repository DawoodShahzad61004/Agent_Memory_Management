## ADR-001 · Use `uv` for environment and dependency management

| Field | Detail |
|---|---|
| **Decision** | Manage the Python environment and dependencies with `uv`, not raw `pip`/`venv`. |
| **Date** | 2026-07-28 |
| **Context** | The repo starts as a bare Python 3.13 venv with no dependency manifest. Needed a consistent tooling choice before any candidate library got installed. |
| **Options Considered** | `pip` + `venv` (stdlib, no extra tooling) · `uv` (fast, lockfile-friendly, already used by the sibling project). |
| **Chosen Solution** | `uv`-managed `.venv/` per environment (currently `LangMem/.venv`), installed via `uv pip install -r requirements.txt`. |
| **Rationale** | Consistency with how the sibling project (`../RAG-work`) manages its own environment, and `uv`'s speed/lockfile ergonomics matter more here since multiple candidate environments (`LangMem/`, later `Mem0/`, `Letta/`, ...) will need to be created and torn down repeatedly during evaluation. |
| **Impact** | Documented in `CLAUDE.md`. Applies to every future candidate directory's environment, not just `LangMem/`. |

---

## ADR-002 · One top-level directory per evaluated memory library, no shared harness

| Field | Detail |
|---|---|
| **Decision** | Each candidate memory library gets its own independent top-level directory (`LangMem/`, later `Mem0/`, `Letta/`, etc.) with its own environment and experiment code. |
| **Date** | 2026-07-28 |
| **Context** | The repo will evaluate several candidates over time; needed to decide up front whether they'd share a common test harness/interface or stay fully independent. |
| **Options Considered** | Shared abstraction layer/harness that all candidates plug into (more reusable code, but risks biasing each candidate toward whatever interface was designed for the first one) · Fully independent, throwaway experiments per candidate (some duplicated boilerplate, but no shared code masks a candidate's real ergonomics). |
| **Chosen Solution** | Fully independent directories. `CLAUDE.md` explicitly notes "don't assume shared code or a common harness between them unless one is explicitly introduced." |
| **Rationale** | This is an evaluation sandbox, not a product — the goal is to see each library's natural fit against Memora's needs, not to force them through a common shape that could hide real differences in ergonomics or effort. |
| **Impact** | `LangMem/` (env + tutorial material) and `temp_graph/` (the actual LangMem experiment) exist independently at repo root. Future candidates repeat this pattern rather than extending `temp_graph/`. |

---

## ADR-003 · Compare every candidate against Memora's four memory roles, not an arbitrary demo

| Field | Detail |
|---|---|
| **Decision** | Every candidate's toy setup must model the same four roles Memora's real architecture separates memory into: working memory, semantic memory (source documents), episodic/learned memory, and failure memory — rather than building whatever demo a given library's own tutorial suggests. |
| **Date** | 2026-07-28 |
| **Context** | Needed a fixed yardstick so that LangMem, Mem0, Letta, etc. produce genuinely comparable results instead of each showcasing a different, incomparable slice of functionality. |
| **Options Considered** | Follow each library's own official tutorial/demo as-is (fastest to build, but not comparable across candidates) · Force every candidate into Memora's four-role shape (more adaptation work per candidate, but produces an apples-to-apples comparison). |
| **Chosen Solution** | Model Memora's roles (or the subset relevant to a given library's design) in every candidate directory. Reference point is `../RAG-work/docs/Architecture.md` § "Memory Architecture". |
| **Rationale** | The end goal is deciding which library should replace/augment Memora's actual memory layer — a comparison is only useful if every candidate is judged against the same real requirements (e.g., "how does this library's abstraction handle the episodic-write + precedence-on-conflict behavior `learned_qa` currently provides?"). |
| **Impact** | Directly shaped `temp_graph/`'s two ChromaDB collections (`learned_qa`, `failure_lessons`) mapping onto Memora's episodic/failure roles. See ADR-008. |

---

## ADR-004 · LangMem selected as the first candidate to evaluate

| Field | Detail |
|---|---|
| **Decision** | Evaluate LangMem before Mem0, Graphiti, Cognee, or Letta. |
| **Date** | 2026-07-28 |
| **Context** | The `Awesome-Memory-for-Agents` survey (Research.md topic 1) produced more candidates than could be evaluated at once. |
| **Options Considered** | Mem0 (standalone memory service, `memory.add()`/`memory.search()` API) · Graphiti (temporal knowledge graphs, strong at supersession/changing facts) · Cognee (combined vector + knowledge-graph memory) · Letta (full MemGPT-style stateful-agent runtime) · LangGraph Store (storage primitive only) · **LangMem**. |
| **Chosen Solution** | LangMem first. |
| **Rationale** | Native integration with the LangGraph stack Memora already runs on, and its `create_memory_manager()` primitive is explicitly storage-agnostic — it can write into arbitrary storage (including Memora's own MongoDB/ChromaDB shape) rather than forcing adoption of a new store, making it the lowest-friction first comparison. |
| **Impact** | `LangMem/` and `temp_graph/` exist; `Mem0/`, `Graphiti/`, `Cognee/`, `Letta/` do not yet. See Research.md topic 1. |

---

## ADR-005 · `requirements.txt` lives inside `LangMem/`, not at repo root

| Field | Detail |
|---|---|
| **Decision** | Per-candidate dependency manifests live inside that candidate's own directory (`LangMem/requirements.txt`), not shared at the repo root. |
| **Date** | 2026-07-28 |
| **Context** | Asked directly when first generating a `requirements.txt`, given future candidates (Mem0, Letta, ...) will each need their own dependency set. |
| **Options Considered** | Single root-level `requirements.txt` covering all candidates (fewer files, but couples unrelated candidates' dependency sets and versions together) · One `requirements.txt` per candidate directory. |
| **Chosen Solution** | `LangMem/requirements.txt`, installed into `LangMem/.venv`. |
| **Rationale** | Consistent with ADR-002's independent-directories decision — candidates must not share dependency state, since a version conflict between e.g. LangMem's and Mem0's required `langchain-core` should not block either evaluation. |
| **Impact** | `temp_graph/` (repo root) runs using the interpreter at `LangMem/.venv/Scripts/python.exe`, not a root-level environment. The file's currently a pinned `uv pip freeze`-style manifest (144 packages) reflecting the fully installed working environment, not the original loose top-level-only draft. |

---

## ADR-006 · `temp_graph/` loads `LangMem/.env` explicitly instead of duplicating it

| Field | Detail |
|---|---|
| **Decision** | `temp_graph/config.py` points `python-dotenv` at `../LangMem/.env` rather than `temp_graph/` having its own `.env` copy. |
| **Date** | 2026-07-29 |
| **Context** | `temp_graph/` is a separate top-level experiment directory from `LangMem/`, but needs the same provider credentials (`CUSTOM_API_BASE`, `CUSTOM_API_KEY`, etc.) already set up there. |
| **Options Considered** | Duplicate a `.env` file into `temp_graph/` (simpler mental model per-directory, but risks the two copies drifting out of sync) · Load `LangMem/.env` explicitly via an absolute path in `config.py`. |
| **Chosen Solution** | `ENV_PATH = _PROJECT_ROOT.parent / "LangMem" / ".env"` in `temp_graph/config.py`. |
| **Rationale** | Single source of truth for credentials while `LangMem/` is the active candidate; avoids silently-stale duplicate secrets. |
| **Impact** | `temp_graph/` cannot run standalone without `LangMem/` present alongside it — an intentional coupling since `temp_graph/` *is* the LangMem experiment, not a generic harness (see ADR-002). |

---

## ADR-007 · Scope the graph to two nodes (`user_input → generate_answer`) instead of replicating Memora's full pipeline

| Field | Detail |
|---|---|
| **Decision** | `temp_graph/graph.py` implements only `user_input → generate_answer`, not Memora's full retrieval/compression/validation pipeline (query variants, NAC/DC/LBC compression, dedup-merge, draft/quality-check stages, etc.). |
| **Date** | 2026-07-29 |
| **Context** | `temp_graph/` copies several service modules from `../RAG-work/app_workflow/services/` but the evaluation only needs to exercise the memory read/write contract, not the entire agent pipeline. |
| **Options Considered** | Port Memora's full multi-stage LangGraph pipeline into `temp_graph/` for maximum fidelity (much larger surface to adapt and debug, most of it irrelevant to comparing memory libraries) · A minimal two-node graph that still reads from and writes to the same two memory collections. |
| **Chosen Solution** | Two nodes only: `user_input_node` (trims input) and `generate_answer_node` (searches both memory collections, builds context, calls the LLM with Memora's grounding prompt). |
| **Rationale** | The thing under evaluation is the memory-store abstraction (extraction, storage, retrieval, precedence), not the retrieval-compression pipeline surrounding it — replicating the full pipeline would add adaptation risk without adding comparison value. |
| **Impact** | `temp_graph/state.py`'s `GraphState` is intentionally minimal (`user_input`, `answer`) compared to Memora's much larger `GraphState`. Retrieval validation, dedup, and compression stages are simply absent from this experiment. |

---

## ADR-008 · Two separate cosine-distance ChromaDB collections, mirroring Memora's collection pattern

| Field | Detail |
|---|---|
| **Decision** | Persist two independent ChromaDB collections — `learned_qa` (accepted-answer lessons) and `failure_lessons` (rejected-answer lessons) — both cosine distance, under `temp_graph/chroma_store/`. |
| **Date** | 2026-07-29 |
| **Context** | Needed persistent storage for the episodic/failure memory roles established in ADR-003, in a shape comparable to Memora's actual collections. |
| **Options Considered** | A single combined collection with a `source` metadata field distinguishing learned vs. failure entries (fewer moving parts) · Two separate collections, one per role. |
| **Chosen Solution** | Two collections via a shared `MemoryCollection` wrapper class (`temp_graph/memory_store.py`), each created with `{"hnsw:space": "cosine"}` metadata — directly mirroring `../RAG-work/app_workflow/services/learned_qa_store.py`'s canonical metadata shape (minus its L2→cosine migration logic, unneeded for fresh collections). |
| **Rationale** | Matches Memora's actual retrieval pattern, where `learned_qa` is queried independently from other memory (see `../RAG-work/docs/Architecture.md` § "Memory Architecture"), and keeps the comparison against Memora faithful at the storage-shape level, not just the API level. |
| **Impact** | `temp_graph/graph.py` creates both collections at startup via `build_graph()`; `temp_graph/nodes.py`'s `generate_answer_node` queries both independently and tags each retrieved block with its source collection in the prompt context. |

---

## ADR-009 · Use LangMem's `create_memory_manager` (insert-only) for the first pass

| Field | Detail |
|---|---|
| **Decision** | `temp_graph/learning.py` uses `langmem.create_memory_manager()` with `enable_inserts=True, enable_updates=False, enable_deletes=False` for both the learned-lesson and failure-lesson managers. |
| **Date** | 2026-07-29 |
| **Context** | LangMem exposes both a lower-level `create_memory_manager()` (returns structured memories, storage-agnostic) and a higher-level `create_memory_store_manager()` (owns a LangGraph `Store`, supports background processing). It also supports update/delete/consolidation of existing memories, not just inserts. |
| **Options Considered** | `create_memory_store_manager` bound directly to a LangGraph `Store` (less custom glue code, but couples this experiment to LangGraph's store abstraction rather than the existing `MemoryCollection`/ChromaDB shape) · `create_memory_manager` with full insert/update/delete enabled (more faithful to LangMem's intended "memory evolution" behavior, but adds consolidation logic to debug before the basic contract is even verified) · `create_memory_manager`, insert-only. |
| **Chosen Solution** | `create_memory_manager`, insert-only, matching the official tutorial's first-pass simplicity (see Research.md topic 3). |
| **Rationale** | Keeps the write-back path storage-agnostic so it plugs into the existing `MemoryCollection`/ChromaDB wrapper instead of adopting LangGraph's `Store` abstraction, and defers update/delete/consolidation behavior until the basic insert contract (schema → structured memory → embed → store) is confirmed working end-to-end. |
| **Impact** | `temp_graph/learning.py`'s `record_accepted()`/`record_rejected()` only ever add new memories; there is currently no path for LangMem to merge, update, or remove an existing `learned_qa`/`failure_lessons` entry. Revisit if/when this experiment needs to demonstrate LangMem's consolidation behavior specifically. |

---

## ADR-010 · Reject the `langmem` SDK's manager layer; reimplement its taxonomy natively as `memora_mini`

| Field | Detail |
|---|---|
| **Decision** | Stop building on `langmem.create_memory_manager()`/`create_memory_store_manager()`. Adopt LangMem's memory taxonomy (episodic/semantic/procedural) and its `BaseStore`-shaped four-verb interface, but implement both from scratch in a new package, `memora_mini/`. Do not import or install `langmem`. |
| **Date** | 2026-07-29 |
| **Context** | `temp_graph/` (ADR-009) proved the basic contract works, but a deeper investigation (`Chat 33 (July 29).txt`; Research.md topic 7) established that `create_memory_manager`/`create_memory_store_manager` are built on `trustcall`, which is built on tool-calling (`.bind_tools()`, internal patch-tool schemas). Memora's actual production LLM endpoint is a self-hosted OpenAI-compatible server with **no tool-calling support**, which was already the reason ADR-061 (parent project) removed tool-calling from query-variant generation. |
| **Options Considered** | (a) Keep using `create_memory_manager` as-is · (b) build a shim that fakes tool-calling on top of the plain-JSON endpoint so `trustcall` still works · (c) adopt LangMem's taxonomy and store-interface *shape* only, and implement extraction/classification/apply natively · (d) drop LangMem entirely and design a memory system from scratch, uninformed by it. |
| **Chosen Solution** | (c) |
| **Rationale** | (a) is simply unavailable against this endpoint. (b) means maintaining a compatibility shim against two upstream libraries (`langmem` and `trustcall`) just to reach an abstraction the project would still have to debug from the outside — worse than owning the code directly. (d) throws away a taxonomy (episodic/semantic/procedural, `BaseStore`'s verb shape) that is a demonstrably better fit than Memora's current ad-hoc three-collection split, for no benefit. The ideas from LangMem are portable even though the package is not. |
| **Impact** | `temp_graph/` (the `langmem`-dependent prototype) was deleted entirely. `memora_mini/` — ~900 lines across `store/`, `memory/`, `graph/` — is built to reach the same evaluation goal without the dependency. Every subsequent decision below (ADR-011 through ADR-020) is a design choice made inside that reimplementation. |

---

## ADR-011 · Store interface signatures held byte-compatible with LangGraph `BaseStore`

| Field | Detail |
|---|---|
| **Decision** | `memora_mini/store/protocol.py`'s `MemoryStore` Protocol uses exactly `BaseStore`'s four verb names, parameter ordering, and keyword-only markers (`put`, `get`, `search(*, query, filter, limit)`, `delete`). |
| **Date** | 2026-07-29 |
| **Options Considered** | A Protocol shaped only for what this code actually needs (e.g. `search(ns, query, k)`, simpler) · a literal `BaseStore` subclass (drags in LangGraph's async surface and `Op`/batch machinery for no benefit here) · a signature-compatible Protocol. |
| **Chosen Solution** | Signature-compatible Protocol. |
| **Rationale** | A Protocol shaped only for this code's own needs would make a later swap to a real `BaseStore` a rewrite of every call site. Matching signatures costs one awkward parameter (`filter` shadows the builtin) and buys a genuine drop-in path: if a tool-calling-capable model becomes available later, a thin `BaseStore` subclass over the same Chroma collections lets LangMem's managers attach without touching a single caller. |
| **Impact** | `store/protocol.py`. Pinned by `tests/test_store.py::test_store_satisfies_the_protocol`, which asserts the parameter list rather than relying on duck-typing alone. |

---

## ADR-012 · Supersede, not delete, as the memory lifecycle

| Field | Detail |
|---|---|
| **Decision** | Superseding a memory sets `active=False` and `superseded_by=<new_key>` on the old record and inserts a new one. `delete()` exists on the store interface but is for operator cleanup only — the write pipeline never calls it. All recall filters `active=True` by default. |
| **Date** | 2026-07-29 |
| **Options Considered** | Hard delete on contradiction · in-place update of the existing record · supersede-with-tombstone · versioned records with an explicit generation counter. |
| **Chosen Solution** | Supersede with tombstone. |
| **Rationale** | The failure mode being designed against is a *wrong classification*, not a wrong memory — the classifier is an 8B model. A hard delete makes a bad `CONTRADICTS` verdict unrecoverable, which is the insert-only problem (that this whole reimplementation exists to fix) inverted into an equally permanent mistake. In-place update loses the old text, so an audit log can't show what changed. Tombstones cost only storage, which is free in this sandbox. |
| **Impact** | Every namespace carries `active`/`superseded_by`. Storage grows monotonically — acceptable here; a periodic hard-delete sweep over long-superseded records is the obvious production follow-up if this ports back to Memora. |

---

## ADR-013 · Classification is per-pair and single-token

| Field | Detail |
|---|---|
| **Decision** | `memory/classify.py` makes one LLM call per `(candidate, neighbour)` pair, and that call returns exactly one of four enum tokens (`DUPLICATE`/`CONTRADICTS`/`REFINES`/`UNRELATED`). |
| **Date** | 2026-07-29 |
| **Options Considered** | One call classifying a candidate against all of its neighbours at once · one call doing extract + reconcile + merge together, i.e. what `create_memory_manager` itself does · one call per pair, single token. |
| **Chosen Solution** | Per-pair, single-token. |
| **Rationale** | Against an 8B model, a call that must align a candidate with several neighbours *and* emit structured output fails in ways that are hard to attribute to a specific cause. A single token has exactly one failure mode — unrecognised text — with an obvious, safe fallback (`UNRELATED` → insert, never mutate); the cost is `candidates × CLASSIFY_NEIGHBOURS` calls per interaction, acceptable because reflection runs offline, never in the request path. |
| **Impact** | `memory/classify.py`; `strongest()` resolves disagreement across neighbours by priority (`CONTRADICTS > REFINES > DUPLICATE`). If a stronger model becomes available later, a batched form is a strictly cheaper drop-in and only this module would change. |

---

## ADR-014 · `REFINES` merges deterministically in Python, never via an LLM call

| Field | Detail |
|---|---|
| **Decision** | The merged record produced by a `REFINES` supersede is a plain Python union — concatenate text, union list fields, take `max()` confidence, preserve `hit_count` — with no LLM call anywhere in `apply.py`. |
| **Date** | 2026-07-29 |
| **Options Considered** | An LLM call producing a clean, synthesised merged answer · a deterministic Python union · keep both records separately and let recall's ranking sort it out. |
| **Chosen Solution** | Deterministic Python union. |
| **Rationale** | The constraint that `apply.py` is the *only* module that writes memory is only meaningful if `apply.py` cannot fail nondeterministically. Putting an LLM merge call inside the write path reintroduces exactly the nondeterminism that constraint exists to remove. The cost is uglier merged text (two concatenated answers rather than one synthesised one), which recall tolerates fine because matching happens on embeddings, not surface text. |
| **Impact** | `memory/apply.py::_merge`. There is deliberately no merge prompt in `prompts.py`. If merged entries visibly degrade answer quality, the fix is to move an LLM merge step into `classify.py`, passing pre-merged text into `plan()` — not to add one to `apply.py`. |

---

## ADR-015 · Semantic memory is curated by hand, not extracted automatically

| Field | Detail |
|---|---|
| **Decision** | No automatic extraction path writes to the `semantic` namespace. Facts are seeded from `facts.py` (`SEED_FACTS`) and added at runtime only via the REPL's `fact` command. |
| **Date** | 2026-07-29 |
| **Options Considered** | Mine facts from the corpus automatically at ingest time · extract facts during reflection alongside episodic memories · curate them by hand. |
| **Chosen Solution** | Curate by hand. |
| **Rationale** | Asked to mine "domain facts" from a chunk, an 8B model restates whatever it just read, which duplicates the `documents` collection into a namespace that then outranks it in the generation prompt. The facts actually worth this namespace's existence — the ASD acronym collision, the evidence-grade rule — require knowing something about the corpus *as a whole*, which single-chunk extraction structurally cannot see. |
| **Impact** | `facts.py`, `memora_mini/corpus/`. The semantic namespace stays small and hand-owned. If the corpus grows, a corpus-wide disambiguation pass (clustering acronyms with divergent neighbour clusters) is the natural automation path — a clustering job, not an LLM-per-chunk job. |

---

## ADR-016 · Procedural memory is proposed deterministically and never auto-applied

| Field | Detail |
|---|---|
| **Decision** | When an active failure memory's `hit_count` reaches `PROCEDURAL_PROPOSAL_HITS`, reflection emits a `PromptRevision` with `approved=False`. Nothing in the query graph reads the `procedural` namespace. |
| **Date** | 2026-07-29 |
| **Options Considered** | An LLM call proposing prompt revisions · a deterministic proposal derived from a recurring-failure-theme threshold · auto-apply approved revisions at generation time · no procedural memory at all. |
| **Chosen Solution** | Deterministic proposal from a threshold, never applied. |
| **Rationale** | A system that rewrites its own system prompt from 8B-model output has no stable baseline left to evaluate against — which defeats the point of a comparison sandbox. Emitting the proposal is still worth doing: it surfaces "this failure theme keeps recurring" as a reviewable artifact. Deriving the trigger from a `hit_count` threshold rather than an LLM judgment keeps it free, deterministic, and reproducible. |
| **Impact** | `memory/reflect.py::propose_prompt_revisions`. Pinned by `tests/test_reflect.py::test_procedural_memory_is_never_injected_into_generation`. Wiring an approval workflow into actual generation is left as a deliberate, separate decision for whoever ports this into Memora. |

---

## ADR-017 · Failure injection carries derived `missing_information`, capped at 2, phrased positively

| Field | Detail |
|---|---|
| **Decision** | Prompt injection for failure memory uses a derived `missing_information` noun phrase — never the raw `user_feedback` text — phrased as positive redirection ("prior attempts missed X; seek and state X"), capped at `MAX_FAILURE_INJECTIONS = 2` and selected by strength score. |
| **Date** | 2026-07-29 |
| **Options Considered** | Inject raw `user_feedback` verbatim, which is what Memora's current `user_thumbdowns`/`failed_variants` injection does · inject a "do not do X" blocklist · inject the derived `missing_information` field as positive redirection. |
| **Chosen Solution** | Derived `missing_information`, positive phrasing, capped. |
| **Rationale** | Raw feedback is a complaint aimed at a person — the wrong shape for redirecting retrieval, and it drags tone and irrelevant detail into the prompt. Negative-only phrasing ("do not omit dosing") measurably fails to change small-model behaviour; positive redirection is the form that actually works. The cap exists because embedding-based recall surfaces far more failure hits than Memora's exact-string match ever did, and Memora's own pipeline already hit prompt-bloat problems past roughly 1,800 tokens against an 8B instruction-following ceiling. |
| **Impact** | `memory/schemas.py::FailureMemory.missing_information`, `prompts.REDIRECTION_LINE`/`REDIRECTION_BLOCK`, `graph/nodes.py::generate`. Pinned by `tests/test_graph.py` (cap honoured; raw feedback text never reaches the prompt). |

---

## ADR-018 · Cosine is asserted on open, not migrated

| Field | Detail |
|---|---|
| **Decision** | `store/chroma_store.py::open_collection()` pins `hnsw:space="cosine"` on every `get_or_create_collection` call and raises `RuntimeError` if an opened collection reports any other space. |
| **Date** | 2026-07-29 |
| **Options Considered** | Assert and fail loudly · snapshot-and-rebuild migration logic, mirroring `../RAG-work/app_workflow/services/learned_qa_store.py` · compute distance-appropriate scores per collection at each call site. |
| **Chosen Solution** | Assert and fail loudly. |
| **Rationale** | This sandbox has no legacy data, so migration code here could never actually be exercised, and untested migration code cannot be trusted. Per-collection score handling would spread the assumption `score = 1 - distance` across every call site — exactly the pattern that let Memora's own L2-vs-cosine bug silently corrupt ranking for months. One factory, one assertion, one place to look. |
| **Impact** | `store/chroma_store.py::open_collection` is the only code path in the package that creates a collection. **When porting this back to Memora, keep Memora's existing migration logic instead** — it handles real pre-existing data that this assertion would simply reject. |

---

## ADR-019 · Interactions are buffered in Chroma; the audit trail is a JSONL log, not a memory namespace

| Field | Detail |
|---|---|
| **Decision** | Pending (not-yet-reflected) interactions live in a Chroma collection (`("memora", DOMAIN, "interactions")`) that is explicitly *not* one of the four memory namespaces. Proposed and applied memory operations are appended to `memory_audit.jsonl` on disk, not stored in Chroma. |
| **Date** | 2026-07-29 |
| **Options Considered** | Interactions in MongoDB, mirroring Memora's own behavior · interactions as a fifth memory namespace · interactions in a non-memory Chroma collection, with the audit trail also in Chroma · interactions in Chroma, audit trail as an append-only JSONL file. |
| **Chosen Solution** | Non-memory Chroma collection for interactions; JSONL file for the audit trail. |
| **Rationale** | MongoDB is excluded by the sandbox's hard constraint (ChromaDB is the only datastore). Making interactions a memory namespace would let raw, unclassified interactions leak into recall alongside actual memories. The audit trail is append-only, read only by humans, and never read back by any code path for behaviour — a log sink, not a datastore — so embedding it into a vector store would buy nothing and would require embedding text nobody ever searches. |
| **Impact** | `store/namespaces.py::INTERACTIONS`, `memory/apply.py::_audit`, `config.AUDIT_LOG_PATH`. This is the one place the "ChromaDB only" rule is interpreted rather than followed literally — flagged here deliberately, since it is exactly the kind of choice a reviewer should push back on. |

---

## ADR-020 · Delete `temp_graph/` entirely; promote `memora_mini/` to a first-class repo-root package

| Field | Detail |
|---|---|
| **Decision** | Remove `temp_graph/` (all 12 modules and its Chroma store) rather than keep it as historical reference, and move `memora_mini/` (and its `tests/`) out from being a `temp_graph/`-adjacent experiment into a top-level directory at the repo root, alongside `LangMem/`. |
| **Date** | 2026-07-29 / 2026-07-30 |
| **Options Considered** | Keep `temp_graph/` around as a dead-but-documented historical artifact · keep `memora_mini/` nested under/alongside `temp_graph/` · delete `temp_graph/` and promote `memora_mini/` to repo root. |
| **Chosen Solution** | Delete `temp_graph/`; promote `memora_mini/` to repo root. |
| **Rationale** | `memora_mini/` doesn't just replace `temp_graph/`'s functionality — it exists specifically *because* `temp_graph/`'s core approach (the `langmem` SDK's manager layer) turned out to be unusable against Memora's real constraints (ADR-010). Keeping a dead prototype around that took a rejected approach added confusion without adding evaluation value; the reasoning is fully captured in ADR-010 and Research.md topic 7 instead. Since `memora_mini/` no longer depends on anything under `LangMem/` except its `.env` file's contents, keeping it nested added a layer of indirection with no benefit. |
| **Impact** | `temp_graph/` no longer exists in the repo (1,446 lines removed). `memora_mini/config.py::ENV_PATH` now resolves the repo-root `.env` instead of `LangMem/.env`; the active environment moved from `LangMem/.venv` to a root-level `.venv/`. All 58 tests were re-verified passing from the new location with no further code changes needed. `memora_mini/`'s own `README.md`/`DECISIONS.md` were renamed to `temp_project_description.md`/`temp_decision_notedown.md` and, once folded into this five-file `docs/` system, deleted (see ADR-010's changelog entry in Architecture.md and Status.md, 2026-07-30). |

---

## ADR-021 · Mem0 selected as the second candidate to evaluate

| Field | Detail |
|---|---|
| **Decision** | Evaluate Mem0 next, after LangMem/`memora_mini`. |
| **Date** | 2026-07-30 |
| **Context** | Research.md topic 1's candidate survey queued Mem0, Graphiti, Cognee, and Letta behind LangMem; LangMem's evaluation (`memora_mini`) reached a stable, tested state (Decisions.md ADR-020), freeing capacity to move to the next candidate. |
| **Options Considered** | Continue refining `memora_mini` further · move to Graphiti (temporal knowledge graphs) · move to Mem0 (standalone `memory.add()`/`memory.search()` service). |
| **Chosen Solution** | Mem0. |
| **Rationale** | Mem0 was already identified in Research.md topic 1 as the most direct structural alternative to `memora_mini`'s own `learned_qa`-style pipeline — a standalone add/search memory service rather than a knowledge-graph or full agent runtime — making it the next-lowest-friction comparison per the queued order. |
| **Impact** | `Sample_Coding_Agent/` created as Mem0's independent top-level candidate directory, per ADR-002's one-directory-per-candidate pattern. |

---

## ADR-022 · Mem0's first pass uses the hosted Platform client; self-hosted Docker deferred

| Field | Detail |
|---|---|
| **Decision** | `Sample_Coding_Agent/main.py` wires against Mem0's hosted Platform (`mem0.MemoryClient`, `api.mem0.ai`) for the first pass, rather than starting directly with Mem0's self-hosted Docker OSS stack (Postgres + pgvector). |
| **Date** | 2026-07-30 |
| **Context** | Getting the first pass wired end-to-end (`mem0.search()`/`mem0.add()` inside a LangGraph node) was the immediate goal; `MemoryClient()` is the fastest path to that, requiring only an API key rather than standing up a Docker Compose stack. |
| **Options Considered** | Hosted Platform client (fastest to wire, but sends interaction content to a third-party cloud service) · self-hosted Docker OSS stack (fully local, consistent with the no-cloud-egress precedent from Research.md topic 6/ADR-019, but more setup before any comparison could begin). |
| **Chosen Solution** | Hosted Platform client, for now. |
| **Rationale** | This was a pragmatic first-pass sequencing choice, not a considered rejection of the no-cloud precedent — the tradeoff wasn't weighed the way ADR-019's MongoDB Atlas decision was. It is flagged here explicitly because it currently contradicts that precedent, and should not be read as a signal that the constraint no longer applies. |
| **Impact** | `Sample_Coding_Agent/main.py:23`. `run_log.txt`'s captured conversation sent real interaction content to `api.mem0.ai`. Investigated (Research.md topic 9) whether self-hosted Docker would satisfy the same requirements — findings suggest yes (bundled Postgres+pgvector, no tool-calling requirement) — but the switch has not been made, and evaluation is now paused (ADR-024) before it could be. Revisit before treating this candidate's results as comparable to `memora_mini`'s fully-local ones. |

---

## ADR-023 · `Sample_Coding_Agent/` loads the repo-root `.env` explicitly, same pattern as `temp_graph`/`memora_mini`

| Field | Detail |
|---|---|
| **Decision** | `Sample_Coding_Agent/main.py` resolves the repo-root `.env` by absolute path (`Path(__file__).resolve().parent.parent / ".env"`) rather than relying on `load_dotenv()`'s default cwd-based search. |
| **Date** | 2026-07-30 |
| **Context** | Fixing BUG-003, where the default `load_dotenv()` call silently found nothing since `Sample_Coding_Agent/` is a sibling, not a parent, of the repo-root `.env`. |
| **Options Considered** | Give `Sample_Coding_Agent/` its own `.env` copy · load the repo-root `.env` by absolute path. |
| **Chosen Solution** | Load the repo-root `.env` explicitly. |
| **Rationale** | Same reasoning as ADR-006: a single source of truth for shared credentials (`CUSTOM_API_BASE`/`CUSTOM_API_KEY`) avoids two copies drifting out of sync, now that `memora_mini` has also standardized on the repo-root `.env` (ADR-020's changelog). Establishes this as the repo-wide convention for every future candidate directory, not just a one-off fix. |
| **Impact** | `Sample_Coding_Agent/main.py:11`. Future candidate directories (Letta, Graphiti, etc.) should follow the same pattern rather than each inventing their own `.env` discovery. |

---

## ADR-024 · Pause external memory-library evaluation pending a local LLM upgrade decision

| Field | Detail |
|---|---|
| **Decision** | Pause further candidate evaluation work in this repo (Mem0 or otherwise) until a decision is made on upgrading the local LLM server to a tool-calling-capable model. |
| **Date** | 2026-07-30 |
| **Context** | Tool-calling support (or its absence) has now shaped multiple candidates' outcomes: it categorically ruled out LangMem's SDK manager layer (ADR-010, via `trustcall`), and even where it isn't a hard requirement (Mem0's core pipeline — Research.md topic 9), enough of the broader tooling and provider-specific behavior in this space assumes it that the current no-tool-calling local endpoint keeps becoming a recurring constraint to design around rather than a one-off blocker. |
| **Options Considered** | Keep evaluating additional candidates (Graphiti, Letta, etc.) against the current no-tool-calling endpoint, designing around the constraint each time as done for LangMem/Mem0 · pause new candidate work and decide on a local LLM upgrade first, since a tool-calling-capable model would remove the constraint for every future candidate at once rather than one at a time. |
| **Chosen Solution** | Pause; decide on the LLM upgrade first. |
| **Rationale** | Working around the no-tool-calling constraint per candidate (ADR-010's `memora_mini` reimplementation, Mem0's JSON-only extraction path) is real, repeated engineering cost. If a tool-calling-capable local model is adopted, that cost disappears for every remaining candidate at once, so resolving the model question first is higher-leverage than continuing to evaluate against a constraint that may not exist much longer. |
| **Impact** | No new candidate directories planned until this is decided. `memora_mini` (LangMem) and `Sample_Coding_Agent/` (Mem0, first pass) are left in their current states — both already tested/working within their own scope, not blocked or broken by the pause. Revisit this ADR once the LLM upgrade decision is made, either resuming with Graphiti/Letta/etc. against an upgraded endpoint, or continuing the no-tool-calling-constrained approach deliberately. |

---

## ADR-025 · Move from evaluation to implementation; build `mem_manage/` as a standalone module for coding agents

| Field | Detail |
|---|---|
| **Decision** | Repurpose the repository from an evaluation sandbox (comparing LangMem, Mem0, etc. against Memora's existing memory layer) to building a single, complete module `mem_manage/` targeted specifically at coding agents. Keep the evaluation work (`memora_mini/`, `Sample_Coding_Agent/`, `LangMem/`) as prior art, but cease new candidate evaluation. |
| **Date** | 2026-09-02 / 2026-09-03 |
| **Context** | The evaluation stalled on a technical constraint (tool-calling support) that kept resurfacing, but the evaluation also produced a clear finding that all candidates shared the same architectural flaw: they accumulate memory indefinitely and never forget on purpose. This is the real gap to solve. Rather than continue searching for an off-the-shelf candidate, the repo should build the missing piece directly. |
| **Options Considered** | Continue the evaluation against multiple candidates · build a lightweight adapter around an existing candidate (e.g., wrap Mem0's API) · build a standalone module from the ground up, informed by prior work and the paper. |
| **Chosen Solution** | Build standalone. |
| **Rationale** | None of the candidates actually solve the core problem (they don't forget); wrapping one would inherit its limitations; building from the ground up means every design decision is intentional and grounded in the paper and this repo's prior art, with no inherited tech debt. The evaluation work stays in the repo as evidence of the alternatives considered. |
| **Impact** | `mem_manage/` is the new deliverable. `memora_mini/`, `Sample_Coding_Agent/`, and `LangMem/` are retained as prior art but not extended. See ADR-020 and §3 of Architecture.md for what carries forward from prior work into the new module. |

---

## ADR-026 · Centralize all configuration into `mem_manage/config.py`; load from repo-root `.env`

| Field | Detail |
|---|---|
| **Decision** | All constants, thresholds, weights, decay parameters, merge-similarity cutoffs, entity-extraction regex patterns, and env-variable loading are centralized in a single `config.py` at the `mem_manage/` root. No other module in the package reads `os.environ` directly. The repo-root `.env` is resolved by absolute path per ADR-023 precedent. |
| **Date** | 2026-09-03 |
| **Context** | The first pass of `importance.py` (2026-09-02, a code snippet) had hardcoded constants scattered throughout, and the copied service files (`llm_setup.py`, etc.) each tried to import config from different paths, creating fragility. `memora_mini/config.py` already demonstrated the single-source-of-truth pattern; applying it here eliminates a source of bugs and makes tuning (especially for the paper-derived constants, which need re-derivation against coding-agent traces) straightforward. |
| **Options Considered** | Leave constants inline where they're used · use environment variables throughout · use a YAML/TOML config file · centralize into one `config.py` module. |
| **Chosen Solution** | Single `config.py`, loaded once at import time. |
| **Rationale** | Python module-level constants are fast, IDE-searchable, and override-friendly via env variables when needed; YAML/TOML adds a format to learn and maintain; scattering via env-only is error-prone for compound defaults. Follows established pattern from `memora_mini/config.py`. |
| **Impact** | `mem_manage/config.py` is the single place to adjust importance weights, decay rates, merge thresholds, and feature flags. Every test and every CLI invocation sees the same configuration baseline. Swapping test-vs-production constants becomes a single env-file edit. |

---

## ADR-027 · Dedup/merge uses LLM-assisted synthesis with deterministic fallback, not pure Python

| Field | Detail |
|---|---|
| **Decision** | When a group of near-duplicate memories is identified for merging, the first choice is an LLM call to synthesize a unified statement (the "merge" step); if that call fails or returns invalid output, or if merging is explicitly disabled, fall back to a deterministic Python union (string concatenation + field unions). The judge validates the LLM merge; if rejected, the fallback is used. |
| **Date** | 2026-09-03 |
| **Context** | ADR-014 established that `memora_mini` merges via deterministic Python (no LLM call in the write path) to keep mutation nondeterministic and safe for an offline consolidation pipeline. However, that produces uglier merged text (two concatenated answers rather than one synthesised answer). The trade-off was specifically about write-path latency and reliability; an offline consolidation step has more latitude. The implementation should offer both: try the LLM first (since it's offline), fall back to deterministic if anything fails (maintaining safety), and let a judge optionally validate the result (implementing Principle 4's deferred conflict resolution, but with an extra validation layer). |
| **Options Considered** | Pure deterministic merge as in ADR-014 (safest, ugliest results) · pure LLM merge (better output, but any failure breaks the consolidation run) · LLM-first with deterministic fallback (takes the upside, contains the downside). |
| **Chosen Solution** | LLM-first with fallback, optionally judge-validated. |
| **Rationale** | Offline pipelines can afford LLM calls; fallback ensures no consolidation run ever fails because the LLM was unreachable or misbehaved; judge validation is an optional extra check. The judge sees *only* whether the merge makes sense (one coherent statement?), not whether it's *true* — that's deferred to Principle 4's recency-based conflict resolution. |
| **Impact** | `services/dedup_merge.py::merge_group()` is the decision point. Parameter `use_llm` controls whether to attempt the LLM path; `judge_llm` controls whether to validate the result. Every test covers the failure paths; the CLI defaults to `use_llm=True, judge_llm=False` (fast path, no double-call overhead). |

---

## ADR-028 · Importance scoring is computed once at store time; activation initializes from it

| Field | Detail |
|---|---|
| **Decision** | The five-factor composite-importance score (`S(e) = Σwᵢfᵢ(e)` from the paper) is computed once when a DurableMemory record is first created (right after consolidation, before store). This becomes the `importance` field on the record; `activation` (Principle 2) initializes from it. Importance is never recomputed; only activation evolves. |
| **Date** | 2026-09-03 |
| **Context** | The paper computes importance at consolidation time; recency, frequency, surprise, and entity salience all benefit from seeing the full corpus (post-dedup, post-merge). Computing it only once (not on every access) keeps it fast and deterministic. Separating importance (the initial signal) from activation (the ongoing state) keeps Principle 2's "single scalar" clean: activation alone evolves on retrieval, interference, and decay; importance is a locked-in foundation. |
| **Options Considered** | Compute importance on every access (accurate but slow) · compute at store time only · compute every consolidation cycle (expensive, defeats the purpose of offline). |
| **Chosen Solution** | At store time only. |
| **Rationale** | Fast, deterministic, faithfully separates the one-time signal (importance) from the ongoing state (activation). If importance-weight tuning is needed, a maintenance cycle can recompute all records' importance from their current content (deferred work, not part of v1). |
| **Impact** | `importance.py::composite_importance()` is called from `memory.py::build_durable_memories()` exactly once per record; its result is stored and never recomputed. |

---

## ADR-029 · Test suite covers numeric assumptions empirically; no eyeballed thresholds

| Field | Detail |
|---|---|
| **Decision** | Every numeric assumption in the test suite — similarity ratios for duplicate-detection thresholds, passive-decay half-life math, entity-salience scaling — is verified empirically (via actual SequenceMatcher runs, decay calculations, etc.) before being locked into a test, not guessed or assumed. |
| **Date** | 2026-09-03 |
| **Context** | The `dedup_merge.py` tests use a 0.90 similarity threshold for grouping near-duplicates; that threshold's actual effect on a diverse set of test entries needed to be checked to avoid false merges and false non-merges. Similarly, the passive-decay tests use approximate half-life math (693 hours ≈ 29 days at λ=0.001); the actual vs. expected activation values needed to be within error bounds. |
| **Options Considered** | Pick thresholds from the paper and trust they'll work · guess a threshold and iterate if tests fail · empirically verify each threshold before writing tests. |
| **Chosen Solution** | Empirical verification before locking. |
| **Rationale** | Thresholds that work on one dataset may fail on another; verifying with actual similarity calculations on the test-fixture entries means the tests reflect reality, not assumptions. The verification step is a one-time cost before v1 ships. |
| **Impact** | Every test involving a numeric boundary includes a comment pointing to the empirical check that validated it (e.g., "verified via SequenceMatcher against 10 distinct topic pairs, max ratio 0.529"). Test fixtures include padding entries specifically to catch false groupings. |

---

## ADR-030 · Python 3.13 environment, `uv`-managed, pinned `requirements.txt` with resolved versions

| Field | Detail |
|---|---|
| **Decision** | The `mem_manage/` package runs on Python 3.13 (matching `memora_mini`'s environment), dependency installation is via `uv` (matching the repo's established pattern), and `mem_manage/requirements.txt` is a pinned list of resolved versions (not abstract `langchain>=1.0`, but `langchain-openai==1.6.0`, etc.) to ensure reproducible builds. |
| **Date** | 2026-09-03 |
| **Context** | The repo already uses `uv` and Python 3.13 for `memora_mini`; consistency across the repo keeps setup simple. Sentence-transformers and torch are heavy dependencies with platform-specific wheels (CPU vs CUDA); pinned versions eliminate version-resolution churn and platform surprises. |
| **Options Considered** | Python 3.12 for better sentence-transformers compatibility · loose pinning ("^1.6.0") for flexibility · full pinned freeze. |
| **Chosen Solution** | Python 3.13, full pinned freeze. |
| **Rationale** | 3.13 is available on this machine and works fine; full pinning removes one class of runtime surprises. Sentence-transformers and torch have plenty of binaries for 3.13+. |
| **Impact** | `mem_manage/requirements.txt` is generated from `uv pip freeze` after a fresh install, pinning 50+ transitive dependencies. Fresh setup: `uv venv .venv --python 3.13` + `uv pip install -r mem_manage/requirements.txt`. |

---
