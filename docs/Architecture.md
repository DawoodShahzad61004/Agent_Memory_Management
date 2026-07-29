## System Overview

This repository is an evaluation sandbox, not a product. Its sole purpose is to help decide which external
memory-management library should replace or augment the hand-rolled memory layer used by the main project,
**Memora** (sibling directory `../RAG-work`, a self-learning agentic RAG system). Each candidate library gets its
own throwaway experiment, built to mimic the memory behavior Memora actually needs, so candidates can be compared
against each other and against Memora's existing implementation on equal footing (see Decisions.md ADR-002,
ADR-003). **LangMem** is the first candidate under evaluation.

## High-Level Architecture

```
                              LangMem/                                 temp_graph/
                        ┌───────────────────┐                    ┌──────────────────────┐
                        │ .venv (uv, py3.13)│  interpreter used  │  graph.py / nodes.py  │
                        │ requirements.txt  │◄───────────────────┤  state.py / config.py │
                        │ .env (credentials)│  env loaded from   │  main.py (REPL)       │
                        │ tutorial_transcript│─────────────────► │  learning.py          │
                        └───────────────────┘                    └──────────┬────────────┘
                                                                             │
                                                                             ▼
                User asks a question (main.py REPL)
                             │
                             ▼
                     ┌───────────────┐
                     │  user_input   │  (nodes.py: trims/normalizes input)
                     └───────┬───────┘
                             ▼
                     ┌────────────────────┐
                     │  generate_answer   │
                     │  1. embed query    │
                     │  2. search learned_qa (k=4)       ┐
                     │  3. search failure_lessons (k=4)  ┼─► context block
                     │  4. format _GENERATE_ANSWER_PROMPT│
                     │  5. llm_invoke(llm, ...)          │
                     └───────┬────────────┘
                             ▼
                        answer returned to REPL
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
            accept (y)                reject (n)
                 │                       │
                 ▼                       ▼
      learning.record_accepted()  learning.record_rejected(feedback)
                 │                       │
      LangMem create_memory_manager  LangMem create_memory_manager
      (schema=LearnedLesson)         (schema=FailureLesson)
                 │                       │
                 ▼                       ▼
      learned_qa.add(...)          failure_lessons.add(...)
      (ChromaDB, cosine)           (ChromaDB, cosine)
```

Both `learned_qa` and `failure_lessons` persist under `temp_graph/chroma_store/` and are read back on every
subsequent `generate_answer` call, independently of each other — mirroring how Memora's `learned_qa` collection is
queried separately from `documents` (see `../RAG-work/docs/Architecture.md` § "Memory Architecture").

## Module Breakdown

### `temp_graph/config.py`
Loads `../LangMem/.env` explicitly (see Decisions.md ADR-006) rather than duplicating an env file. Defines
`CHROMA_STORE_PATH`, the two collection names (`LEARNED_QA_COLLECTION`, `FAILURE_LESSONS_COLLECTION`),
`MEMORY_SEARCH_K` (4), and the LLM/embedding timeout and rate-limit constants consumed by `llm_caller.py` and
`embedding_manager.py` (trimmed subset of `../RAG-work/app_workflow/config.py`'s defaults).

### `temp_graph/state.py`
`GraphState(TypedDict)` — intentionally minimal: `user_input: str`, `answer: NotRequired[str]`. Deliberately much
smaller than Memora's `GraphState`, which additionally tracks per-track retrieval, validation, dedup-merge, and
compression fields (see Decisions.md ADR-007 for why those stages aren't replicated here).

### `temp_graph/graph.py`
`build_graph()` — creates a `chromadb.PersistentClient` at `CHROMA_STORE_PATH`, one `EmbeddingManager`, and the two
`MemoryCollection` instances (`learned_qa`, `failure_lessons`). Wires a two-node `StateGraph`:
`START → user_input → generate_answer → END`. Returns `(compiled_graph, learned_qa, failure_lessons)` so the caller
(`main.py`) can pass the same collection handles into `learning.py`'s write-back functions.

### `temp_graph/nodes.py`
`user_input_node` strips/normalizes the raw input. `make_generate_answer_node(learned_qa, failure_lessons)` returns
a closure (`generate_answer_node`) so the node stays a plain `(state, config) -> dict` callable while still holding
references to both memory collections. Inside: searches both collections for the current query, tags each hit's
context block with `[Source: learned_qa]` or `[Source: failure_lessons]`, falls back to a "no prior lessons" string
when both are empty, formats `_GENERATE_ANSWER_PROMPT`, and calls the LLM via `llm_invoke`.

### `temp_graph/memory_schemas.py`
Two Pydantic schemas LangMem's `create_memory_manager` extracts into:
- `LearnedLesson(question, lesson, reason)` — distilled from an accepted answer.
- `FailureLesson(question, mistake, guidance, reason)` — distilled from a rejected answer plus the user's feedback text.

### `temp_graph/memory_store.py`
`MemoryCollection` — a thin wrapper around one ChromaDB collection (`hnsw:space: cosine`), independent of LangMem.
`.add(uid, text, metadata)` is idempotent (skips if `uid` already exists) and embeds via the shared
`EmbeddingManager`. `.search(query, k)` embeds the query and returns up to `k` hits (content, metadata, distance),
most-similar first. This is the storage layer LangMem's `create_memory_manager` output gets written into — LangMem
itself never touches ChromaDB directly (see Research.md topic 2/4).

### `temp_graph/learning.py`
The write-back layer under actual evaluation. Defines two `create_memory_manager` instances (one per schema),
each `enable_inserts=True, enable_updates=False, enable_deletes=False` (Decisions.md ADR-009). `record_accepted()`
builds a two-turn conversation (question + accepted answer) and invokes the learn-manager; `record_rejected()`
builds a three-turn conversation (question + rejected answer + user feedback) and invokes the failure-manager. Both
filter the extracted memories by `isinstance(memory.content, <Schema>)`, build a stable content-hash ID
(`hashlib.sha256(...)[:16]`), and call the corresponding `MemoryCollection.add()`.

### `temp_graph/main.py`
The REPL entry point. Builds the graph once, then loops: take a question → `app.invoke({"user_input": query})` →
print the answer → ask `[y/n/skip]` → on `y` call `record_accepted`, on `n` prompt for feedback text and call
`record_rejected`, on anything else skip without writing.

### `temp_graph/llm_caller.py`, `llm_setup.py`, `embedding_manager.py`, `prompts.py`
Copied from `../RAG-work/app_workflow/services/` and adapted: imports repointed from `app_workflow.config` to the
local `config.py`; the Langfuse/Phoenix/LangSmith `operation_tracing` instrumentation stripped (not needed for this
sandbox); `llm_setup.py` trimmed to the single `llm` instance this graph uses (a `ChatOpenAI` pointed at
`CUSTOM_API_BASE`/`CUSTOM_API_KEY`, shared between `generate_answer` and, via `learning.py`, as the model backing
both `create_memory_manager` instances); `prompts.py` trimmed to just `_GENERATE_ANSWER_PROMPT` (the compression/
dedup/distillation prompts belong to Memora's full pipeline, unused here since LangMem does the extraction work
instead). `llm_caller.py`'s FIFO gate, adaptive cooldown, and full Groq/OpenAI error taxonomy were kept as-is even
though this experiment is single-user, since it's the same `llm_invoke()` contract `nodes.py` and `learning.py`'s
underlying LLM calls (via LangMem) both depend on.

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Graph orchestration | LangGraph `StateGraph` (`langgraph==1.2.9`) | Two nodes only — see Decisions.md ADR-007 |
| Memory extraction | LangMem `create_memory_manager` (`langmem==0.0.30`) | Insert-only for this first pass — ADR-009 |
| LLM | `ChatOpenAI` via `langchain-openai`, pointed at a custom OpenAI-compatible endpoint (`CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME`) | Same instance drives both `generate_answer` and LangMem's extraction |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` | CPU, 384-dim, verified working |
| Vector storage | ChromaDB `PersistentClient`, cosine distance | Two collections: `learned_qa`, `failure_lessons`, under `temp_graph/chroma_store/` |
| Env/dependency management | `uv`, Python 3.13 | Per-candidate venv (`LangMem/.venv`) — ADR-001, ADR-005 |
| Config/secrets | `python-dotenv` loading `LangMem/.env` | Shared across `LangMem/` and `temp_graph/` — ADR-006 |

## Changelog

### 2026-07-28 — Repo scaffold and LangMem environment

`README.md` and `CLAUDE.md` created; `LangMem/` directory added with a pinned `requirements.txt` (`uv pip install -r
requirements.txt`-installable, `LangMem/.venv`) and the LangMem tutorial reference material
(`tutorial_transcript.txt`, `.env` for provider credentials). No experiment code existed yet at this point.

### 2026-07-29 — `temp_graph/` LangMem experiment implemented

Full first-pass experiment added: `config.py`, `state.py`, `graph.py`, `nodes.py`, `main.py` (the LangGraph wiring
described above), `memory_schemas.py` + `memory_store.py` (the episodic/failure memory schemas and ChromaDB store),
`learning.py` (LangMem `create_memory_manager` write-back), and adapted `llm_caller.py`/`embedding_manager.py`/
`llm_setup.py`/`prompts.py` copied from `../RAG-work/app_workflow/services/`. Verified via smoke test: all modules
import cleanly, `build_graph()` runs end-to-end, the embedding model loads (CPU, 384-dim), and both ChromaDB
collections initialize successfully (0 entries, fresh store). Live LLM answer generation has not yet been
end-to-end tested because `CUSTOM_API_BASE`/`CUSTOM_API_KEY` in `LangMem/.env` were blank as of this writing — see
Status.md for the pending follow-up.

---
