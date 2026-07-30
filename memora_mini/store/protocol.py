"""The store interface.

Signatures are deliberately byte-compatible with LangGraph's BaseStore: if a
tool-calling-capable model becomes available later, a thin BaseStore subclass
over the same Chroma collections lets LangMem's managers drop in without
touching a single caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Item:
    """One stored memory. `value` is the decoded dict, list fields restored."""

    namespace: tuple[str, ...]
    key: str
    value: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchItem(Item):
    """An Item plus its retrieval score (cosine similarity, 0..1, higher=better)."""

    score: float = 0.0


@runtime_checkable
class MemoryStore(Protocol):
    def put(self, namespace: tuple[str, ...], key: str, value: dict) -> None: ...

    def get(self, namespace: tuple[str, ...], key: str) -> Item | None: ...

    def search(
        self,
        namespace: tuple[str, ...],
        *,
        query: str | None = None,
        filter: dict | None = None,
        limit: int = 10,
    ) -> list[SearchItem]: ...

    def delete(self, namespace: tuple[str, ...], key: str) -> None: ...
