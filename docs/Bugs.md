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
