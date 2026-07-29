## 1. Survey of open-source agent-memory libraries

| Field | Detail |
|---|---|
| **Topic** | Which existing open-source library (if any) could replace/augment Memora's hand-rolled memory layer (MongoDB `feedback_interactions`/`user_thumbdowns`/`failed_variants` + ChromaDB `documents`/`learned_qa`). |
| **Date** | 2026-07-28 |
| **Findings** | Started from the GitHub list [TsinghuaC3I/Awesome-Memory-for-Agents](https://github.com/TsinghuaC3I/Awesome-Memory-for-Agents), which aggregates research papers and memory-related products. Too many candidates to evaluate exhaustively, so the list was narrowed to 4-5 based on stars, recency, and open-issue health. A deeper comparison (via ChatGPT) evaluated six specifically against Memora's LangGraph + ChromaDB + MongoDB stack: **LangMem** (native LangGraph integration, extraction/consolidation toolkit — best fit), **Mem0** (standalone `memory.add()`/`memory.search()` service, could duplicate the existing `learned_qa` pipeline), **Graphiti** (temporal knowledge graphs, strong for supersession/changing facts, likely excessive unless temporal conflicts become central), **Cognee** (combined vector + knowledge-graph memory for multi-hop retrieval), **Letta** (full MemGPT-style stateful-agent runtime, too invasive architecturally), **LangGraph Store** (namespaced cross-thread persistence — a storage primitive, not a memory-lifecycle manager). |
| **Conclusion** | Shortlisted LangMem as the first candidate to build a throwaway comparison harness for, on the reasoning that it integrates natively with the LangGraph stack Memora already uses and can write into custom storage (not just its own store), making a like-for-like comparison against Memora's existing `SelfLearner` straightforward. Mem0, Graphiti, Cognee, and Letta are queued as later candidates, each to get its own top-level directory per [[decisions-repo-structure]] (see Decisions.md ADR-002). |
| **Relevance to Project** | Sets the overall evaluation order for this repo. Directly informs Decisions.md ADR-004 (LangMem chosen first) and the repo structure in CLAUDE.md. |

---

## 2. LangMem — architecture and API deep dive

| Field | Detail |
|---|---|
| **Topic** | What LangMem actually is, what it does to raw interaction records, and where its responsibility boundary sits relative to a custom memory pipeline like Memora's `SelfLearner`. |
| **Date** | 2026-07-28 |
| **Findings** | LangMem is a memory-*processing* toolkit, not a database or storage platform — "LangGraph Store saves and retrieves memories; LangMem decides what should become a memory and how existing memories should change." It defines three memory categories (semantic/episodic/procedural) and two writing patterns: **hot-path** (agent calls `create_manage_memory_tool`/`create_search_memory_tool` mid-conversation) and **background** (a separate process reviews the conversation later via `create_memory_store_manager`, better for production since it doesn't add latency to every response). The lower-level primitive `create_memory_manager()` returns structured `ExtractedMemory` objects without requiring LangGraph's `InMemoryStore` — it can be pointed at any storage layer (MongoDB, ChromaDB, Postgres), which is what makes it usable against Memora's existing collections rather than forcing a rewrite. LangMem also supports two storage shapes: **profile** (one evolving structured object per user/project — good for stable, bounded fields) and **collection** (independent atomic memories — good for decisions, lessons, findings). Maturity note: as of July 2026 PyPI's latest published version was `0.0.30` (released 2025-10-27) — still a 0.0.x release, so version pinning and testing across `langmem`/`langgraph`/`langchain-core` combinations was flagged as necessary rather than assumed-safe. |
| **Conclusion** | LangMem is best scoped as *the extraction/consolidation layer only* — it does not replace MongoDB/ChromaDB persistence, the existing quality/confidence gates, conflict resolution, provenance, or ranking/recency logic. Exact responsibility split established: raw-record reading, quality filtering, thumbdown/interaction joining, schema definition, factual-grounding verification, existing-memory search, embedding, and Chroma upsert all remain custom code; LangMem's job is strictly turning a conversation + schema + instructions into structured memory proposals. |
| **Relevance to Project** | Directly shaped `temp_graph/learning.py` and `temp_graph/memory_schemas.py` — `create_memory_manager` (not `create_memory_store_manager`) was used with `enable_updates=False`/`enable_deletes=False` for the first pass (see Decisions.md ADR-009), and the custom `MemoryCollection` wrapper (`temp_graph/memory_store.py`) does the embedding/Chroma-upsert work LangMem deliberately leaves external. |

---

## 3. LangMem official tutorial walkthrough

| Field | Detail |
|---|---|
| **Topic** | `LangMem/tutorial_transcript.txt` — a walkthrough of LangMem's own introductory demo, used as the reference pattern before adapting it to Memora's shape. |
| **Date** | 2026-07-28 |
| **Findings** | The tutorial builds a `LearningCoachMemory` Pydantic schema with a `Literal` `memory_type` field (`role`/`learning_goal`/`preference`/`current_focus`) plus `value` and `reason` fields, scoped by a `(user_id, "learning_coach_memories")` namespace. It calls `create_memory_manager(llm, schemas=[...], instructions=..., enable_inserts=True, enable_updates=False, enable_deletes=False)`, invokes it with `{"messages": [...], "max_steps": 1}`, and manually writes each extracted memory into LangGraph's `InMemoryStore` before a later turn recalls *all* memories in the namespace (no semantic filtering, `query=None, limit=10`) and injects them into a personalization prompt. The tutorial itself flags this as non-production: `InMemoryStore` is wiped on restart, recall is unfiltered rather than searched, and update/delete/conflict-resolution/expiration/provenance are all explicitly out of scope for the demo. |
| **Conclusion** | The demo's core mechanics (schema → `create_memory_manager` → structured memory → manual persistence → later recall) transferred directly into `temp_graph/`, but two production gaps called out by the tutorial were deliberately closed rather than inherited: persistence uses ChromaDB (`temp_graph/memory_store.py`) instead of `InMemoryStore`, and recall uses embedding similarity search (`MemoryCollection.search()`) instead of unfiltered full-namespace fetch. |
| **Relevance to Project** | Baseline pattern for `temp_graph/learning.py`, `temp_graph/memory_schemas.py`, and `temp_graph/memory_store.py`. See Decisions.md ADR-006 and ADR-009 for where the toy setup deliberately diverged from the tutorial's simplifications. |

---

## 4. Mapping LangMem's responsibility boundary onto Memora's `SelfLearner`

| Field | Detail |
|---|---|
| **Topic** | Concretely, what would LangMem do to a raw `feedback_interactions`/`user_thumbdowns` record on the path to `learned_qa`/`failure_lessons`, and what stays Memora's own code (referenced from `../RAG-work/app_workflow/services/self_learner.py` and `learned_qa_store.py`). |
| **Date** | 2026-07-28 |
| **Findings** | Confirmed LangMem has *no* built-in concept of `learned_qa` or `failure_lessons` collections — those are Memora-specific ideas that must be modeled via custom Pydantic schemas (`LearnedLesson`, `FailureLesson`) and custom instructions passed to `create_memory_manager`. Walked through the exact responsibility table: MongoDB record reading, `quality == "OK"` eligibility filtering, and thumbdown/interaction joining stay in application code; schema definition and LLM-driven extraction/consolidation go to LangMem; factual-grounding verification (claim-to-evidence checking), existing-memory search for merge/update decisions, embedding generation (`all-MiniLM-L6-v2`), Chroma upsert, and recency/aging reranking all remain custom responsibilities outside LangMem entirely. |
| **Conclusion** | This is the actual point of comparison for evaluating LangMem (and later Mem0/Letta) against Memora's existing `SelfLearner`: same read/write contract — `learned_qa` + `failure_lessons`, semantic recall via embeddings, provenance-carrying metadata — different extraction engine underneath. LangMem replaces only the LLM-extraction/consolidation portion of `SelfLearner._generate_qa_pairs()`; it does not replace `SelfLearner` itself. |
| **Relevance to Project** | This mapping is the reason `temp_graph/` was scoped the way it is (see CLAUDE.md "What 'similar to my original one' means") and is the yardstick the next candidate's toy setup should be measured against for a fair comparison. |

---
