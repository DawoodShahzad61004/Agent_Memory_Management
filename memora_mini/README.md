# memora_mini

A small, self-contained agentic-RAG graph with a **LangMem-style long-term memory layer
implemented natively** — no `langmem` dependency, no tool-calling anywhere.

This is a sandbox/reference implementation, not a product. It exists to prototype fixes for four
structural problems in the memory layer of the parent project (`../RAG-work`, "Memora"):

| Parent-project problem                                             | What memora_mini does instead                                                                                    |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Memory is insert-only; a bad distilled entry is permanent          | `DUPLICATE / CONTRADICTS / REFINES / UNRELATED` classification, supersede-with-audit lifecycle, strength decay |
| Failure memory keyed on an exact normalized query string (BUG-009) | Embedding recall only — a thumbdown on one wording reaches any semantically similar rewording                   |
| `track` / `evidence_type` are advisory, so they drift          | Both are **load-bearing**: retrieval filters on them, so a wrong value is a visible miss                  |
| No semantic memory, no procedural memory                           | Four namespaces, all populated and all queryable                                                                 |

---

## Setup

```bash
# From temp_graph/, using the sandbox venv:
../LangMem/.venv/Scripts/python.exe -m pip install -r memora_mini/requirements.txt

# Requires CUSTOM_API_BASE / CUSTOM_API_KEY / CUSTOM_API_MODEL_NAME in ../LangMem/.env
cd memora_mini
../../LangMem/.venv/Scripts/python.exe demo.py    # scripted end-to-end demo
../../LangMem/.venv/Scripts/python.exe main.py    # CLI REPL
```

Tests need no LLM server and no network:

```bash
# from temp_graph/
../LangMem/.venv/Scripts/python.exe -m pytest tests/ -q
```

### CLI commands

| Command                     | Effect                                        |
| --------------------------- | --------------------------------------------- |
| `<question>`              | run the graph                                 |
| `bad <feedback>`          | thumb down the last answer with feedback text |
| `fact <subject> \| <fact>` | add a semantic fact by hand                   |
| `learn`                   | force a reflection run now                    |
| `stats`                   | per-namespace counts, active/superseded split |
| `quit`                    | exit                                          |

---

## The four namespaces

| Namespace                              | LangMem type        | Contents                                     | Written by                                            |
| -------------------------------------- | ------------------- | -------------------------------------------- | ----------------------------------------------------- |
| `("memora", "<domain>", "episodic")` | episodic            | distilled Q&A from successful interactions   | reflection                                            |
| `("memora", "<domain>", "semantic")` | semantic            | domain facts and disambiguation rules        | `facts.py` / `fact` command (curated, on purpose) |
| `("memora", "global", "failure")`    | episodic (negative) | consolidated thumbdowns                      | reflection                                            |
| `("memora", "global", "procedural")` | procedural          | proposed prompt revisions,`approved=False` | reflection; **never auto-applied**              |

`<domain>` is a config constant (`DOMAIN`, default `"demo"`), not a user id — this is a single-user
local system, so the segmentation axis is corpus domain.

Two collections are **not** memory namespaces:

- `documents` — the source corpus. Read-only at query time, reached through the retriever.
- `("memora", "<domain>", "interactions")` — a pending-reflection buffer. Nothing recalls from it and
  it is never injected into a prompt.

### The store interface

`store/protocol.py` defines a four-verb `MemoryStore` Protocol whose signatures are byte-compatible
with LangGraph's `BaseStore`:

```python
put(namespace, key, value) -> None
get(namespace, key) -> Item | None
search(namespace, *, query=None, filter=None, limit=10) -> list[SearchItem]
delete(namespace, key) -> None
```

That compatibility is the whole point of the abstraction: if a tool-calling-capable model becomes
available later, a thin `BaseStore` subclass over the same Chroma collections lets LangMem's managers
drop in without touching a single caller.

`delete()` exists for operator cleanup only. The normal lifecycle is **supersede**: the old record
stays, flipped to `active=False` with `superseded_by` pointing at its replacement. All recall filters
`active=True` by default.

### Strength-based recall

`memory/recall.py` re-ranks `search()` results client-side:

```
score = similarity * (1 + w_hits * log1p(hit_count)) * recency_decay(last_hit_at)
```

It over-fetches `3 × limit` before re-ranking, then bumps `hit_count` / `last_hit_at` on everything it
returned. That bump is what makes unused memories fade — and it goes through Chroma's `update()` with
metadata only, so it never re-embeds.

---

## Constraint rationale

Everything below is inherited from the parent project, which operates under a hard no-data-egress
constraint. They are not preferences.

**One local LLM endpoint, every role.** A single OpenAI-compatible chat-completions server
(`CUSTOM_API_BASE`, ~`llama-3.1-8b-instruct`). `llm.py` is the only module that talks to it.

**No tool-calling, anywhere.** The server does not support it. No `tools=`, no `functions=`, no
`.bind_tools()`, no `trustcall`, no structured-output helper — every one of those compiles to a tool
schema. Structured output is asked for as plain JSON in the prompt and repaired in `json_fix.py`
(strip fences → `json_repair` → Pydantic validate, dropping bad array elements rather than the whole
response). **This is why the LangMem SDK's manager layer is rejected and reimplemented here.**

**No embeddings endpoint.** All embeddings come from local `all-MiniLM-L6-v2`, 384-dim, CUDA if
available.

**8B-sized prompts.** Every LLM call asks for either a short JSON array or a single enum token. No
call extracts, reconciles and consolidates at once. Failure injection is capped at
`MAX_FAILURE_INJECTIONS` (default 2) because the parent project hit prompt-bloat problems past
roughly 1,800 tokens against an 8B instruction-following ceiling.

**The model never proposes a delete.** It emits classifications only. Every destructive decision is
made deterministically in `memory/apply.py`, which is the only module in the package that writes to a
memory namespace.

**ChromaDB is the only datastore.** No MongoDB, no SQLite, no flat files. One factory
(`store/chroma_store.open_collection`) creates every collection, pins `hnsw:space = "cosine"`, and
asserts cosine on open — in the parent project a collection was accidentally created at the L2
default while scores were computed as `1 - distance`, which silently corrupted ranking for months.
The one file on disk is `memory_audit.jsonl`, a log sink; nothing reads it back for behaviour.

---

## Memory formation

Offline only — every `LEARN_EVERY_N` successful interactions, or on the `learn` command. Never in the
request path. Episodic and failure memories run through the same three stages, differing only in
namespace and schema:

1. **Extract** (`memory/extract.py`) — one LLM call per interaction → a JSON array of at most
   `MAX_CANDIDATES_PER_INTERACTION` candidates, validated against the target schema. Fields derivable
   in Python (`track`, `source_paths`) are filled in afterwards, not asked for.
2. **Classify** (`memory/classify.py`) — recall the candidate's top-3 nearest neighbours, then one LLM
   call per (candidate, neighbour) pair returning one enum token. Anything unparseable becomes
   `UNRELATED` — fail-safe, because `UNRELATED` means *insert*, never *mutate*.
3. **Apply** (`memory/apply.py`) — pure Python, fixed table:

   ```
   DUPLICATE   -> no-op; bump the existing entry's hit_count
   REFINES     -> supersede the existing entry with a merged record
   CONTRADICTS -> supersede, and append both versions to the audit log
   UNRELATED   -> insert as new
   ```

Guards, all config-driven: `MAX_OPS_PER_RUN` caps a run; ops referencing a key that is not in the
store are dropped; an entry whose `hit_count` exceeds `PROTECTED_HIT_COUNT` is not superseded on a
first `CONTRADICTS` (a `contradiction_strikes` counter is incremented instead, and it takes
`CONTRADICTION_STRIKES_REQUIRED` strikes to act) and is never destroyed by a mere `REFINES`; and
`DRY_RUN_MEMORY_OPS = True` by default, which logs every proposed operation as structured JSON and
writes nothing.

### Failure memory specifically

Thumbdowns are **consolidated, not accumulated** — ten on one theme collapse into one entry, because
each new failure candidate is classified against existing failure memories exactly like an episodic
one. Two extras:

- **Summarised at write time.** Extraction derives a short `missing_information` noun phrase from the
  raw feedback. That field, not the raw text, is what feeds prompt injection.
- **Injected as positive redirection.** `"prior attempts missed X; seek and state X"`, not a list of
  things to avoid — negative-only phrasing measurably fails to change model behaviour.

---

## The graph

```
load_memory -> retrieve -> generate -> judge -> (INSUFFICIENT & budget left ? retrieve : log_interaction) -> END
```

- **load_memory** — semantic facts for the query, plus semantically similar prior failures. No exact-string
  matching anywhere.
- **retrieve** — two tracks kept separate end to end: the `documents` collection and the episodic
  namespace. Never merged or co-ranked here.
- **generate** — the *only* place the two tracks combine, at the context boundary: learned-QA section
  first under an explicit precedence rule, documents second.
- **judge** — one LLM call, one enum (`OK | INSUFFICIENT`). Retry budget `MAX_ITERATIONS = 2`.
- **log_interaction** — persist the interaction record into the pending-reflection buffer.

### Why `track` and `evidence_type` are load-bearing

`retrieve` filters the episodic track on `track="learned_qa"`, so a record written with the wrong
`track` never comes back — a visible retrieval miss rather than a field that quietly rots. On a
**retry** iteration (the judge said `INSUFFICIENT`) the same recall additionally filters
`evidence_type` to human evidence (`observational | rct | meta_analysis`), which does the same job for
that field. `tests/test_graph.py::test_episodic_track_filter_is_load_bearing` pins this.

---

## What this would take to port into the parent project

Roughly in order of effort:

1. **Swap the store, keep the callers.** `ChromaMemoryStore` already speaks `BaseStore`'s signatures.
   In `../RAG-work`, `learned_qa_store.py` and `feedback_store.py` would be reimplemented behind
   `MemoryStore`, and `retriever.py` would call `recall()` instead of `collection.query()`. The
   existing cosine migration logic in `learned_qa_store.py` is *better* than this sandbox's assert
   (it snapshots and rebuilds rather than refusing) and should be kept — `open_collection` here is the
   simplified form for a store with no legacy data.
2. **Add the store-managed fields.** `hit_count`, `last_hit_at`, `active`, `superseded_by`,
   `contradiction_strikes` do not exist on the current `learned_qa` records. A one-off backfill
   defaulting `active=True`, `hit_count=0` is enough; recall degrades gracefully on records that lack
   them.
3. **Move failure memory out of MongoDB.** This is the BUG-009 fix and the biggest behavioural change.
   `user_thumbdowns` / `failed_variants` become one embedded `failure` namespace; the exact-string
   `normalized_query` lookup is deleted, not fixed. MongoDB stays for `feedback_interactions` (audit
   and analytics), which this sandbox does not attempt to replace.
4. **Insert the reflection pipeline where `SelfLearner.run_distillation()` sits.** Same trigger
   (`ENABLE_AUTO_DISTILLATION`, every N successful interactions), but extract → classify → apply
   instead of extract → insert. Ship it with `DRY_RUN_MEMORY_OPS=True` and read the audit log for a
   week before letting it write.
5. **What does *not* port.** The parent project's context-compression pipeline (NAC/DC/LBC), its
   parallel `Send`-per-variant fan-out, its tracing instrumentation, and its multi-stage
   `fix_llm_output` all sit above this layer and are untouched by it. `demo.py`, `facts.py` and the
   `corpus/` fixtures are sandbox scaffolding and would not be carried over.

Design decisions with real alternatives are recorded in `DECISIONS.md`, in a form that maps onto the
parent project's ADR table format.

---

## Non-goals

No context compression. No MongoDB. No cloud services. No FastAPI/HTTP layer. No tracing backends. No
PDF ingestion. No multi-user support, auth, or `{user_id}` namespace templating. No `langmem`
dependency. No tool-calling.
