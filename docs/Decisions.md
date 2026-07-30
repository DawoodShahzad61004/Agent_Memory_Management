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
| **Rationale** | Against an 8B model, a call that must align a candidate with several neighbours *and* emit structured output fails in ways that are hard to attribute to a specific cause. A single token has exactly one failure mode — unrecognised text — with an obvious, safe fallback (`UNRELATED` → insert). The cost is `candidates × CLASSIFY_NEIGHBOURS` calls per interaction, acceptable because reflection runs offline, never in the request path. |
| **Impact** | `memory/classify.py`; `strongest()` resolves disagreement across neighbours by priority (`CONTRADICTS` > `REFINES` > `DUPLICATE`). If a stronger model becomes available later, a batched form is a strictly cheaper drop-in and only this module would change. |

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
