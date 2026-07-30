"""ChromaMemoryStore — the only implementation of MemoryStore, and the only
code path in this package that creates a Chroma collection.

Why the single factory: in the parent project a collection was accidentally
created at the L2 default while scores were computed as `1 - distance`, which
is only correct for cosine. That silently corrupted ranking for months. Here
`open_collection()` pins cosine on create and *asserts* cosine on open, so a
mis-spaced collection fails loudly at startup instead of degrading quietly.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import chromadb

from memora_mini.config import CHROMA_PATH
from memora_mini.embeddings import embed_one
from memora_mini.store.namespaces import collection_name
from memora_mini.store.protocol import Item, SearchItem

logger = logging.getLogger(__name__)

_COSINE = {"hnsw:space": "cosine"}
_JSON_PREFIX = "__json__:"
_NONE = "__none__"
TEXT_KEY = "text"  # value[TEXT_KEY] is what gets embedded


def open_collection(client: chromadb.ClientAPI, name: str):
    """The single collection factory. Pins cosine; verifies it on every open."""
    collection = client.get_or_create_collection(name=name, metadata=dict(_COSINE))
    space = (collection.configuration_json or {}).get("hnsw", {}).get("space")
    if space != "cosine":
        raise RuntimeError(
            f"collection '{name}' reports hnsw:space={space!r}, expected 'cosine'. "
            "Scores are computed as 1 - distance, which is only valid for cosine. "
            "Delete the collection and re-ingest rather than querying it."
        )
    return collection


def _encode(value: dict) -> dict[str, Any]:
    """dict -> Chroma metadata (scalars only). Lists/dicts are JSON-encoded."""
    meta: dict[str, Any] = {}
    for key, val in value.items():
        if key == TEXT_KEY:
            continue
        if val is None:
            meta[key] = _NONE
        elif isinstance(val, (list, dict, tuple)):
            meta[key] = _JSON_PREFIX + json.dumps(list(val) if isinstance(val, tuple) else val)
        elif isinstance(val, (str, int, float, bool)):
            meta[key] = val
        else:
            meta[key] = str(val)
    return meta


def _decode(meta: dict[str, Any] | None, document: str | None) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, val in (meta or {}).items():
        if isinstance(val, str) and val == _NONE:
            value[key] = None
        elif isinstance(val, str) and val.startswith(_JSON_PREFIX):
            value[key] = json.loads(val[len(_JSON_PREFIX):])
        else:
            value[key] = val
    if document is not None:
        value[TEXT_KEY] = document
    return value


class ChromaMemoryStore:
    """Local persistent ChromaDB behind the four-verb MemoryStore interface."""

    def __init__(self, path: str | None = None):
        self._client = chromadb.PersistentClient(path=path or CHROMA_PATH)
        self._collections: dict[str, Any] = {}

    def collection(self, namespace: tuple[str, ...]):
        name = collection_name(namespace)
        if name not in self._collections:
            self._collections[name] = open_collection(self._client, name)
        return self._collections[name]

    # --- the four verbs ----------------------------------------------------
    def put(self, namespace: tuple[str, ...], key: str, value: dict) -> None:
        text = value.get(TEXT_KEY)
        if not text:
            raise ValueError(f"value must carry a non-empty '{TEXT_KEY}' field to embed")
        self.collection(namespace).upsert(
            ids=[key],
            embeddings=[embed_one(text)],
            documents=[text],
            metadatas=[_encode(value)],
        )

    def get(self, namespace: tuple[str, ...], key: str) -> Item | None:
        res = self.collection(namespace).get(ids=[key])
        if not res["ids"]:
            return None
        return Item(
            namespace=namespace,
            key=res["ids"][0],
            value=_decode(res["metadatas"][0], (res.get("documents") or [None])[0]),
        )

    def search(
        self,
        namespace: tuple[str, ...],
        *,
        query: str | None = None,
        filter: dict | None = None,
        limit: int = 10,
    ) -> list[SearchItem]:
        collection = self.collection(namespace)
        count = collection.count()
        if count == 0:
            return []
        where = _build_where(filter)
        if query is None:
            res = collection.get(where=where, limit=limit) if where else collection.get(limit=limit)
            return [
                SearchItem(namespace, key, _decode(meta, doc), score=0.0)
                for key, meta, doc in zip(res["ids"], res["metadatas"], res["documents"])
            ]
        res = collection.query(
            query_embeddings=[embed_one(query)],
            n_results=min(limit, count),
            where=where,
        )
        return [
            SearchItem(namespace, key, _decode(meta, doc), score=1.0 - dist)
            for key, meta, doc, dist in zip(
                res["ids"][0], res["metadatas"][0], res["documents"][0], res["distances"][0]
            )
        ]

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        """Operator cleanup only. The normal lifecycle is supersede (see apply.py)."""
        self.collection(namespace).delete(ids=[key])

    # --- metadata-only update: must not re-embed ---------------------------
    def update_metadata(self, namespace: tuple[str, ...], key: str, patch: dict) -> None:
        """Cheap partial update — runs on every recall, so it never re-embeds."""
        current = self.get(namespace, key)
        if current is None:
            return
        merged = {**current.value, **patch}
        self.collection(namespace).update(ids=[key], metadatas=[_encode(merged)])

    def count(self, namespace: tuple[str, ...]) -> int:
        return self.collection(namespace).count()


def _build_where(filter: dict | None) -> dict | None:
    """Chroma needs an explicit $and once there is more than one condition."""
    if not filter:
        return None
    clauses = [{k: v if isinstance(v, dict) else {"$eq": v}} for k, v in filter.items()]
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}
