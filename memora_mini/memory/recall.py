"""Strength-based recall: a client-side re-rank over store.search().

    score = similarity * (1 + w_hits * log1p(hit_count)) * recency_decay(last_hit_at)

Every returned item gets its hit_count bumped and last_hit_at refreshed. That
bump is what lets unused memories fade: a memory nothing recalls decays toward
its raw similarity while frequently-used ones float up.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from memora_mini.config import (
    OVERFETCH_FACTOR,
    RECENCY_FLOOR,
    RECENCY_HALF_LIFE_DAYS,
    SIMILARITY_FLOOR,
    STRENGTH_HIT_WEIGHT,
)
from memora_mini.memory.schemas import utcnow
from memora_mini.store.protocol import SearchItem


def recency_decay(last_hit_at: str, now: datetime | None = None) -> float:
    if not last_hit_at:
        return RECENCY_FLOOR
    try:
        seen = datetime.fromisoformat(last_hit_at)
    except ValueError:
        return RECENCY_FLOOR
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - seen).total_seconds() / 86400.0)
    decay = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
    return max(RECENCY_FLOOR, decay)


def strength(item: SearchItem, now: datetime | None = None) -> float:
    hits = int(item.value.get("hit_count", 0) or 0)
    boost = 1.0 + STRENGTH_HIT_WEIGHT * math.log1p(hits)
    return item.score * boost * recency_decay(str(item.value.get("last_hit_at", "")), now)


def recall(
    store,
    namespace: tuple[str, ...],
    query: str | None,
    *,
    limit: int = 4,
    filter: dict | None = None,
    active_only: bool = True,
    bump: bool = True,
) -> list[SearchItem]:
    """Over-fetch, re-rank by strength, truncate, then bump what we returned."""
    where = dict(filter or {})
    if active_only:
        where["active"] = True
    hits = store.search(namespace, query=query, filter=where or None, limit=limit * OVERFETCH_FACTOR)
    if query is not None:
        hits = [h for h in hits if h.score >= SIMILARITY_FLOOR]
    now = datetime.now(timezone.utc)
    ranked = sorted(hits, key=lambda h: strength(h, now), reverse=True)[:limit]
    if bump:
        stamp = utcnow()
        for hit in ranked:
            store.update_metadata(
                namespace,
                hit.key,
                {"hit_count": int(hit.value.get("hit_count", 0) or 0) + 1, "last_hit_at": stamp},
            )
    return ranked
