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
