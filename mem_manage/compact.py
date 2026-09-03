"""Public entry point: compact a markdown file of raw episodic memory event
records into a pruned, deduped set of durable memories.

Pipeline: parse -> score -> dedupe/merge (LLM-assisted) -> passive decay ->
rerank + prune bottom N%. Dedup/merge runs before decay so a reinforced
memory's last_accessed_at reflects its most recent contributing entry;
pruning runs last, over the already-consolidated memories rather than raw
near-duplicate fragments. See docs/Architecture.md for the full rationale.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from .consolidate import refresh_decay, rerank_and_prune
from .importance import parse_episodic_md
from .memory import DurableMemory, build_durable_memories
from .services.dedup_merge import LLMCall, dedupe_and_merge


def compact_markdown(
    text: str,
    *,
    now: datetime | None = None,
    embedder=None,
    llm_call: LLMCall | None = None,
    judge_call: LLMCall | None = None,
    use_llm: bool = True,
) -> list[DurableMemory]:
    records = parse_episodic_md(text)
    memories = build_durable_memories(records, now=now)
    memories = dedupe_and_merge(
        memories,
        embedder=embedder,
        llm_call=llm_call,
        judge_call=judge_call,
        use_llm=use_llm,
    )
    memories = refresh_decay(memories, now=now)
    memories = rerank_and_prune(memories)
    return memories


def compact_markdown_file(path: str | Path, **kwargs) -> list[DurableMemory]:
    text = Path(path).read_text(encoding="utf-8")
    return compact_markdown(text, **kwargs)


def _main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m mem_manage.compact <episodic-log.md>", file=sys.stderr)
        return 2
    text = Path(argv[1]).read_text(encoding="utf-8")
    record_count = len(parse_episodic_md(text))
    memories = compact_markdown(text)
    print(f"{record_count} episodic record(s) -> {len(memories)} durable memory(ies)")
    for memory in memories:
        merged_note = (
            f" (merged from {len(memory.merged_from)})" if len(memory.merged_from) > 1 else ""
        )
        print(f"  [{memory.importance:.3f}] {memory.tag}{merged_note}: {memory.content[:80]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
