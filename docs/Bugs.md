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
| **Issue** | `python Customer_Support_Agent/main.py` crashed on startup with `httpx.ConnectError: [Errno 11001] getaddrinfo failed`, raised from `mem0.client.main.MemoryClient.__init__` → `_validate_api_key()`'s `GET /v1/ping/` call to `api.mem0.ai`. |
| **Found Date** | 2026-07-30 |
| **Status** | Root-caused; not fixed (network-level, outside this repo's control) |
| **Severity** | LOW — intermittent, self-resolves on retry |
| **File** | `Customer_Support_Agent/main.py:23` |
| **Description** | The crash is a DNS resolution failure, not an application bug: `nslookup api.mem0.ai` against the machine's default resolver failed outright once, then succeeded on an immediate retry. General connectivity (`ping 8.8.8.8`, `nslookup google.com`) was unaffected throughout. |
| **Root Cause** | `Get-DnsClientServerAddress` showed the active Wi-Fi adapter configured with `fe80::1` — a link-local IPv6 address on the router itself — as its DNS resolver, and Windows tries IPv6 resolution first. Querying that resolver directly 5 times in a row timed out on attempts 1-2 and succeeded on 3-5: the router's IPv6 DNS forwarding is itself intermittently unreliable, not a symptom of anything in this codebase. The IPv4 resolver on the same router (`192.168.1.1`) is only tried as a fallback after the IPv6 one times out (~2s × 3 retries), which matches the delay observed before the crash. |
| **Solution** | Not applied yet. Two options identified: (1) point the Wi-Fi adapter at a public resolver (8.8.8.8/1.1.1.1) instead of the router — fixes DNS for every app, offered but not actioned; (2) self-host Mem0 via Docker so `MemoryClient()`'s calls resolve to `localhost`/a Docker service name instead of `api.mem0.ai` — fixes this one dependency only, since `CUSTOM_API_BASE` (the LLM endpoint) still resolves through the same flaky router path either way (see Decisions.md ADR-022). Current workaround is simply retrying — `run_log.txt`'s captured session ran successfully once DNS happened to resolve. |
| **Date Resolved** | Open |

---

### BUG-003 · `Customer_Support_Agent/main.py` didn't find the repo-root `.env`

| Field | Detail |
|---|---|
| **Issue** | `main.py` called `load_dotenv()` with no path argument, so it searched from the current working directory upward and never found `.env`, which lives at the repo root (`Memory-Management-Tools/.env`), one directory above `Customer_Support_Agent/`. `MEM0_API_KEY`/`CUSTOM_API_BASE`/`CUSTOM_API_KEY` all read as unset as a result. |
| **Found Date** | 2026-07-30 |
| **Status** | Resolved |
| **Severity** | LOW |
| **File** | `Customer_Support_Agent/main.py:11` |
| **Description** | Confirmed no `.env` exists inside `Customer_Support_Agent/` or is discoverable from it via `load_dotenv()`'s default cwd-based search; the actual file was found at the repo root via a directory listing. |
| **Root Cause** | `Customer_Support_Agent/` is a sibling of the repo-root `.env`, not a parent of it — `python-dotenv`'s default search only looks upward from the invoking script's/cwd's directory, so it never crosses into a directory it isn't nested under. Identical layout to the one `temp_graph/` hit and fixed via ADR-006. |
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
| **File** | `Customer_Support_Agent/main.py:68-70` |
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
| **File** | `Customer_Support_Agent/main.py:85` |
| **Description** | A `StateGraph` whose only node's only outgoing edge points back to itself, with no conditional edge or `END` anywhere, has no defined termination condition. |
| **Root Cause** | Currently masked by how the graph is driven: `run_conversation()` (`main.py:93-97`) iterates `compiled_graph.stream(...)` and `return`s out of the function as soon as the first event containing a message arrives — so the generator is abandoned after one step and the self-loop is never actually followed. Nothing currently calls `.invoke()` or fully consumes the stream. |
| **Solution** | Not yet applied — flagging since any future change that fully drains the stream (or switches to `.invoke()`) would loop indefinitely. The likely intended fix is either an edge to `END` after `chatbot`, or a conditional edge with an explicit stop condition. |
| **Date Resolved** | Open |

---
