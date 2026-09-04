# Learnings

Findings reported by agents across project runs.

## 2026-09-01 09:12:03Z — requirements

Clarification needed on the Groq migration in llm_setup.py: is this temporary until rate limits are evaluated, or a permanent replacement for Anthropic? Should the client fall back to Anthropic on Groq API errors, or fail loudly? Does requirements.txt pin the groq SDK to an exact version or track latest?

## 2026-09-01 09:34:51Z — T-011

[auto] `pytest` failed (exit 1): groq.AuthenticationError: Invalid API Key - GROQ_API_KEY not set in test environment, llm_setup.py:23

## 2026-09-01 10:02:17Z — llm-setup

Groq client initialization must happen after config validation, not before; moved the GROQ_API_KEY check into the provider constructor, matching the existing Anthropic/OpenAI validation pattern. Missing key now fails fast at startup instead of surfacing as an opaque 401 on the first completion call.

## 2026-09-01 10:20:40Z — reviewer

llm_setup.py hardcodes the Groq model name (`mixtral-8x7b-32768`) instead of reading it from config. This was flagged as temporary since the commit message says "temporarily on groq" — needs a follow-up to make model selection provider-agnostic before this is load-bearing.

## 2026-09-01 11:05:12Z — architecture

Decision recorded: Groq is a stop-gap for local dev/testing only, chosen for free-tier speed during iteration; Anthropic remains the default for deployed agent runs. llm_setup.py keeps both provider branches rather than removing Anthropic support, so switching back is a one-line config change.

## 2026-09-02 14:10:22Z — requirements

Need clarification on the fuzzy similarity threshold for memory dedup raised during the earlier compaction work: should near-duplicate entries (same fact, reworded) merge automatically, or only flag for manual review? What similarity score counts as "duplicate" vs. merely "related"?

## 2026-09-02 14:38:47Z — T-012

[auto] `pytest tests/test_compact.py` failed (exit 1): AssertionError: expected 2 merged entries but got 0 — cosine_similarity threshold of 0.95 too strict for paraphrased findings

## 2026-09-02 15:01:03Z — reviewer

Lowering the fuzzy-match threshold from 0.95 to 0.85 caused unrelated entries about different files to merge incorrectly. Threshold tuning needs a labeled test set instead of picking single values by trial — flagged for follow-up using real historical entries as ground truth.

## 2026-09-02 15:44:29Z — performance

Computing embeddings for the similarity check on every compaction run recomputed vectors for unchanged entries. Added an embedding cache keyed by content hash so only entries new since the last run get embedded. Reduced a 200-entry compaction from ~40s to ~3s.

## 2026-09-03 09:15:08Z — architecture

Adding structured logging across mem_manage services. Decided on stdlib `logging` with a JSON formatter rather than a new dependency, so log lines stay parseable without adding an entry to requirements.txt.

## 2026-09-03 09:47:33Z — T-013

[auto] `pytest` failed (exit 1): ValueError: Unknown format code 'f' for object of type 'str' — logging call in llm_setup.py mixed %-style formatting inside an f-string

## 2026-09-03 10:12:56Z — reviewer

Log levels were inconsistent — provider validation failures logged at INFO, which hid real errors from log aggregation. Reset convention: DEBUG for internal state, INFO for lifecycle events (provider selected, memory loaded), WARNING for recoverable issues, ERROR only for failures that abort the run.
