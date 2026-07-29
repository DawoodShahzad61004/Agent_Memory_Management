### BUG-001 · `README.md` and `LangMem/requirements.txt` saved as UTF-16LE instead of UTF-8

| Field | Detail |
|---|---|
| **Issue** | Both `README.md` (repo root) and `LangMem/requirements.txt` are encoded as UTF-16LE with a BOM and CRLF line endings, instead of plain UTF-8. |
| **Found Date** | 2026-07-29 |
| **Status** | Open |
| **Severity** | LOW |
| **File** | `README.md`, `LangMem/requirements.txt` |
| **Description** | `file README.md LangMem/requirements.txt` reports `Unicode text, UTF-16, little-endian text, with CRLF line terminators` for both. A hex dump confirms a `fffe` BOM followed by every character null-byte-padded (e.g. `23 00 20 00 4d 00 ...` for `"# M..."`). Reading either file with a tool that assumes UTF-8 (or naive byte-oriented `grep`/diff) renders every character as spaced-out garbage, e.g. `a i o h a p p y e y e b a l l s = = 2 . 7 . 1` instead of `aiohappyeyeballs==2.7.1`. Both were produced by shell redirection (`>`) rather than a text-editor Write, which on this environment's PowerShell defaults to UTF-16LE for redirected output rather than UTF-8. |
| **Root Cause** | Files created via PowerShell `>`/`Out-File`-style redirection inherit that shell's non-UTF-8 default text encoding, rather than being written through a UTF-8-explicit path. A rewrite attempt on 2026-07-29 (overwriting `README.md`'s content entirely via the editor's file-write tool) still produced UTF-16LE output (this time without a BOM) even though other brand-new files written the same session (`docs/*.md`) came out as plain UTF-8 — so the encoding appears tied to this specific file/path being an *overwrite* of an already-UTF-16 file, not just to how the content was authored. The exact mechanism (tool-level encoding-preservation-on-overwrite vs. some filesystem/editor-state artifact) is unconfirmed. |
| **Solution** | Re-save both files as UTF-8 without BOM by deleting and recreating them (rather than overwriting in place), or by writing through a path confirmed to force UTF-8 regardless of the target's existing encoding, then re-verifying with `file <path>`. Not yet attempted for `LangMem/requirements.txt`; attempted once for `README.md` on 2026-07-29 without success (see Root Cause). `uv`/`pip` and most modern `git` tooling tolerate a UTF-16 BOM in practice, so this has not yet blocked any workflow, but it should not be relied upon. |
| **Date Resolved** | — |

---
