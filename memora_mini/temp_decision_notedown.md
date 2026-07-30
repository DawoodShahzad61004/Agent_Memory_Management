# memora_mini — Design Decisions

Same table shape as `../RAG-work/docs/Decisions.md`, so these port back as ADRs directly. Numbered
`MM-xxx` to avoid colliding with the parent project's `ADR-xxx` series.

---

## MM-001 — Reimplement LangMem's taxonomy natively rather than depend on the SDK

| Field | Detail |
|---|---|
| **Decision** | Adopt LangMem's memory taxonomy (episodic / semantic / procedural) and its store interface, but implement both natively. Do not install or import `langmem`. |
| **Date** | July 2026 |
| **Context** | The sandbox exists to evaluate LangMem against the parent project's hand-rolled memory layer. The parent project's only LLM endpoint is a self-hosted OpenAI-compatible server with no tool-calling support. |
| **Options Considered** | (a) Use `langmem`'s `create_memory_manager` as-is · (b) use `langmem` with a shimmed tool-calling adapter · (c) adopt the taxonomy and store interface, implement natively · (d) ignore LangMem and design from scratch |
| **Chosen Solution** | (c) |
| **Rationale** | `langmem`'s manager layer is built on `trustcall`, which is built on tool-calling. Option (a) is simply unavailable. Option (b) means maintaining a shim against two upstream libraries to gain an abstraction we would still have to debug. Option (d) throws away a taxonomy that is a genuinely better fit than the parent project's ad-hoc split. The ideas are portable; the package is not. |
| **Impact** | ~900 lines of implementation instead of a dependency. The store Protocol's signatures are held byte-compatible with `BaseStore` (MM-002) so the decision is reversible if tool-calling ever arrives. The earlier `temp_graph/` prototype, which *did* use `create_memory_manager`, is superseded by this one. |

---

## MM-002 — Store interface signatures held compatible with LangGraph `BaseStore`

| Field | Detail |
|---|---|
| **Decision** | The `MemoryStore` Protocol's four verbs use exactly `BaseStore`'s parameter names, ordering and keyword-only markers. |
| **Date** | July 2026 |
| **Options Considered** | A Protocol shaped for what this code actually needs (simpler, e.g. `search(ns, query, k)`) · a literal `BaseStore` subclass · signature-compatible Protocol |
| **Chosen Solution** | Signature-compatible Protocol |
| **Rationale** | A literal subclass drags in LangGraph's async surface and `Op`/batch machinery for no benefit here. A Protocol shaped only for this code would make the later swap a rewrite of every call site. Matching signatures costs one awkward parameter (`filter` shadows the builtin) and buys a drop-in path: a thin `BaseStore` subclass over the same Chroma collections. |
| **Impact** | `store/protocol.py`. Pinned by `tests/test_store.py::test_store_satisfies_the_protocol`, which asserts the parameter list rather than just duck-typing. |

---

## MM-003 — Supersede, not delete, as the memory lifecycle

| Field | Detail |
|---|---|
| **Decision** | Superseding sets `active=False` and `superseded_by=<new_key>` on the old record and inserts the new one. `delete()` exists but is for operator cleanup only. Recall filters `active=True`. |
| **Date** | July 2026 |
| **Options Considered** | Hard delete on contradiction · in-place update of the existing record · supersede with tombstone · versioned records with an explicit generation counter |
| **Chosen Solution** | Supersede with tombstone |
| **Rationale** | The failure mode being designed against is a *wrong* classification, not a wrong memory. A hard delete makes a bad `CONTRADICTS` verdict from an 8B model unrecoverable — exactly the insert-only problem inverted. In-place update loses the old text, so the audit log cannot show what changed. Tombstones cost storage, which is free here, and make the whole history reconstructable. |
| **Impact** | Every namespace carries `active` / `superseded_by`. Storage grows monotonically — acceptable for a sandbox, and a periodic hard-delete sweep over long-superseded records is the obvious production follow-up. |

---

## MM-004 — Classification is per-pair and single-token

| Field | Detail |
|---|---|
| **Decision** | One LLM call per (candidate, neighbour) pair, returning exactly one of four enum tokens. |
| **Date** | July 2026 |
| **Options Considered** | One call classifying a candidate against all N neighbours at once · one call doing extract + reconcile + merge together (what `create_memory_manager` does) · per-pair single-token |
| **Chosen Solution** | Per-pair single-token |
| **Rationale** | Against an 8B model, a call that must align a candidate with three neighbours *and* emit structured output fails in ways that are hard to attribute. A single token has one failure mode — unrecognised text — with an obvious fail-safe (`UNRELATED` → insert). Cost is `candidates × 3` calls per interaction, which is acceptable because reflection runs offline. |
| **Impact** | `memory/classify.py`. If a stronger model becomes available, the batched form is a strictly cheaper drop-in and only this module changes. |

---

## MM-005 — REFINES merges deterministically in Python, not via an LLM

| Field | Detail |
|---|---|
| **Decision** | The merged record for a `REFINES` supersede is produced by a Python union (concatenate text, union list fields, `max` confidence, preserve `hit_count`), with no LLM call. |
| **Date** | July 2026 |
| **Options Considered** | An LLM merge call producing a clean merged answer · deterministic Python union · keep both records and let recall sort it out |
| **Chosen Solution** | Deterministic Python union |
| **Rationale** | The constraint that `apply.py` is the only module that writes memory is only worth anything if `apply.py` cannot fail nondeterministically. An LLM merge call inside the write path reintroduces exactly that. The cost is uglier merged text — two concatenated answers rather than one synthesised one — which recall tolerates because it matches on embeddings. |
| **Impact** | `memory/apply.py::_merge`. There is deliberately no merge prompt in `prompts.py`. Revisit if merged entries visibly degrade answer quality; the fix is an LLM merge in the *classify* stage, passing the merged text into `plan()`. |

---

## MM-006 — Semantic memory is curated, not extracted

| Field | Detail |
|---|---|
| **Decision** | No automatic extraction path writes to the semantic namespace. Facts are seeded from `facts.py` and added via the REPL's `fact` command. |
| **Date** | July 2026 |
| **Options Considered** | Mine facts from the corpus at ingest time · extract facts during reflection alongside episodic memories · curate by hand |
| **Chosen Solution** | Curate by hand |
| **Rationale** | Asked to mine "domain facts", an 8B model restates whatever chunk it just read, which duplicates the `documents` collection into a namespace that then outranks it in the prompt. The facts that actually earn their place — the ASD acronym collision, the evidence-grade rule — are precisely the ones that require knowing something about the corpus as a whole, which single-chunk extraction cannot see. |
| **Impact** | `facts.py`, `memora_mini/corpus/`. The semantic namespace is small and hand-owned. If the corpus grows, a corpus-wide disambiguation pass (find acronyms with divergent neighbour clusters) is the natural automation, and it is a clustering job, not an LLM job. |

---

## MM-007 — Procedural memory is proposed deterministically and never auto-applied

| Field | Detail |
|---|---|
| **Decision** | When an active failure memory's `hit_count` reaches `PROCEDURAL_PROPOSAL_HITS`, reflection emits a `PromptRevision` with `approved=False`. Nothing in the generate path reads the procedural namespace. |
| **Date** | July 2026 |
| **Options Considered** | An LLM call proposing prompt revisions · deterministic proposal from a recurring failure theme · auto-apply approved revisions at generation time · no procedural memory at all |
| **Chosen Solution** | Deterministic proposal, never applied |
| **Rationale** | A system that rewrites its own system prompt from 8B-model output has no stable baseline to evaluate against — which defeats the point of a comparison sandbox. Emitting the proposal is still worth doing: it surfaces "this theme keeps failing" as a reviewable artifact. Deriving it from a `hit_count` threshold rather than an LLM call keeps it free and reproducible. |
| **Impact** | `memory/reflect.py::propose_prompt_revisions`. Pinned by `tests/test_reflect.py::test_procedural_memory_is_never_injected_into_generation`. Wiring approval into generation is a deliberate, separate decision for whoever ports this. |

---

## MM-008 — Failure injection carries `missing_information`, capped at 2

| Field | Detail |
|---|---|
| **Decision** | Prompt injection uses a derived `missing_information` noun phrase, phrased as positive redirection, capped at `MAX_FAILURE_INJECTIONS = 2` and selected by strength score. |
| **Date** | July 2026 |
| **Options Considered** | Inject raw `user_feedback` (what the parent project stores) · inject a "do not do X" blocklist · inject derived `missing_information` as redirection |
| **Chosen Solution** | Derived `missing_information`, positive phrasing |
| **Rationale** | Raw feedback is a complaint aimed at a person; it is the wrong shape for redirecting retrieval, and it drags tone and irrelevant detail into the prompt. Negative-only phrasing ("do not omit dosing") measurably fails to change model behaviour. The cap exists because embedding recall surfaces far more failure hits than the parent project's exact-string match ever did, and the parent project already hit prompt-bloat problems past roughly 1,800 tokens against an 8B ceiling. |
| **Impact** | `FailureMemory.missing_information`, `prompts.REDIRECTION_LINE`, `graph/nodes.py::load_memory`. Pinned by `tests/test_graph.py` (cap honoured; raw feedback text never reaches the prompt). |

---

## MM-009 — Cosine asserted on open, rather than migrated

| Field | Detail |
|---|---|
| **Decision** | `open_collection()` pins `hnsw:space="cosine"` on create and raises on any collection that reports a different space. |
| **Date** | July 2026 |
| **Options Considered** | Assert and fail loudly · snapshot-and-rebuild migration (what `../RAG-work/app_workflow/services/learned_qa_store.py` does) · compute distance-appropriate scores per collection |
| **Chosen Solution** | Assert and fail loudly |
| **Rationale** | This sandbox has no legacy data, so migration is code that can never be exercised and therefore can never be trusted. Per-collection score handling spreads the assumption `score = 1 - distance` across every call site, which is how the parent project's L2 bug survived for months. One factory, one assertion, one place to look. |
| **Impact** | `store/chroma_store.py::open_collection` — the only code path in the package that creates a collection. **When porting, keep the parent project's migration logic instead**: it handles real data that this assertion would simply reject. |

---

## MM-010 — Interactions buffered in Chroma; the audit trail is a JSONL log

| Field | Detail |
|---|---|
| **Decision** | Pending interactions live in a Chroma collection outside the four memory namespaces. Proposed and applied memory operations are appended to `memory_audit.jsonl`. |
| **Date** | July 2026 |
| **Options Considered** | Interactions in MongoDB (parent-project behaviour) · interactions in a fifth memory namespace · interactions in a non-memory Chroma collection; audit in Chroma · audit as a JSONL file |
| **Chosen Solution** | Non-memory Chroma collection + JSONL audit |
| **Rationale** | MongoDB is excluded by constraint. Making interactions a memory namespace would let raw, unclassified interactions leak into recall. The audit trail is append-only, read by humans, and never read back by the code for behaviour — a log sink, not a datastore, so putting it in a vector store would buy nothing and would require embedding text nobody searches. |
| **Impact** | `store/namespaces.py::INTERACTIONS`, `memory/apply.py::_audit`. This is the one place the "ChromaDB only" rule is interpreted rather than followed literally; flagged here because it is exactly the kind of thing a reviewer should push back on. |
