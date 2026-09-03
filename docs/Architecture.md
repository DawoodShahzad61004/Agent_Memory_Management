## System Overview

This repository builds **`mem_manage/`** — a reusable memory-management module for **coding agents**. It is the
single deliverable; everything else in the tree either feeds it (prior art) or exercises it (the sample agent).

The module's job: accept raw agent interactions, and maintain from them a small, current, non-contradictory set of
**durable learnings** that can be recalled cheaply. The design premise is that a memory store which only ever
accumulates gets worse with use — retrieval noise rises, stale conventions outlive the code that motivated them,
and contradictory entries sit side by side with nothing to break the tie. So **forgetting is a first-class
mechanism here, not storage cleanup**: every record carries a decaying activation value, and decay is what
resolves conflicts, bounds growth, and keeps recall precise.

> **Current state: design phase.** `mem_manage/` exists as an empty directory. The design below is the target;
> nothing in it is implemented yet. What *is* implemented and working in this repo is prior art —
> `memora_mini/` (§ "Prior art") — several of whose mechanisms are direct antecedents of the target design.

### How the repo got here

It started as an evaluation sandbox for a separate project, **Memora** (`../RAG-work`), comparing external
memory-management libraries one at a time: LangMem first (`memora_mini/`), then Mem0 (`Sample_Coding_Agent/`).
Two things came out of it. First, a hard constraint: most candidates' memory-manager layers depend on LLM
tool-calling, which the available local endpoint does not support — a hard blocker for LangMem's SDK
(Decisions.md ADR-010, Research.md topic 7) and a soft one shaping Mem0's options (Research.md topic 9), which
eventually paused the evaluation entirely (ADR-024). Second, and more usefully: none of the candidates forget on
purpose. They extract and accumulate. The repo is now scoped to building that missing piece directly rather than
continuing to shop for it. The evaluation directories remain as prior art and are not being resumed.

### Current tree

```
Agent_Memory_Management/
├── mem_manage/            THE MODULE — the deliverable. Empty; design phase.
├── Sample_Coding_Agent/   TEST HARNESS — the agent mem_manage/ is wired into and exercised against.
├── memora_mini/           PRIOR ART (working) — LangMem taxonomy reimplemented natively.
├── LangMem/               PRIOR ART (reference material only, not executable).
├── tests/                 pytest suite for memora_mini/ — 58 tests, no LLM server, no network.
└── docs/                  five-file tracking system.
```

---

## Design Principles

These are the constraints `mem_manage/` is built to satisfy. Each one exists because of a specific failure mode
observed in the candidates evaluated here.

### 1. Every entry is timestamped

`created_at` and `last_accessed_at` on every record, always. Time is the input every other mechanism reads —
decay, maturation, conflict resolution, and degradation are all functions of elapsed time. A record without a
usable timestamp cannot participate in any of them, so timestamps are set at the store layer and are never
optional or LLM-supplied.

### 2. Every memory carries an activation value

A single scalar strength per record, rising on retrieval and falling with time and interference. It is the one
number that recall ranking, merge eligibility, degradation tier, and hard-delete all read. Keeping it to one
scalar is deliberate: separate "importance" and "recency" and "usage" scores drift out of agreement and each
needs its own tuning story. One value, several inputs.

### 3. Similar memories consolidate: dedupe → merge → summarize → hard-delete

Near-duplicates are not all kept. They are deduped (the same learning arriving twice reinforces one record rather
than creating a second), merged (overlapping learnings fold into one), and summarized (a cluster of related
records collapses into the generalization they share). Records whose activation bottoms out are eventually
**hard-deleted** — actually removed, not tombstoned forever. Growth is bounded by consolidation working
continuously, not by a size cap that triggers a panic eviction.

This is the one principle with a working antecedent already in the repo: `memora_mini/memory/apply.py` does
deterministic dedupe/merge via its `DUPLICATE`/`REFINES` verdicts (§ "Prior art"). What it lacks is the deletion
end — it supersedes forever and never reclaims.

### 4. Conflicting memories are timestamped, not updated

When a new learning contradicts an existing one, the new one is **written alongside** the old with its own
timestamp. The old record is not edited, overwritten, or deleted at write time.

The reason is that write-time conflict resolution requires deciding *which* of two plausible statements is
currently true — an expensive, error-prone LLM judgement made at the worst possible moment, with the least
context, in the latency-sensitive path. Deferring is strictly better here: the stale record stops being retrieved
and reinforced, so its activation decays while the current one's is refreshed on every use. Interference between
the two (principle 7) accelerates the separation. The conflict resolves itself, correctly, from usage evidence
rather than from a guess.

The cost is a window during which both records exist and could both be recalled. That is accepted: recall ranks
by activation, so the fresher record dominates almost immediately, and a caller that needs certainty can read
timestamps off the results it got.

### 5. Durable learnings, not raw event records

What gets stored is the generalization, not the transcript. *"This repo uses `pytest` fixtures, not
`unittest.TestCase`"* is durable. *"The user ran the test suite at 14:32"* is not — it is an event, true forever
and useful almost never. Raw interactions are buffered for processing and discarded after; only extracted
learnings enter the memory store.

For a coding agent specifically, the durable categories are project conventions, architectural constraints,
tooling and environment facts, recurring failure modes, and stated user preferences — things that will still
change the agent's behaviour a hundred turns later.

### 6. Explicit choices outrank inferred preferences

A preference the user stated outright ("always use tabs", "don't touch the migrations directory") is recorded as
an explicit choice: higher initial importance, slower decay, and — critically — it is not overridden by
contradicting *inferred* evidence. A preference guessed from observed behaviour is recorded as inferred: lower
initial importance, faster decay, freely superseded.

Every record therefore carries its provenance. Collapsing the two produces the failure where an agent watches a
user work around a stated rule twice and quietly concludes the rule is gone.

### 7. Adaptive decay, in three layers

Not one forgetting mechanism but three, addressing different causes of a memory becoming worthless:

1. **Passive decay** — unused memories fade on a time curve. Handles the memory that was true and simply stopped
   being relevant. Refreshed on every retrieval, so what the agent actually uses stays hot.
2. **Interference-based forgetting** — memories that are mutually similar and crowded suppress each other.
   Handles the memory that is redundant rather than stale: in a dense cluster of near-identical learnings, they
   cannot all stay strong, and the ones that stop being retrieved lose. This is also what makes principle 4's
   deferred conflict resolution converge quickly instead of drifting.
3. **Graceful degradation** — a fading memory is *compressed* before it is deleted: full record → summary → gist
   → tombstone → gone. Handles the memory that is mostly stale but retains a usable kernel, and avoids the cliff
   where something crosses a threshold and disappears in one step while a caller still needed the gist of it.

---

## Target Architecture — `mem_manage/`

### Record shape

Every record, regardless of type, carries:

| Field | Purpose |
|---|---|
| `created_at` | Principle 1. Set at the store layer; the LLM never supplies it. |
| `last_accessed_at` | Principle 1. Bumped on every retrieval that returns this record. |
| `activation` | Principle 2. The single scalar all lifecycle decisions read. |
| `importance` | The initial, provenance-weighted value activation starts from. |
| `provenance` | `explicit` \| `inferred`. Principle 6 — drives both initial importance and decay rate. |
| `fidelity` | Current degradation tier (principle 7, layer 3). |
| `access_count` | Reinforcement input to activation. |
| `content` / `content_embedding` | The learning itself, and its vector for similarity and interference. |

### Lifecycle

```
raw interaction
      │
      ▼  (buffered, never written directly to memory)
┌──────────────┐
│  extract     │  interaction → candidate durable learnings, tagged explicit|inferred   (principle 5, 6)
└──────┬───────┘
       ▼
┌──────────────┐
│  consolidate │  dedupe → merge → summarize against similar existing records           (principle 3)
│              │  contradiction? write new, leave old standing                          (principle 4)
└──────┬───────┘
       ▼
┌──────────────┐
│  store       │  timestamped, activation initialised from importance × provenance      (principle 1, 2)
└──────┬───────┘
       ▼
┌──────────────┐
│  recall      │  rank by similarity × activation; bump activation + last_accessed_at   (principle 2)
└──────┬───────┘
       ▼
┌──────────────┐
│  maintain    │  passive decay · interference suppression · degrade tier · hard-delete (principle 7, 3)
└──────────────┘      offline, scheduled — never in the request path
```

`recall` is the only stage on the agent's critical path. `extract`, `consolidate` and `maintain` run offline —
consistent with the precedent already established in this repo (Decisions.md ADR-013, ADR-014: the request path
does not pay for memory formation, and deterministic Python does the mutation once the LLM has done the judging).

### Formulae

Derived from **["Human-Inspired Memory Architecture for LLM Agents"](https://arxiv.org/pdf/2605.08538v1)**
(arXiv:2605.08538v1). Its published constants are the paper's calibration and are treated here as **starting
points to be re-derived against coding-agent traces**, not settled configuration. The paper's own evaluation
includes a VSCode dataset — closer to this module's workload than a general-chat benchmark — which is why it was
chosen as the source.

| # | Mechanism | Formula | Governs here |
|---|---|---|---|
| 1 | Composite importance | `S(e) = Σᵢ wᵢ · fᵢ(e)` over five factors — recency, frequency, surprise, entity salience, outcome (paper weights `0.25 / 0.25 / 0.20 / 0.15 / 0.15`) | The **initial** value a new record's activation starts from. Principle 6 enters here: `provenance = explicit` weights the outcome/salience terms up. |
| 2 | Passive decay | `I(t) = I₀ · e^(−λt)`, `t` in hours since encoding (paper: `λ = 0.001`, ≈29-day half-life) | Principle 7 layer 1. `t` resets on retrieval, which is what makes actively-used memories persist indefinitely. |
| 3 | Interference | `I_interference = Σⱼ wⱼ · sim(mᵢ, mⱼ)` (paper: retroactive `0.6`, proactive `0.4`) | Principle 7 layer 2, and the accelerator for principle 4's deferred conflict resolution. `sim()` is the same embedding similarity consolidation uses. |
| 4 | Maturation | `A(t) = 1 / (1 + e^(−(t − t½)/k))` (paper: `t½ = 168 h`, `k = 48`) | The sigmoid ramp a new record climbs before it is fully trusted in recall — a learning seen once should not immediately outrank one confirmed across a week. Gates three zones, not one cutoff: `A < 0.3` inactive (RAG covers the gap), `0.3 ≤ A < 0.5` can influence search ranking but never surfaces in context, `A ≥ 0.5` retrievable. |
| 5 | Reconsolidation | Paper §7.2: retrieved memories enter a 60-minute labile window; new information blends in by confidence/recency/contradiction-severity; outcome-based reinforcement. No exact blending formula given — the paper states this was not meaningfully validated (too few cross-session contradictions in its benchmark). | **Not yet adopted here.** Research.md topic 10 works out a candidate formula set (`U_o`, `E_x`, `P_new`, `B_x`, `R_review`) extending this, but it resolves contradictions as an active, judged decision at consolidation time — which is in tension with Principle 4 below (conflicts are written alongside the old record and left to passive decay, with no write-time "which one is right" judgment anywhere). That tension is unresolved and needs an ADR before either mechanism is implemented. |
| — | Graceful degradation | Fidelity ladder `L0` (full record) → `L2` (summary) → `L3` (gist) → `L5` (tombstone) → hard delete, stepped by age and activation | Principle 7 layer 3. Triggered by the record's own state, not by storage pressure. |

> **Verify before implementing.** These were read out of the paper during design, not transcribed from a
> validated build. Check each equation, symbol, and constant against the source text before writing code against
> it, and record the calibration actually adopted in Decisions.md. Row 5 remains flagged even after a full
> read-through (2026-09-02, Research.md topic 10) since it was never reduced to code, only to a candidate design.

### Deliberately out of scope

- **No tool-calling anywhere.** The constraint that stalled the evaluation (ADR-010, ADR-024) is a design input
  now: extraction and classification use plain-JSON prompting with repair, exactly as `memora_mini/json_fix.py`
  already does.
- **No cloud egress.** Interaction content stays local. This is the precedent set in Research.md topic 6 and the
  one thing the Mem0 first pass violated (ADR-022).
- **The model never proposes a delete.** Deletion is a deterministic consequence of activation, computed in
  Python. Same rule as ADR-014.
- **Not an agent framework.** `mem_manage/` is a library with a narrow interface; it does not own the graph, the
  prompt, or the LLM client.

---

## Test Harness — `Sample_Coding_Agent/`

The agent `mem_manage/` gets wired into and exercised against. It is currently the **unconverted** Mem0
first-pass chatbot inherited from the evaluation — a single-file LangGraph app with a customer-support persona,
calling Mem0's hosted client directly. Converting it (coding-agent persona and task set, Mem0 swapped for
`mem_manage/`) is prerequisite work for testing the module.

```
Sample_Coding_Agent/
├── .venv/           uv-managed Python 3.13: mem0ai + langgraph + langchain-openai + python-dotenv (gitignored)
├── main.py          single-file LangGraph chatbot: one `chatbot` node, mem0 MemoryClient search + add
└── run_log.txt      captured 5-turn REPL transcript, hosted Mem0 Platform, live LLM
```

### Current state (pre-conversion)

**Graph** — `START → chatbot → chatbot` (self-loop, no edge to `END`). `chatbot` (`main.py:31-80`) is the only
node: it searches Mem0 for memories filtered by `user_id`, builds a system prompt from the results, calls the LLM,
then writes the turn back via `mem0.add()`. `run_conversation()` (`main.py:89-97`) drives the graph via `.stream()`
and returns as soon as the first event carries a message — which is what keeps the self-loop (`main.py:85`) from
actually looping forever in practice (Bugs.md BUG-005).

**Memory model** — everything in one Mem0 space scoped only by a hardcoded `mem0_user_id = "alice"`
(`main.py:101`). No role separation, no accept/reject step; every turn is written unconditionally via
`mem0.add()` (`main.py:68`), and Mem0's own opaque extraction decides what becomes durable. This is precisely the
accumulate-everything shape `mem_manage/` exists to replace, which makes it a useful before/after baseline.

**Storage backend** — `MemoryClient()` (`main.py:23`) is Mem0's *hosted* Platform (`api.mem0.ai`), authenticated
via `MEM0_API_KEY`. It is the one point in the repo that sends interaction content to a third-party cloud service
(ADR-022, Research.md topic 6). Replacing it with `mem_manage/` closes that gap as a side effect.

**Known issues** — BUG-002 (intermittent DNS failure reaching `api.mem0.ai`, traced to the local router's IPv6
resolver, not a code defect), BUG-004 (`mem0.add()` reports "0 memories added" despite writes provably
succeeding), BUG-005 (the self-loop above). All three are Mem0-side or wiring-side and are expected to disappear
with the conversion rather than be fixed in place.

---

## Prior art

Working code in the repo that is **not** part of the deliverable, kept because its mechanisms informed the design
above and its test suite still passes.

### `memora_mini/` — LangMem's taxonomy, reimplemented natively

A ~900-line native reimplementation of LangMem's memory *taxonomy* (episodic / semantic / procedural) and *store
interface shape*, with no `langmem` import anywhere and no tool-calling. Built after the SDK-based prototype
(`temp_graph/`, deleted) hit the `trustcall` tool-calling blocker (Research.md topic 7; Decisions.md ADR-010).

```
memora_mini/
├── config.py            all constants, feature flags, env loading (repo-root .env)
├── llm.py               one OpenAI-compatible chat client, no tool-calling
├── json_fix.py          fence-strip -> json_repair -> Pydantic validate
├── embeddings.py        sentence-transformers all-MiniLM-L6-v2, 384-dim, local only
├── prompts.py           every prompt string; each asks for JSON array XOR one enum token
├── facts.py             curated seed data for the semantic namespace
├── ingest.py            corpus/*.md -> chunk -> embed -> `documents` collection
├── store/
│   ├── protocol.py      MemoryStore Protocol (put/get/search/delete), BaseStore-signature-compatible
│   ├── chroma_store.py  ChromaMemoryStore — the only code path that creates a Chroma collection
│   └── namespaces.py    the four namespace tuples + the interactions buffer + name mapping
├── memory/
│   ├── schemas.py       EpisodicMemory, FailureMemory, SemanticFact, PromptRevision, MemoryBase
│   ├── recall.py        strength-based re-rank wrapper over store.search()
│   ├── extract.py       stage 1 — one LLM call per interaction -> candidate memories
│   ├── classify.py      stage 2 — one LLM call per (candidate, neighbour) -> one enum token
│   ├── apply.py         stage 3 — pure Python; the only module that writes a memory namespace
│   └── reflect.py       orchestrates extract -> classify -> apply, offline only
├── graph/
│   ├── state.py         RAGState TypedDict
│   ├── nodes.py         the six node functions
│   └── build.py         StateGraph wiring
├── corpus/              5 small .md fixtures (includes the ASD acronym collision)
├── main.py              CLI REPL
└── demo.py              scripted end-to-end walkthrough
```

**What carries forward into `mem_manage/`:** the offline three-stage formation pipeline (extract → classify →
apply, with all mutation in deterministic Python); strength-based recall re-ranking with a recency term; the
four-verb store protocol; and JSON-repair-instead-of-tool-calling. **What does not:** supersede-forever with no
reclamation, exact-similarity classification without an interference notion, and namespace separation by memory
*type* rather than by activation state.

#### Memory formation pipeline (offline, never in the request path)

```
pending interactions (Chroma "interactions" buffer, reflected=False)
              │
              ▼  every LEARN_EVERY_N successes, or the `learn` command
    ┌─────────────────────┐
    │  extract.py         │  1 LLM call / interaction -> JSON array (<= MAX_CANDIDATES_PER_INTERACTION)
    └─────────┬───────────┘
              ▼
    ┌─────────────────────┐
    │  classify.py        │  recall top-3 neighbours; 1 LLM call / (candidate, neighbour) -> 1 enum token
    └─────────┬───────────┘  DUPLICATE | CONTRADICTS | REFINES | UNRELATED  (unparseable -> UNRELATED)
              ▼
    ┌─────────────────────┐
    │  apply.py (no LLM)  │  DUPLICATE   -> bump hit_count
    │                     │  REFINES     -> supersede with Python-union merge
    │                     │  CONTRADICTS -> supersede + audit both versions
    │                     │  UNRELATED   -> insert
    └─────────┬───────────┘
              ▼
  memory_audit.jsonl (append-only) + the four memory namespaces
```

#### The query graph (`graph/build.py`)

```
load_memory -> retrieve -> generate -> judge -> (INSUFFICIENT & budget left ? retrieve : log_interaction) -> END
```

- **load_memory** — recalls semantic facts and semantically-similar prior failures for the query. No exact-string
  matching anywhere (closes BUG-009 from Memora's design; Decisions.md ADR-018).
- **retrieve** — two tracks kept separate end to end: the `documents` collection and the `episodic` namespace,
  filtered on `track="learned_qa"` (and, on a retry iteration, additionally on `evidence_type`). Never merged here.
- **generate** — the only place the two tracks combine, at the context boundary: learned-QA section first under an
  explicit precedence rule, source documents second. Failure memories are injected as positive redirection built
  from `missing_information`, capped at `MAX_FAILURE_INJECTIONS`.
- **judge** — one LLM call, one enum token (`OK` | `INSUFFICIENT`). Retry budget `MAX_ITERATIONS = 2`.
- **log_interaction** — persists the interaction into the pending-reflection buffer; nothing here calls an LLM.

#### Module breakdown

**`config.py`** — all constants and env loading in one place; nothing else in the package reads `os.environ`
directly. Loads the repo-root `.env` (`REPO_ROOT / ".env"`), not `LangMem/.env` — this changed when `memora_mini/`
was promoted to a first-class root-level package (Status.md, 2026-07-30). Defines the LLM role config (one
endpoint, every role), embedding config, storage paths, the four namespace-adjacent constants, recall/strength
weights, retrieval top-k's, and memory-formation guard thresholds (`MAX_OPS_PER_RUN`, `PROTECTED_HIT_COUNT`,
`CONTRADICTION_STRIKES_REQUIRED`, `DRY_RUN_MEMORY_OPS`, default `True`).

**`store/protocol.py`, `store/namespaces.py`, `store/chroma_store.py`** — `MemoryStore` is a `typing.Protocol` with
exactly four verbs (`put`, `get`, `search`, `delete`) whose parameter names, ordering, and keyword-only markers are
held byte-compatible with LangGraph's `BaseStore` (ADR-012), even though nothing here imports LangGraph's store
module. `ChromaMemoryStore` is the only implementation and the only code path that creates a Chroma collection:
`open_collection()` pins `hnsw:space="cosine"` on create and asserts it on every open, raising loudly on a mismatch
(ADR-019). `namespaces.py` defines the four memory namespaces plus a fifth, non-memory `interactions` buffer, and
the single `"__".join(namespace)` mapping to a Chroma collection name. Chroma metadata only accepts scalars, so
`_encode`/`_decode` JSON-flatten list fields on write and restore them on read — always at the store layer, never
at call sites. `update_metadata()` is a metadata-only Chroma `update()` (no re-embed), used for
`hit_count`/`last_hit_at` bumps on every recall.

**`memory/schemas.py`** — five Pydantic models: `MemoryBase` (store-managed fields every memory type shares —
`hit_count`, `last_hit_at`, `active`, `superseded_by`, `contradiction_strikes`, `memory_type`, `created_at`; the LLM
never sets these), `EpisodicMemory`, `FailureMemory`, `SemanticFact`, `PromptRevision` (`approved` always `False` on
write), plus `ClassificationVerdict`. Each subclass implements `to_text()`, the string that actually gets embedded.

**`memory/recall.py`** — wraps `store.search()` with a client-side strength re-rank:
`score = similarity * (1 + w_hits * log1p(hit_count)) * recency_decay(last_hit_at)`. Over-fetches
`limit * OVERFETCH_FACTOR` before re-ranking and truncating, drops hits below `SIMILARITY_FLOOR` when a semantic
query was given, and — unless called with `bump=False` (used by `classify.py`, since reflection is offline
bookkeeping and must not inflate the hit counts that drive recall) — bumps `hit_count`/`last_hit_at` on every
returned item. `recency_decay()` floors at `RECENCY_FLOOR` (0.5) with a `RECENCY_HALF_LIFE_DAYS`-day half-life, so
decay alone can never zero out a memory, only de-prioritize it. *(This floor is exactly the limitation
`mem_manage/`'s decay model removes: here decay can only re-rank, never retire.)*

**`memory/extract.py`, `classify.py`, `apply.py`, `reflect.py`** — `extract.py` makes one LLM call per interaction,
asking for a JSON array of at most `MAX_CANDIDATES_PER_INTERACTION` candidates; fields Python can derive (`track`,
`source_paths`) are filled in afterwards rather than asked for. `classify.py` recalls each candidate's top-
`CLASSIFY_NEIGHBOURS` neighbours and makes one LLM call per pair, returning a single enum token via
`json_fix.parse_enum` (unparseable → `UNRELATED`, the fail-safe default because it maps to insert, never mutate);
`strongest()` picks the highest-priority verdict when neighbours disagree (`CONTRADICTS > REFINES > DUPLICATE`).
`apply.py` is pure Python and the *only* module that writes to a memory namespace: a fixed table turns each verdict
into a `MemoryOp` (`plan()`), then `apply_ops()` executes (or, in dry-run, only logs) the batch, enforcing
`MAX_OPS_PER_RUN`, dropping ops whose `target_key` no longer exists, and protecting high-`hit_count` entries from a
single `REFINES`/`CONTRADICTS` verdict (`PROTECTED_HIT_COUNT`, `CONTRADICTION_STRIKES_REQUIRED`). `reflect.py`
orchestrates all three stages over two lanes — episodic (from `OK` interactions) and failure (from `THUMBDOWN`
interactions) — using the *same* code path for both, which is what makes repeated thumbdowns on one theme
consolidate into a single entry instead of accumulating. It also runs `propose_prompt_revisions()`: a deterministic
(no LLM) rule turning a failure theme recurring `PROCEDURAL_PROPOSAL_HITS` times into a `PromptRevision` with
`approved=False`.

**`json_fix.py`** — the only thing standing between an 8B model's prose habits and a validated Pydantic object,
since there is no tool-calling and no structured-output helper anywhere. Three tiers: `strip_fences()` (seek the
outermost brackets), `parse_json()` (`json.loads`, then `json_repair.repair_json` on failure), and `parse_list()`
(validate each array element against a Pydantic schema, silently dropping bad elements rather than discarding the
whole batch — partial success beats total failure). `parse_enum()` handles the single-token responses used by
`classify.py` and the graph's `judge` node.

**`llm.py`** — a deliberately thin `OpenAI` client wrapper pointed at
`CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME`. No `tools=`, no `.bind_tools()`, no `trustcall`
(Research.md topic 7). `chat()` retries with exponential backoff up to `LLM_MAX_ATTEMPTS`; `is_reachable()` is a
short-timeout probe so `demo.py`/`main.py` fail fast instead of hanging on the request path's 120s timeout.

**`graph/state.py`, `nodes.py`, `build.py`** — `RAGState` is a `TypedDict` carrying the query, iteration counter,
the two retrieval tracks, recalled semantic facts and failure memories, the assembled prompt, the answer, the judge
verdict, and a handle to the `store` itself (passed through state rather than closed over). `nodes.py` implements
the node functions as plain `state -> partial-state` functions. `build.py` wires the five-node `StateGraph` with one
conditional edge out of `judge` and exposes `ask()` as the single entry point for `main.py` and `demo.py`.

**`facts.py`, `ingest.py`, `corpus/`** — `facts.py` seeds the semantic namespace by hand (three facts, including
the ASD-acronym-collision disambiguation rule) rather than extracting automatically (ADR-016). `ingest.py` chunks
`corpus/*.md` (paragraph-greedy, falling back to a character window for oversized paragraphs) into the `documents`
collection, which is not a memory namespace and is read-only at query time. `corpus/` holds five small fixtures:
`asd_autism.md` and `asd_cardiology.md` (the deliberate acronym collision), `vitamin_d.md` (the
contradiction-supersede demo step), `omega3.md`, `evidence_grades.md`.

**`main.py`, `demo.py`** — `main.py` is the CLI REPL: `<question>` runs the graph; `bad <feedback>` logs a thumbdown
against the last answer; `fact <subject> | <fact>` adds a semantic fact by hand; `learn` forces a reflection run;
`stats` prints per-namespace active/superseded counts. Reflection also runs automatically every `LEARN_EVERY_N`
successful turns. `demo.py` is the scripted, non-interactive walkthrough of all nine acceptance-criteria steps
(ingest → ask → dry-run learn → live learn → semantically-different rephrasing → thumbdown-then-reword (BUG-009
check) → repeated-thumbdown consolidation → contradiction supersede → final stats).

### `LangMem/` — reference material

Holds the LangMem candidate's environment and documentation (`LangMem_Documentation.txt`, `tutorial_transcript.txt`,
a pinned `requirements.txt`). Reference only; nothing runs out of this directory.

### Superseded: `temp_graph/` (deleted 2026-07-29)

The original LangMem-SDK-based prototype: a two-node LangGraph (`user_input -> generate_answer`) backed by two
ChromaDB collections (`learned_qa`, `failure_lessons`), writing via `langmem.create_memory_manager()` with
`enable_inserts=True, enable_updates=False, enable_deletes=False` (former ADR-009). Never live-LLM-tested end to
end — credentials were blank for its whole existence. Deleted rather than kept, since `memora_mini/` demonstrates
directly why the SDK approach doesn't work here (ADR-010).

---

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| **`mem_manage/`** | **not yet implemented** | Design targets: no tool-calling, no cloud egress, deterministic mutation in Python. |
| Graph orchestration | LangGraph `StateGraph` (`langgraph==1.2.9`) | `memora_mini` (five nodes, one conditional edge) and `Sample_Coding_Agent` (one self-looping node) |
| Memory extraction/classification | Hand-written `memory/extract.py` + `memory/classify.py` | Plain-JSON prompts + `json_fix.py` repair; no tool-calling, no `trustcall` |
| Memory writes | Hand-written `memory/apply.py` | Pure Python, deterministic; the model never proposes a delete |
| LLM | `openai` client against a self-hosted OpenAI-compatible endpoint (`CUSTOM_API_BASE`/`CUSTOM_API_KEY`/`CUSTOM_API_MODEL_NAME`, ~`llama-3.1-8b-instruct`) | Every role (generate, judge, extract, classify) routes to the same endpoint |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` | Local only, CUDA if available, 384-dim, normalised |
| Vector storage | ChromaDB `PersistentClient`, cosine distance | One factory (`store/chroma_store.open_collection`) creates every collection |
| Third-party memory service | `mem0ai` hosted Platform (`api.mem0.ai`) | `Sample_Coding_Agent/` only, pre-conversion; to be removed with the `mem_manage/` swap (ADR-022) |
| Structured-output repair | `json_repair` | Tier 2 of `json_fix.py`, between fence-stripping and Pydantic validation |
| Env/dependency management | `uv`, Python 3.13, root-level `.venv/` | Gitignored; not present in a fresh checkout |
| Config/secrets | `python-dotenv` loading the repo-root `.env` | Resolved by absolute path, never by cwd search (ADR-006, ADR-023) |
| Testing | `pytest`, 58 tests, no LLM server or network required | `tests/` at repo root; covers `memora_mini`'s store, recall, apply, json_fix, reflect, and graph behaviour |

---

## Changelog

### 2026-07-28 — Repo scaffold and LangMem environment

`README.md` and `CLAUDE.md` created; `LangMem/` directory added with a pinned `requirements.txt`
(`uv pip install -r requirements.txt`-installable, `LangMem/.venv`) and the LangMem tutorial reference material
(`tutorial_transcript.txt`, `.env` for provider credentials). No experiment code existed yet at this point.

### 2026-07-29 — `temp_graph/` LangMem-SDK experiment implemented, then superseded

Full first-pass experiment added: `config.py`, `state.py`, `graph.py`, `nodes.py`, `main.py`, `memory_schemas.py` +
`memory_store.py`, `learning.py` (LangMem `create_memory_manager` write-back), and adapted
`llm_caller.py`/`embedding_manager.py`/`llm_setup.py`/`prompts.py` copied from `../RAG-work/app_workflow/services/`.
Verified via smoke test: all modules import cleanly, `build_graph()` runs end-to-end, the embedding model loads
(CPU, 384-dim), and both ChromaDB collections initialize successfully. Live LLM answer generation was never
end-to-end tested (credentials were blank).

Later the same day, a much larger session (`Chat 33 (July 29).txt`) worked through whether LangMem's storage options (Postgres/MongoDB/
Redis-backed `BaseStore`, semantic search via MongoDB Atlas Vector Search) fit Memora's constraints, concluded they
didn't (local `mongod`, no cloud egress — Research.md topics 5-6), then set out to build **`memora_mini`**: a
native reimplementation of LangMem's taxonomy and store-interface shape, deliberately avoiding the `langmem`
package because its manager layer depends on `trustcall`, which depends on tool-calling, which the project's local
LLM endpoint does not support (Research.md topic 7; ADR-010).

`memora_mini/` was built bottom-up: `config.py`/`embeddings.py`/`store/protocol.py`/`store/chroma_store.py`/
`memory/recall.py` first, with `tests/test_store.py` and `tests/test_recall.py` passing (19 tests) before any
LLM-touching code existed; then `json_fix.py`/`llm.py`; then the three-stage memory pipeline (`extract.py`,
`classify.py`, `apply.py`, `reflect.py`) with `tests/test_apply.py` and `tests/test_reflect.py`; then the five-node
graph (`tests/test_graph.py`); then `ingest.py`, the `corpus/` fixtures (including the deliberate ASD acronym
collision), `main.py`, and `demo.py`. Verified: 56 tests passing, then 58 after adding semantic-facts and
procedural-proposal coverage; `demo.py` run structurally against a fake LLM harness (the real endpoint was
unreachable — connection timeout) confirmed all nine acceptance-criteria steps end to end, including
thumbdown-consolidation (4 → 1 active entry) and a CONTRADICTS supersede with full audit trail. `temp_graph/` was
then deleted entirely (1,446 lines removed) as fully superseded.

### 2026-07-30 — `memora_mini/` and `tests/` promoted to repo root

Both directories moved from being `temp_graph/` siblings to first-class repo-root packages. `config.py`'s
`ENV_PATH` was updated to load the repo-root `.env` (`REPO_ROOT / ".env"`) instead of `LangMem/.env`, and the
active Python environment moved from `LangMem/.venv` to a root-level `.venv/`. Verified: all 58 tests still pass
from the new location with no other code changes required — the only stale references left behind were setup
commands in `temp_project_description.md`, which were corrected to the new paths.

### 2026-07-30 — Documentation consolidated onto `memora_mini`

This `docs/` five-file system, which previously described only the deleted `temp_graph/` experiment, was rewritten
from the ground up to describe `memora_mini` as the current state of the LangMem evaluation, using
`Chat 33 (July 29).txt`, the current contents of every `memora_mini/` module, and
`temp_project_description.md`/`temp_decision_notedown.md` as source material. `README.md` was rewritten to match
(and its UTF-16LE encoding bug, BUG-001, fixed in the process). `memora_mini/temp_project_description.md` and
`memora_mini/temp_decision_notedown.md` were deleted once their content was folded in, so a single documentation
set (`docs/`) remains. `graphify-out/` was regenerated against the updated tree.

### 2026-07-30 — Mem0 candidate: `Sample_Coding_Agent/` first pass, then evaluation paused

`Sample_Coding_Agent/` created (then named `Customer_Support_Agent/`): a single-file LangGraph chatbot (`main.py`)
calling Mem0's hosted `MemoryClient` directly (`mem0.search()`/`mem0.add()`), with its own `uv`-managed `.venv`.
First run crashed with `httpx.ConnectError: getaddrinfo failed` inside `MemoryClient()`'s startup auth check
(BUG-002); diagnosed as the Wi-Fi adapter's link-local IPv6 DNS resolver intermittently timing out, not a code
defect. Separately found `load_dotenv()` was called with no path and never found the repo-root `.env` (BUG-003),
fixed the same way `temp_graph/` was (ADR-006) by resolving `Path(__file__).resolve().parent.parent / ".env"`
explicitly (ADR-023). A live 5-turn conversation was then captured end-to-end (`run_log.txt`) against the hosted
Mem0 Platform and a live LLM, demonstrating growing recall across turns (0 → 1 → 3 → 6 → 8 relevant memories) —
but every turn's `mem0.add()` logged "0 memories added" despite those same later searches proving new memories
were in fact being written (BUG-004, open). A parallel research pass (Research.md topic 9) corrected an initial,
partly-wrong answer about self-hosted Mem0's OSS capabilities against Mem0's actual current (v3) source and docs —
concluding, notably, that Mem0's core pipeline does *not* hard-require tool-calling.

Evaluation was then paused: across candidates so far, tool-calling had kept resurfacing as a design constraint (a
hard blocker for LangMem's SDK layer, a soft one shaping Mem0's provider/extraction choices), and an upgrade to a
tool-calling-capable local LLM was under consideration but not decided (ADR-024). That pause is what the
2026-09-02 pivot resolves — by building the module rather than resuming the search.

### 2026-09-02 — Repurposed: from evaluation sandbox to `mem_manage/`, a memory module for coding agents

The repo's purpose changed. It is no longer a comparison harness for external memory libraries; it now builds one
module, `mem_manage/`, targeting **coding agents** rather than the conversational/support agents the evaluation
candidates were shaped around. The pivot follows from ADR-024's pause: the evaluation had established both a hard
constraint (no tool-calling available) and a shared gap across every candidate examined — they accumulate memory
and none of them forget deliberately.

Seven design principles were fixed (timestamps on every entry; a single activation scalar; consolidation by
dedupe/merge/summarize/hard-delete; conflicts written alongside rather than overwriting; durable learnings over raw
events; explicit choices outranking inferred preferences; three-layer adaptive decay), and
arXiv:2605.08538v1 *"Human-Inspired Memory Architecture for LLM Agents"* was adopted as the formula source —
composite importance, exponential passive decay, interference scoring, the maturation sigmoid, and the
graceful-degradation fidelity ladder. Its constants are starting points pending re-derivation against
coding-agent traces; the equations are recorded here as read during design and are flagged for verbatim
verification before implementation.

`Customer_Support_Agent/` was renamed **`Sample_Coding_Agent/`** (contents unchanged) and re-scoped from "Mem0
candidate under evaluation" to "test harness for `mem_manage/`" — its conversion from a customer-support persona
to a coding agent, and the replacement of its Mem0 dependency, are the prerequisite next steps. `memora_mini/`,
`LangMem/`, and the `temp_graph/` record were reframed as prior art; their content is retained here unchanged,
with the mechanisms that carry forward into `mem_manage/` (and the ones that don't) called out explicitly.
`README.md` and this document were rewritten to match. `mem_manage/` itself remains empty — design only, no code.

### 2026-09-02 — Paper read in full; reconsolidation gap surfaced as an unresolved design tension

arXiv:2605.08538v1 was read end to end (previously only "read out of the paper during design," per the Formulae
table's own verification flag). This confirmed the four already-adopted equations and added detail the table
didn't have: consolidation's top/middle/bottom 20/60/20 promote/retain/prune bands, the maturation sigmoid's three
retrieval zones (now folded into row 4 above), and a chronological-consistency quarantine filter (15-minute TTL
against out-of-order/duplicate/causally-inverted events) not previously recorded here. A follow-on research pass
went deeper into §7.2 (Reconsolidation), which the paper itself only sketches and flags as unvalidated, and worked
out a candidate formula set for resolving contradictory memories via versioned graph claims (Research.md topic
10) — added above as Formulae row 5, explicitly not adopted. That candidate procedure is an active, judged
resolution, which sits in real tension with Principle 4's decision to defer all conflict resolution to passive
decay; row 5's note flags this, and the reconciliation is left open pending an ADR. No code changed; `mem_manage/`
remains empty.

---
