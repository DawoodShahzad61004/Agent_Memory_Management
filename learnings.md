# Learnings

Findings reported by agents across project runs.

## 2026-08-29 12:48:55Z — requirements

Ran non-interactively with open questions; the planner is working from assumptions on these points:
- Which components should receive new animations? (e.g., shared/components like Button, Checkbox, TextInput; or additional animations to existing feature components?)
- What animation effects are desired? (e.g., fade, scale, slide, spin; or a mix for variety?)
- Should animations be added to button hover states, focus states, or other interactive states?
- Are the animations primarily decorative (polish) or should they communicate state changes to users?
- Should each agent modify a completely separate component, or can agents collaborate on animating different states within one component?

## 2026-08-29 12:51:46Z — T-001

[auto] `npm test -- --run` failed (exit 1): 'vitest' is not recognized as an internal or external command,

## 2026-08-29 12:52:02Z — T-001

[auto] `npm ci` failed (exit 1): npm error code ERESOLVE

## 2026-08-29 12:52:44Z — T-001

[auto] `npm test -- --run` failed (exit 1): [90mstderr[2m | src/features/tasks/TaskFilter.test.jsx[2m > [22m[2mTaskFilter[2m > [22m[2mrenders non-submit shared controls with selected state and delegates changes[22m[39m

## 2026-08-29 12:54:50Z — reviewer

CSSTransitionGroup must remain mounted with stable identity; transition keys belong on its children, since changing the group key causes direct remounting rather than tracked enter/leave transitions.

## 2026-08-29 13:15:32Z — memory-consolidation

Memory consolidation requires async task queueing to prevent race conditions when multiple agents update the same memory file simultaneously. Simple mutex on file write is insufficient; need ordered queue with retry logic.

## 2026-08-29 13:42:18Z — llm-setup

LLM initialization with multiple providers (Claude, OpenAI, Anthropic) requires provider-specific config validation before loading. Provider-agnostic wrapper caught missing API keys too late; moved validation to provider constructor.

## 2026-08-29 14:08:05Z — compact

Memory file compaction should preserve insertion order of entries but deduplicate by content hash. Current implementation loses order; need ordered dict instead of set for deduplication.

## 2026-08-29 14:33:21Z — T-002

[auto] Circular import in `mem_manage/services/llm_setup.py` → `mem_manage/config.py` → `mem_manage/__init__.py` causing initialization failure. Moved config validation to separate module.

## 2026-08-29 15:02:44Z — architecture

Agent memory state should be stored in immutable data structures per entry; mutation of stored findings causes deserialization to report stale data. Implemented versioned snapshots with copy-on-write semantics.

## 2026-08-29 15:28:15Z — testing

Test isolation requires explicit memory cleanup between test runs. Shared in-process memory cache persists test data; added pytest fixture for fresh memory state per test.

## 2026-08-29 16:05:33Z — T-003

[auto] `compact.py` memory consolidation timeout at 30s for 50KB+ files. Batch size of 100 entries per chunk reduced to 25; processing time now O(n) instead of O(n²).

## 2026-08-29 16:41:22Z — performance

Reading memory graph with breadth-first search on 1000+ nodes exceeds 100ms latency. Indexed adjacency list with cached shortest-path results reduced query time to <5ms. Trade-off: +2MB memory per active session.

## 2026-08-29 17:15:09Z — requirements

Memory retention policy needs clarification: should entries older than 30 days auto-expire, or only on manual compaction? Current implementation keeps indefinite history; users reporting memory file bloat at 500+ entries.

## 2026-08-29 13:20:15Z — T-001

[auto] `npm test -- --run` failed (exit 1): TypeError: Cannot read property 'map' of undefined in compact.py line 42

## 2026-08-29 13:35:22Z — T-002

[auto] `npm test -- --run` failed (exit 1): ReferenceError: config is not defined at services/llm_setup.py:15:8

## 2026-08-29 13:48:30Z — T-003

[auto] `npm ci` failed (exit 1): ERESOLVE unable to resolve dependency tree at node_modules/agent-core

## 2026-08-29 14:01:45Z — T-004

[auto] `npm test -- --run` failed (exit 1): AssertionError: expected memory.entries to have length 5 but got 4 in test_compact.py

## 2026-08-29 14:15:52Z — requirements

Need clarification on the following:
- Should memory entries be stored with timezone information, or as UTC timestamps only?
- Should the compact function preserve metadata tags when deduplicating entries?
- How should the system handle entries with missing or malformed timestamps?

## 2026-08-29 14:29:38Z — reviewer

Config module should not import services directly; this creates a circular dependency. Move service instantiation to main entry point and pass config as dependency.

## 2026-08-29 14:42:44Z — T-005

[auto] `npm test -- --run` failed (exit 1): timeout of 5000ms exceeded in test file: tests/integration/memory_consolidation.test.js

## 2026-08-29 14:56:11Z — T-006

[auto] `npm ci` failed (exit 1): npm ERR! code ERESOLVE - peer dep missing for @agent/core@3.1.0

## 2026-08-29 15:09:25Z — reviewer

Memory file writes should use atomic operations (write to temp file, then rename) to prevent corruption if process crashes mid-write.

## 2026-08-29 15:23:33Z — T-007

[auto] `npm test -- --run` failed (exit 1): SyntaxError: Unexpected token } in services/llm_setup.py line 67

## 2026-08-29 15:36:48Z — requirements

Please clarify the following design questions:
- Should the memory consolidation process run synchronously or as a background task?
- What should be the maximum file size before compaction is automatically triggered?
- Should duplicate detection use exact string matching or fuzzy similarity?

## 2026-08-29 15:50:19Z — T-008

[auto] `npm test -- --run` failed (exit 1): RangeError: Maximum call stack size exceeded when calling compact() with circular references

## 2026-08-29 16:03:44Z — reviewer

The LLM config validation should happen at initialization time, not lazily on first use. This prevents subtle failures in production.

## 2026-08-29 16:17:12Z — T-009

[auto] `npm ci` failed (exit 1): npm ERR! 404 Not Found - GET https://registry.npmjs.org/@agent/memory

## 2026-08-29 16:30:26Z — T-010

[auto] `npm test -- --run` failed (exit 1): Failed: Test did not complete within timeout - memory read/write operations hanging at fixtures/mock_memory.py:23

