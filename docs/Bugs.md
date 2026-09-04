### BUG-001 · `README.md` and `LangMem/requirements.txt` saved as UTF-16LE instead of UTF-8

| Field | Detail |
|---|---|
| **Issue** | Both `README.md` (repo root) and `LangMem/requirements.txt` were encoded as UTF-16LE (with CRLF line endings, `README.md` without a BOM, `LangMem/requirements.txt` with an `fffe` BOM), instead of plain UTF-8. |
| **Found Date** | 2026-07-29 |
| **Status** | Partially Resolved — `README.md` fixed 2026-07-30; `LangMem/requirements.txt` still open |
| **Severity** | LOW |
| **File** | `README.md` (fixed), `LangMem/requirements.txt` (still affected) |
| **Description** | A byte-level read of both files confirmed every character null-byte-padded (e.g. `23 00 20 00 4d 00 ...` for `"# M..."`). Reading either file with a tool that assumes UTF-8 (or naive byte-oriented `grep`/diff) renders every character as spaced-out garbage, e.g. `a i o h a p p y e y e b a l l s = = 2 . 7 . 1` instead of `aiohappyeyeballs==2.7.1`. Both were originally produced by shell redirection (`>`) rather than a text-editor write, which on this environment's PowerShell defaults to UTF-16LE for redirected output rather than UTF-8. |
| **Root Cause** | Files created via PowerShell `>`/`Out-File`-style redirection inherit that shell's non-UTF-8 default text encoding, rather than being written through a UTF-8-explicit path. A rewrite attempt on 2026-07-29 (overwriting `README.md`'s content entirely via the editor's file-write tool) still produced UTF-16LE output (that time without a BOM) even though other brand-new files written the same session (`docs/*.md`) came out as plain UTF-8 — so the encoding appeared tied to that overwrite being applied to an already-UTF-16 file, not to how the content was authored. |
| **Solution** | On 2026-07-30, `README.md` was fully rewritten (content plus a fresh write) as part of the documentation-consolidation pass and re-verified byte-for-byte as plain UTF-8 (`data = open(...).read(); data[:1] == b'#'`, no null-byte padding). `LangMem/requirements.txt` was left untouched — it belongs to the now-reference-only `LangMem/` tutorial material rather than the active `memora_mini/` package (which has its own, already-UTF-8, `memora_mini/requirements.txt`), so re-saving it was out of scope for this pass. `uv`/`pip` and most modern `git` tooling tolerate a UTF-16 BOM in practice, so the remaining instance has not blocked any workflow, but it should not be relied upon if `LangMem/requirements.txt` is ever installed from again. |
| **Date Resolved** | 2026-07-30 (`README.md` only) |

---

### BUG-002 · Intermittent `httpx.ConnectError: getaddrinfo failed` from `MemoryClient()` against Mem0's hosted Platform

| Field | Detail |
|---|---|
| **Issue** | `python Sample_Coding_Agent/main.py` crashed on startup with `httpx.ConnectError: [Errno 11001] getaddrinfo failed`, raised from `mem0.client.main.MemoryClient.__init__` → `_validate_api_key()`'s `GET /v1/ping/` call to `api.mem0.ai`. |
| **Found Date** | 2026-07-30 |
| **Status** | Root-caused; not fixed (network-level, outside this repo's control) |
| **Severity** | LOW — intermittent, self-resolves on retry |
| **File** | `Sample_Coding_Agent/main.py:23` |
| **Description** | The crash is a DNS resolution failure, not an application bug: `nslookup api.mem0.ai` against the machine's default resolver failed outright once, then succeeded on an immediate retry. General connectivity (`ping 8.8.8.8`, `nslookup google.com`) was unaffected throughout. |
| **Root Cause** | `Get-DnsClientServerAddress` showed the active Wi-Fi adapter configured with `fe80::1` — a link-local IPv6 address on the router itself — as its DNS resolver, and Windows tries IPv6 resolution first. Querying that resolver directly 5 times in a row timed out on attempts 1-2 and succeeded on 3-5: the router's IPv6 DNS forwarding is itself intermittently unreliable, not a symptom of anything in this codebase. The IPv4 resolver on the same router (`192.168.1.1`) is only tried as a fallback after the IPv6 one times out (~2s × 3 retries), which matches the delay observed before the crash. |
| **Solution** | Not applied yet. Two options identified: (1) point the Wi-Fi adapter at a public resolver (8.8.8.8/1.1.1.1) instead of the router — fixes DNS for every app, offered but not actioned; (2) self-host Mem0 via Docker so `MemoryClient()`'s calls resolve to `localhost`/a Docker service name instead of `api.mem0.ai` — fixes this one dependency only, since `CUSTOM_API_BASE` (the LLM endpoint) still resolves through the same flaky router path either way (see Decisions.md ADR-022). Current workaround is simply retrying — `run_log.txt`'s captured session ran successfully once DNS happened to resolve. |
| **Date Resolved** | Open |

---

### BUG-003 · `Sample_Coding_Agent/main.py` didn't find the repo-root `.env`

| Field | Detail |
|---|---|
| **Issue** | `main.py` called `load_dotenv()` with no path argument, so it searched from the current working directory upward and never found `.env`, which lives at the repo root (`Memory-Management-Tools/.env`), one directory above `Sample_Coding_Agent/`. `MEM0_API_KEY`/`CUSTOM_API_BASE`/`CUSTOM_API_KEY` all read as unset as a result. |
| **Found Date** | 2026-07-30 |
| **Status** | Resolved |
| **Severity** | LOW |
| **File** | `Sample_Coding_Agent/main.py:11` |
| **Description** | Confirmed no `.env` exists inside `Sample_Coding_Agent/` or is discoverable from it via `load_dotenv()`'s default cwd-based search; the actual file was found at the repo root via a directory listing. |
| **Root Cause** | `Sample_Coding_Agent/` is a sibling of the repo-root `.env`, not a parent of it — `python-dotenv`'s default search only looks upward from the invoking script's/cwd's directory, so it never crosses into a directory it isn't nested under. Identical layout to the one `temp_graph/` hit and fixed via ADR-006. |
| **Solution** | Changed `main.py:11` to `load_dotenv(Path(__file__).resolve().parent.parent / ".env")`, loading the repo-root `.env` explicitly by absolute path — same fix pattern as ADR-006, now also the pattern for this candidate (Decisions.md ADR-023). |
| **Date Resolved** | 2026-07-30 |

---

### BUG-004 · `mem0.add()` always logs "0 memories added" despite memories provably being written

| Field | Detail |
|---|---|
| **Issue** | Every turn in `run_log.txt`'s captured conversation prints `Memory saved: 0 memories added` / `Memory details: []` from `main.py:69-70`, immediately after the corresponding `mem0.add()` call — yet the *next* turn's `mem0.search()` reliably finds a new memory that can only have come from the turn that just claimed to have saved none (e.g. turn 1 logs "0 memories," turn 2's search immediately finds 1 memory describing turn 1's exchange). |
| **Found Date** | 2026-07-30 |
| **Status** | Open |
| **Severity** | MEDIUM — doesn't block functionality (memories are in fact being written and recalled), but makes the app's own logging actively misleading about whether writes succeeded, which matters for an evaluation whose whole point is judging Mem0's write behavior |
| **File** | `Sample_Coding_Agent/main.py:68-70` |
| **Description** | `result = mem0.add(interaction, user_id=user_id)` followed by `result.get('results', [])` returns an empty list on every single turn of the captured session, with no exceptions raised and no errors logged elsewhere. |
| **Root Cause** | Not yet determined. Candidates: Mem0's `add()` response shape for this account/API version may not use a top-level `results` key the way `main.py:69` assumes (silently returning `[]` from `.get()` rather than surfacing a shape mismatch), or extraction/write may happen asynchronously/deferred server-side such that the synchronous `add()` response never carries the eventually-written memory. Needs a direct inspection of the raw `mem0.add()` return payload (not just the `.get('results', [])` projection) to distinguish these. |
| **Solution** | Not yet applied. |
| **Date Resolved** | Open |

---

### BUG-005 · `chatbot -> chatbot` graph edge has no route to `END`

| Field | Detail |
|---|---|
| **Issue** | `main.py:85` wires `graph.add_edge("chatbot", "chatbot")` — the only edge out of the sole node is back to itself — and `END` is never imported or used anywhere in the file. |
| **Found Date** | 2026-07-30 |
| **Status** | Open — latent, not yet triggered |
| **Severity** | LOW |
| **File** | `Sample_Coding_Agent/main.py:85` |
| **Description** | A `StateGraph` whose only node's only outgoing edge points back to itself, with no conditional edge or `END` anywhere, has no defined termination condition. |
| **Root Cause** | Currently masked by how the graph is driven: `run_conversation()` (`main.py:93-97`) iterates `compiled_graph.stream(...)` and `return`s out of the function as soon as the first event containing a message arrives — so the generator is abandoned after one step and the self-loop is never actually followed. Nothing currently calls `.invoke()` or fully consumes the stream. |
| **Solution** | Not yet applied — flagging since any future change that fully drains the stream (or switches to `.invoke()`) would loop indefinitely. The likely intended fix is either an edge to `END` after `chatbot`, or a conditional edge with an explicit stop condition. |
| **Date Resolved** | Open |

---

### BUG-006 · Unused `ChatGroq` import crashes `mem_manage.compact` at startup

| Field | Detail |
|---|---|
| **Issue** | `python -m mem_manage.compact ./learnings.md` crashed immediately with `ModuleNotFoundError: No module named 'langchain_groq'`, raised from `mem_manage/services/llm_setup.py:20`. |
| **Found Date** | 2026-09-04 |
| **Status** | Resolved |
| **Severity** | LOW |
| **File** | `mem_manage/services/llm_setup.py`, `mem_manage/requirements.txt` |
| **Description** | The traceback pointed at a plain `import` line, not at any code that was actually being exercised — `_default_llm_calls()` in `dedup_merge.py` imports `llm_setup` lazily, and `llm_setup.py`'s own module-level docstring stated that `ChatGroq` stubs had been removed, yet line 20 still imported `ChatGroq` unconditionally. `requirements.txt` line 22 still listed `langchain_groq` too, contradicting its own nearby comment (lines 11-15) saying it wasn't needed. |
| **Root Cause** | Leftover, contradictory code: the module docstring and the actual import had drifted out of sync, and the stale `requirements.txt` line meant even installing dependencies fresh wouldn't have surfaced the mismatch until this exact import path was hit at runtime. |
| **Solution** | Removed the unused `ChatGroq` import from `llm_setup.py` and the corresponding `langchain_groq` line from `requirements.txt`, since the local LLM server was down and Groq needed to become a real, used client (see BUG-007) — at which point the import stopped being dead code and the docstring was updated to match. |
| **Date Resolved** | 2026-09-04 |

---

### BUG-007 · `groq==1.7.0` pin incompatible with `langchain-groq==1.1.3` (`groq<1.0.0` required)

| Field | Detail |
|---|---|
| **Issue** | `uv pip install -r mem_manage/requirements.txt` failed to resolve: "Because `langchain-groq==1.1.3` depends on `groq>=0.30.0,<1.0.0` and you require `groq==1.7.0`, we can conclude that your requirements and `langchain-groq==1.1.3` are incompatible." |
| **Found Date** | 2026-09-04 |
| **Status** | Resolved |
| **Severity** | LOW |
| **File** | `mem_manage/requirements.txt` |
| **Description** | `requirements.txt` pinned `groq==1.7.0` (the current major version at the time it was written) alongside `langchain-groq==1.1.3`, which has never supported `groq`'s 1.x line. |
| **Root Cause** | The two pins were chosen independently without checking `langchain-groq`'s actual dependency bound; `uv pip install --dry-run "langchain-groq"` confirmed the resolver's own fix (`groq==0.37.1`) before anything was changed. |
| **Solution** | Before repinning, verified that downgrading `groq` was safe for this codebase: `llm_caller.py`'s caught exception classes (`BadRequestError`, `RateLimitError`, `AuthenticationError`, etc.) are the standard Stainless-generated names present across that whole version range, not something introduced in 1.x. Repinned `groq` to `0.37.1` in `requirements.txt`; `uv pip install -r mem_manage/requirements.txt` then resolved and installed cleanly (76 packages). |
| **Date Resolved** | 2026-09-04 |

---

### BUG-008 · `.env` misplaced at `mem_manage/.env` instead of the repo root — `GROQ_API_KEY` never loads

| Field | Detail |
|---|---|
| **Issue** | After BUG-006/BUG-007 were fixed, `python -m mem_manage.compact` still failed: `groq.GroqError: The api_key client option must be set either by passing api_key to the client or by setting the GROQ_API_KEY environment variable`. |
| **Found Date** | 2026-09-04 |
| **Status** | Resolved |
| **Severity** | LOW |
| **File** | `mem_manage/.env` (moved to `.env`, repo root) |
| **Description** | A live `GROQ_API_KEY` was in fact present in a `.env` file in the repo — just not at the path `config.py` reads. (A separate detour along the way: running the retry command through the Bash tool raised `ModuleNotFoundError: No module named 'dotenv'` even though `python-dotenv` was confirmed installed in the project `.venv` — that turned out to be the Bash tool shell running under a different, global Python 3.14 install rather than the project's `.venv`, not a real dependency gap; switching to invoking `.venv/Scripts/python.exe` directly resolved it and is unrelated to this bug's actual fix.) |
| **Root Cause** | `config.py` explicitly loads `REPO_ROOT / ".env"` by design (ADR-023, extended to `mem_manage/config.py` by ADR-030) — this is the repo's established convention, confirmed by re-reading both ADRs before touching the file. The actual `.env` (containing the live key, plus three commented-out prior keys) was sitting one directory down, at `mem_manage/.env`, instead. |
| **Solution** | Moved `.env` from `mem_manage/.env` to the repo root via `git mv` (which correctly reported the file as untracked — it was already gitignored, so this was a plain filesystem move with no git history to preserve). The pipeline then ran end-to-end via Groq, producing 4 durable memories from 5 episodic records. |
| **Date Resolved** | 2026-09-04 |

---

### BUG-009 · Embedding model not using CUDA despite a working GPU

| Field | Detail |
|---|---|
| **Issue** | `EmbeddingManager` logged `CUDA not available; running on CPU` on every run, and `EmbeddingManager().device` reported `"cpu"`, despite the machine having a working NVIDIA GPU. |
| **Found Date** | 2026-09-04 |
| **Status** | Resolved |
| **Severity** | MEDIUM (performance — CPU embedding is materially slower on larger corpora) |
| **File** | `.venv` (torch package); `mem_manage/requirements.txt` (documented fix) |
| **Description** | `nvidia-smi` confirmed a working RTX 5050 Laptop GPU (Blackwell architecture, `sm_120` compute capability, driver supporting CUDA 13.x) with headroom (62MiB/8151MiB used). `torch.cuda.is_available()` still returned `False` inside the project's `.venv`. |
| **Root Cause** | The project's `uv`-managed `.venv` had installed `torch==2.14.0+cpu` — plain `pip`/`uv pip install torch` defaults to a CPU-only wheel; the CUDA-enabled build lives on a separate PyTorch package index, not PyPI. A red herring along the way: global-PATH `pip`/`python` pointed at an entirely different Python 3.14 install that happened to already have `torch==2.11.0+cu128` installed, which briefly made it look like a driver/environment problem rather than a wheel-selection one — `which python`/`pip show torch` inside an activated shell were pointing at that other install, not the project's `.venv`. |
| **Solution** | Reinstalled directly into the project's `.venv` via `uv pip install --python .venv/Scripts/python.exe --index-url https://download.pytorch.org/whl/cu130 "torch==2.14.0+cu130" --reinstall-package torch` (matches the RTX 5050's Blackwell architecture and the driver's CUDA 13.x support; a 1.9GB download). Verified: `torch.cuda.is_available()` → `True`, `torch.cuda.get_device_name(0)` → `"NVIDIA GeForce RTX 5050 Laptop GPU"`, a GPU tensor op ran correctly, and `EmbeddingManager().device` → `"cuda"`. Documented the exact install command in `mem_manage/requirements.txt` (a normal `torch==` pin can't express a CUDA build since it lives on a separate index), so a future plain `uv sync`/`uv pip install -r requirements.txt` doesn't silently regress back to the CPU wheel. |
| **Date Resolved** | 2026-09-04 |

---

### BUG-010 · `graphify update <subpath>` creates a stray duplicate graph instead of updating the root graph (recurrence)

| Field | Detail |
|---|---|
| **Issue** | After editing `llm_caller.py`, `dedup_merge.py`, and `consolidate.py`, running `graphify update mem_manage` created a second, separate `mem_manage/graphify-out/` directory instead of updating the existing repo-root `graphify-out/`. |
| **Found Date** | 2026-09-04 |
| **Status** | Resolved (recurrence of a known gotcha) |
| **Severity** | LOW (tooling gotcha, no data lost) |
| **File** | `mem_manage/graphify-out/` (created, then deleted) |
| **Description** | `graphify update <subpath>` scopes both the re-extraction and its own output directory to that subpath, rather than updating the single existing root-level graph the repo actually uses. |
| **Root Cause** | This exact behavior was already discovered and logged for future reference on 2026-09-03 (see Status.md, that date's entry) — "the correct invocation is always `graphify update .` from the repo root." The note alone didn't prevent the repeat this session, since the natural instinct when only a subdirectory changed is to scope the update command to just that subdirectory. |
| **Solution** | Deleted the stray, untracked `mem_manage/graphify-out/` (`git status` confirmed nothing tracked was affected) and re-ran `graphify update .` from the repo root, which correctly updated the existing root graph. Recording this as its own bug entry (rather than assuming the 2026-09-03 note was sufficient) since a purely narrative reminder didn't stick — always invoke `graphify update .` from the repo root for this single-root-graph project, never a subpath, regardless of how localized the actual code change was. |
| **Date Resolved** | 2026-09-04 |

---

### BUG-011 · `[auto] ...` boilerplate prefix on auto-generated failure entries distorts embedding similarity, causing false merges

| Field | Detail |
|---|---|
| **Issue** | Two topically unrelated auto-generated test-failure entries in `learnings.md` (one about a Groq auth error, one about an unrelated logging-format bug) merged together at `MERGE_SIMILARITY_THRESHOLD=0.60`, while a topically related pair — the same Groq auth-error entry and its true narrative sibling (a reviewer note) — scored *lower* similarity and did not merge. |
| **Found Date** | 2026-09-04 |
| **Status** | Resolved |
| **Severity** | MEDIUM (correctness of consolidation output — wrong entries get folded together) |
| **File** | `mem_manage/services/dedup_merge.py` |
| **Description** | Verified with the real production embedder (`sentence-transformers/all-MiniLM-L6-v2`, matching `EmbeddingManager`) against the actual run log: the confirmed false-merge pair scored 0.625 cosine similarity; the true sibling pair inside the intended narrative cluster scored only 0.564-0.576. Since any threshold low enough to admit the true pair (≤0.564) necessarily also admits the false one (0.625), the ranking itself was inverted — not just close — so no single value of `MERGE_SIMILARITY_THRESHOLD` could separate them (see Research.md topic 12). |
| **Root Cause** | Every auto-generated entry shares the exact literal prefix `[auto] \`<command>\` failed (exit <code>): ` — emitted by the sibling project `Bhai-To-Bhai`'s `orchestrator/artifacts.py::run_shared_command()` for every failed shell command a task agent runs (see Research.md topic 11). A short-text embedding model like MiniLM weights that shared, high-frequency template heavily regardless of topic, so two unrelated auto-failures can out-score a real topical pair where only one side is auto-generated. |
| **Solution** | Added `_embedding_text()` to `dedup_merge.py`: a regex (`^\[auto\] \`.*?\` failed \(exit -?\d+\): `) strips the literal boilerplate prefix before text reaches the embedder inside `find_near_duplicate_groups()`, falling back to the full content if stripping would leave nothing. Stored/merged `content` is left untouched — only what's fed to the embedder changes. Verified against the real model: the confirmed false-merge pair dropped from 0.625 → 0.399 similarity, and a second false pair from 0.576 → 0.156, both now safely clear of the unchanged 0.60 threshold (the threshold-raise considered in Research.md topic 12 turned out to be unnecessary). Added 6 tests (4 unit tests on `_embedding_text`, 1 integration test confirming `find_near_duplicate_groups` actually feeds the embedder stripped text); 119/119 tests passed. |
| **Date Resolved** | 2026-09-04 |

---
