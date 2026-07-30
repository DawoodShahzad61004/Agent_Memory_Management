## System Overview

This repository is an evaluation sandbox, not a product. Its sole purpose is to help decide which external
memory-management approach should replace or augment the hand-rolled memory layer used by the main project,
**Memora** (sibling directory `../RAG-work`, a self-learning agentic RAG system). Each candidate gets its own
throwaway experiment, built to mimic the memory behavior Memora actually needs, so candidates can be compared
against each other and against Memora's existing implementation on equal footing (see Decisions.md ADR-002,
ADR-003). **LangMem** is the first (and so far only) candidate under evaluation.

The evaluation went through two implementations:

1. **`temp_graph/`** (2026-07-28/29, now deleted) — a thin LangGraph wrapper that called the `langmem` SDK's
   `create_memory_manager()` directly. Superseded once it became clear the SDK's manager layer has a hard
   dependency on tool-calling (`trustcall`), which Memora's actual LLM endpoint does not support (Research.md
   topic 7; Decisions.md ADR-010).
2. **`memora_mini/`** (2026-07-29 onward, current) — a ~900-line native reimplementation of LangMem's memory
   *taxonomy* (episodic / semantic / procedural) and *store interface shape*, with no `langmem` import anywhere.
   This is the system described in the rest of this document.

## High-Level Architecture

```
memora_mini/
├── config.py            all constants, feature flags, env loading (repo-root .env)
├── llm.py                one OpenAI-compatible chat client, no tool-calling
├── json_fix.py           fence-strip -> json_repair -> Pydantic validate
├── embeddings.py         sentence-transformers all-MiniLM-L6-v2, 384-dim, local only
├── prompts.py             every prompt string; each asks for JSON array XOR one enum token
├── facts.py               curated seed data for the semantic namespace
├── ingest.py              corpus/*.md -> chunk -> embed -> `documents` collection
├── store/
│   ├── protocol.py        MemoryStore Protocol (put/get/search/delete), BaseStore-signature-compatible
│   ├── chroma_store.py     ChromaMemoryStore — the only code path that creates a Chroma collection
│   └── namespaces.py       the four namespace tuples + the interactions buffer + name mapping
├── memory/
│   ├── schemas.py          EpisodicMemory, FailureMemory, SemanticFact, PromptRevision, MemoryBase
│   ├── recall.py           strength-based re-rank wrapper over store.search()
│   ├── extract.py          stage 1 — one LLM call per interaction -> candidate memories
│   ├── classify.py         stage 2 — one LLM call per (candidate, neighbour) -> one enum token
│   ├── apply.py             stage 3 — pure Python; the only module that writes a memory namespace
│   └── reflect.py           orchestrates extract -> classify -> apply, offline only
├── graph/
│   ├── state.py             RAGState TypedDict
│   ├── nodes.py             the six node functions
│   └── build.py             StateGraph wiring
├── corpus/                 5 small .md fixtures (includes the ASD acronym collision)
├── main.py                  CLI REPL
└── demo.py                  scripted end-to-end walkthrough
```

### Memory formation pipeline (offline, never in the request path)

```
pending interactions (Chroma "interactions" buffer, reflected=False)
              │
              ▼  every LEARN_EVERY_N successes, or the `learn` command
    ┌─────────────────────┐
    │  extract.py          │  1 LLM call / interaction -> JSON array (<= MAX_CANDIDATES_PER_INTERACTION)
    └─────────┬────────────┘
              ▼
    ┌─────────────────────┐
    │  classify.py         │  recall top-3 neighbours; 1 LLM call / (candidate, neighbour) -> 1 enum token
    └─────────┬────────────┘   DUPLICATE | CONTRADICTS | REFINES | UNRELATED  (unparseable -> UNRELATED)
              ▼
    ┌─────────────────────┐
    │  apply.py (no LLM)    │  DUPLICATE   -> bump hit_count
    │                       │  REFINES     -> supersede with Python-union merge
    │                       │  CONTRADICTS -> supersede + audit both versions
    │                       │  UNRELATED   -> insert
    └─────────┬────────────┘
              ▼
  memory_audit.jsonl (append-only) + the four memory namespaces
```

### The query graph (`graph/build.py`)

```
load_memory -> retrieve -> generate -> judge -> (INSUFFICIENT & budget left ? retrieve : log_interaction) -> END
```

- **load_memory** — recalls semantic facts and semantically-similar prior failures for the query. No exact-string
  matching anywhere (this closes BUG-009 from Memora's design, see Bugs.md and Decisions.md ADR-018).
- **retrieve** — two tracks kept separate end to end: the `documents` collection and the `episodic` namespace,
  filtered on `track="learned_qa"` (and, on a retry iteration, additionally on `evidence_type`). Never merged here.
- **generate** — the only place the two tracks combine, at the context boundary: learned-QA section first under an
  explicit precedence rule, source documents second. Failure memories are injected as positive redirection built
  from `missing_information`, capped at `MAX_FAILURE_INJECTIONS`.
- **judge** — one LLM call, one enum token (`OK` | `INSUFFICIENT`). Retry budget `MAX_ITERATIONS = 2`.
- **log_interaction** — persists the interaction into the pending-reflection buffer; nothing here calls an LLM.

## Module Breakdown

### `config.py`
All constants and env loading in one place — nothing else in the package reads `os.environ` directly. Loads the
repo-root `.env` (`REPO_ROOT / ".env"`, i.e. `Memory-Management-Tools/.env`), not `LangMem/.env` — this changed
when `memora_mini/` was promoted from `temp_graph/`'s sibling to a first-class root-level package (see Status.md,
2026-07-30). Defines the LLM role config (one endpoint, every role), embedding config, storage paths, the four
namespace-adjacent constants, recall/strength weights, retrieval top-k's, and memory-formation guard thresholds
(`MAX_OPS_PER_RUN`, `PROTECTED_HIT_COUNT`, `CONTRADICTION_STRIKES_REQUIRED`, `DRY_RUN_MEMORY_OPS`, default `True`).

### `store/protocol.py`, `store/namespaces.py`, `store/chroma_store.py`
`MemoryStore` is a `typing.Protocol` with exactly four verbs — `put`, `get`, `search`, `delete` — whose parameter
names, ordering, and keyword-only markers are held byte-compatible with LangGraph's `BaseStore` (Decisions.md
ADR-012), even though nothing here imports LangGraph's store module. `ChromaMemoryStore` is the only implementation
and the only code path in the package that creates a Chroma collection: `open_collection()` pins
`hnsw:space="cosine"` on create and asserts it on every open, raising loudly on a mismatch (Decisions.md ADR-019).
`namespaces.py` defines the four memory namespaces plus a fifth, non-memory `interactions` buffer, and the single
`"__".join(namespace)` mapping to a Chroma collection name. Chroma metadata only accepts scalars, so `_encode`/
`_decode` in `chroma_store.py` JSON-flatten list fields on write and restore them on read — always at the store
layer, never at call sites. `update_metadata()` is a metadata-only Chroma `update()` (no re-embed), used for
`hit_count`/`last_hit_at` bumps on every recall.

### `memory/schemas.py`
Five Pydantic models: `MemoryBase` (the store-managed fields every memory type shares — `hit_count`, `last_hit_at`,
`active`, `superseded_by`, `contradiction_strikes`, `memory_type`, `created_at`; the LLM never sets these),
`EpisodicMemory` (`question`, `answer`, `track`, `evidence_type`, `source_paths`, `confidence`), `FailureMemory`
(`original_query`, `bad_answer`, `user_feedback`, `missing_information`, `failed_variants`), `SemanticFact`
(`subject`, `fact`, `disambiguates`), `PromptRevision` (`target_prompt`, `proposed_text`, `rationale`, `approved`
— always `False` on write), and `ClassificationVerdict` (a single enum field, used by `json_fix.parse_enum`
indirectly). Each subclass implements `to_text()`, the string that actually gets embedded.

### `memory/recall.py`
Wraps `store.search()` with a client-side strength re-rank:
`score = similarity * (1 + w_hits * log1p(hit_count)) * recency_decay(last_hit_at)`. Over-fetches
`limit * OVERFETCH_FACTOR` before re-ranking and truncating, drops hits below `SIMILARITY_FLOOR` when a semantic
query was given, and — unless called with `bump=False` (used by `classify.py`, since reflection is offline
bookkeeping and must not inflate the hit counts that drive recall) — bumps `hit_count`/`last_hit_at` on every
returned item. `recency_decay()` floors at `RECENCY_FLOOR` (0.5) with a `RECENCY_HALF_LIFE_DAYS`-day half-life, so
decay alone can never zero out a memory, only de-prioritize it relative to actively-recalled ones.

### `memory/extract.py`, `memory/classify.py`, `memory/apply.py`, `memory/reflect.py`
`extract.py` makes one LLM call per interaction, asking for a JSON array of at most `MAX_CANDIDATES_PER_INTERACTION`
candidates; fields Python can derive (`track`, `source_paths`) are filled in afterwards rather than asked for.
`classify.py` recalls each candidate's top-`CLASSIFY_NEIGHBOURS` neighbours and makes one LLM call per pair,
returning a single enum token via `json_fix.parse_enum` (unparseable -> `UNRELATED`, the fail-safe default because
it maps to insert, never mutate); `strongest()` picks the highest-priority verdict when neighbours disagree
(`CONTRADICTS > REFINES > DUPLICATE`). `apply.py` is pure Python and the *only* module in the package that writes
to a memory namespace: a fixed table turns each verdict into a `MemoryOp` (`plan()`), then `apply_ops()` executes
(or, in dry-run, only logs) the batch, enforcing `MAX_OPS_PER_RUN`, dropping ops whose `target_key` no longer
exists, and protecting high-`hit_count` entries from a single `REFINES`/`CONTRADICTS` verdict (`PROTECTED_HIT_COUNT`,
`CONTRADICTION_STRIKES_REQUIRED`). `reflect.py` orchestrates all three stages over two lanes — episodic (from `OK`
interactions) and failure (from `THUMBDOWN` interactions) — using the *same* extract→classify→apply code path for
both, which is what makes repeated thumbdowns on one theme consolidate into a single entry instead of accumulating.
It also runs `propose_prompt_revisions()`: a purely deterministic (no LLM) rule that turns a failure theme recurring
`PROCEDURAL_PROPOSAL_HITS` times into a `PromptRevision` with `approved=False`.

### `json_fix.py`
The only thing standing between an 8B model's prose habits and a validated Pydantic object, since there is no
tool-calling and no structured-output helper anywhere in this package. Three tiers: `strip_fences()` (pull the
payload out of markdown fences / surrounding commentary by seeking the outermost brackets), `parse_json()`
(`json.loads`, then `json_repair.repair_json` on failure), and `parse_list()` (validate each array element against
a Pydantic schema, silently dropping bad elements rather than discarding the whole batch — partial success beats
total failure). `parse_enum()` handles the single-token responses used by `classify.py` and the graph's `judge`
node.

### `llm.py`
A deliberately thin `OpenAI` client wrapper pointed at `CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME`.
No `tools=`, no `.bind_tools()`, no `trustcall` — none of that is available against this endpoint (Research.md
topic 7). `chat()` retries with exponential backoff up to `LLM_MAX_ATTEMPTS`; `is_reachable()` is a short-timeout
probe so `demo.py`/`main.py` fail fast with a clear message instead of hanging on the request-path's 120s timeout.

### `graph/state.py`, `graph/nodes.py`, `graph/build.py`
`RAGState` is a `TypedDict` carrying the query, iteration counter, the two retrieval tracks, recalled semantic
facts and failure memories, the assembled prompt, the answer, the judge verdict, and a handle to the `store`
itself (passed through state rather than closed over, unlike `temp_graph/`'s closure-based nodes). `nodes.py`
implements the five node functions described in the graph diagram above, each a plain `state -> partial-state`
function. `build.py` wires the five-node `StateGraph` with one conditional edge out of `judge` and exposes `ask()`
as the single entry point used by both `main.py` and `demo.py`.

### `facts.py`, `ingest.py`, `corpus/`
`facts.py` seeds the semantic namespace by hand (three facts, including the ASD-acronym-collision disambiguation
rule) rather than extracting facts automatically — see Decisions.md ADR-016 for why. `ingest.py` chunks
`corpus/*.md` (paragraph-greedy, falling back to a character window for oversized paragraphs) into the `documents`
collection, which is not a memory namespace and is read-only at query time. `corpus/` holds five small fixtures:
`asd_autism.md` and `asd_cardiology.md` (the deliberate acronym collision), `vitamin_d.md` (used for the
contradiction-supersede demo step), `omega3.md`, `evidence_grades.md`.

### `main.py`, `demo.py`
`main.py` is the CLI REPL: `<question>` runs the graph; `bad <feedback>` logs a thumbdown against the last answer;
`fact <subject> | <fact>` adds a semantic fact by hand; `learn` forces a reflection run; `stats` prints per-namespace
active/superseded counts. Reflection also runs automatically every `LEARN_EVERY_N` successful turns. `demo.py` is
the scripted, non-interactive walkthrough of all nine acceptance-criteria steps (ingest → ask → dry-run learn →
live learn → semantically-different rephrasing → thumbdown-then-reword (BUG-009 check) → repeated-thumbdown
consolidation → contradiction supersede → final stats), used to verify the whole pipeline without live LLM calls
during structural testing (see Status.md).

## Superseded: `temp_graph/` (deleted 2026-07-29)

The original LangMem-SDK-based prototype: a two-node LangGraph (`user_input -> generate_answer`) backed by two
ChromaDB collections (`learned_qa`, `failure_lessons`), writing to them via `langmem.create_memory_manager()` with
`enable_inserts=True, enable_updates=False, enable_deletes=False` (former ADR-009). It ran against `LangMem/.venv`
and loaded `LangMem/.env` explicitly. It was never live-LLM-tested end to end — `CUSTOM_API_BASE`/`CUSTOM_API_KEY`
were blank for the whole time it existed — only graph wiring, Chroma collection creation, and the embedding
pipeline were confirmed working. It is fully superseded by `memora_mini/` and was deleted rather than kept as a
reference, since `memora_mini/` demonstrates directly why the SDK approach doesn't work here (Decisions.md
ADR-010) — keeping a dead prototype around added confusion without adding comparison value. `LangMem/` itself
(the `.venv`, pinned `requirements.txt`, tutorial transcript, and `LangMem_Documentation.txt`) remains, as
reference material for the LangMem candidate.

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Graph orchestration | LangGraph `StateGraph` (`langgraph==1.2.9`) | Five nodes, one conditional edge — no `langmem` import |
| Memory extraction/classification | Hand-written `memory/extract.py` + `memory/classify.py` | Plain-JSON prompts + `json_fix.py` repair; no tool-calling, no `trustcall` |
| Memory writes | Hand-written `memory/apply.py` | Pure Python, deterministic; the model never proposes a delete |
| LLM | `openai` Python client against a self-hosted OpenAI-compatible endpoint (`CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME`, ~`llama-3.1-8b-instruct`) | Every role (generate, judge, extract, classify) routes to the same endpoint |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` | Local only, CUDA if available, 384-dim, normalised |
| Vector storage | ChromaDB `PersistentClient`, cosine distance | One factory (`store/chroma_store.open_collection`) creates every collection; four memory namespaces + `documents` + `interactions` |
| Structured-output repair | `json_repair` | Tier 2 of `json_fix.py`, between fence-stripping and Pydantic validation |
| Env/dependency management | `uv`, Python 3.13, root-level `.venv/` | `memora_mini/requirements.txt` pinned separately from `LangMem/requirements.txt` |
| Config/secrets | `python-dotenv` loading the repo-root `.env` | Changed from `LangMem/.env` when `memora_mini/` moved to repo root — see Status.md, 2026-07-30 |
| Testing | `pytest`, 58 tests, no LLM server or network required | `tests/` at repo root; covers store, recall, apply, json_fix, reflect, and graph behaviour |

## Changelog

### 2026-07-28 — Repo scaffold and LangMem environment

`README.md` and `CLAUDE.md` created; `LangMem/` directory added with a pinned `requirements.txt` (`uv pip install -r
requirements.txt`-installable, `LangMem/.venv`) and the LangMem tutorial reference material
(`tutorial_transcript.txt`, `.env` for provider credentials). No experiment code existed yet at this point.

### 2026-07-29 — `temp_graph/` LangMem-SDK experiment implemented, then superseded

Full first-pass experiment added: `config.py`, `state.py`, `graph.py`, `nodes.py`, `main.py`, `memory_schemas.py` +
`memory_store.py`, `learning.py` (LangMem `create_memory_manager` write-back), and adapted
`llm_caller.py`/`embedding_manager.py`/`llm_setup.py`/`prompts.py` copied from `../RAG-work/app_workflow/services/`.
Verified via smoke test: all modules import cleanly, `build_graph()` runs end-to-end, the embedding model loads
(CPU, 384-dim), and both ChromaDB collections initialize successfully. Live LLM answer generation was never
end-to-end tested (credentials were blank).

Later the same day, a much larger session (`Chat 33 (July 29).txt`) worked through whether LangMem's storage
options (Postgres/MongoDB/Redis-backed `BaseStore`, semantic search via MongoDB Atlas Vector Search) fit Memora's
constraints, concluded they didn't (local `mongod`, no cloud egress — Research.md topics 5-6), then set out to
build **`memora_mini`**: a native reimplementation of LangMem's taxonomy and store-interface shape, deliberately
avoiding the `langmem` package because its manager layer depends on `trustcall`, which depends on tool-calling,
which the project's local LLM endpoint does not support (Research.md topic 7; Decisions.md ADR-010).

`memora_mini/` was built bottom-up per its own working-method instructions: `config.py`/`embeddings.py`/
`store/protocol.py`/`store/chroma_store.py`/`memory/recall.py` first, with `tests/test_store.py` and
`tests/test_recall.py` passing (19 tests) before any LLM-touching code existed; then `json_fix.py`/`llm.py`; then
the three-stage memory pipeline (`extract.py`, `classify.py`, `apply.py`, `reflect.py`) with `tests/test_apply.py`
and `tests/test_reflect.py`; then the five-node graph (`tests/test_graph.py`); then `ingest.py`, the `corpus/`
fixtures (including the deliberate ASD acronym collision), `main.py`, and `demo.py`. Verified: 56 tests passing,
then 58 after adding semantic-facts and procedural-proposal coverage; `demo.py` run structurally against a fake
LLM harness (the real endpoint was unreachable — connection timeout) confirmed all nine acceptance-criteria steps
end to end, including thumbdown-consolidation (4 -> 1 active entry) and a CONTRADICTS supersede with full audit
trail. `temp_graph/` was then deleted entirely (1,446 lines removed) as fully superseded, and `memora_mini/`'s own
`README.md`/`DECISIONS.md` were renamed to `temp_project_description.md`/`temp_decision_notedown.md` pending
consolidation into this five-file `docs/` system.

### 2026-07-30 — `memora_mini/` and `tests/` promoted to repo root

Both directories moved from being `temp_graph/` siblings to first-class repo-root packages. `config.py`'s
`ENV_PATH` was updated to load the repo-root `.env` (`REPO_ROOT / ".env"`) instead of `LangMem/.env`, and the
active Python environment moved from `LangMem/.venv` to a root-level `.venv/`. Verified: all 58 tests still pass
from the new location with no other code changes required — the only stale references left behind were setup
commands in `temp_project_description.md`, which were corrected to the new paths.

### 2026-07-30 — Documentation consolidated onto `memora_mini`

This `docs/` five-file system, which previously described only the deleted `temp_graph/` experiment, was rewritten
from the ground up (this document included) to describe `memora_mini` as the current state of the LangMem
evaluation, using `Chat 33 (July 29).txt`, the current contents of every `memora_mini/` module, and
`temp_project_description.md`/`temp_decision_notedown.md` as source material. `README.md` was rewritten to match
(and its UTF-16LE encoding bug, BUG-001, fixed in the process — see Bugs.md). `memora_mini/temp_project_description.md`
and `memora_mini/temp_decision_notedown.md` were deleted once their content was folded in, so a single documentation
set (`docs/`) remains. `graphify-out/` was regenerated against the updated tree.

---
