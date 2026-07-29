import logging

import chromadb

from embedding_manager import EmbeddingManager

logger = logging.getLogger(__name__)

# Mirrors ../../RAG-work/app_workflow/services/learned_qa_store.py's canonical
# metadata shape. No distance-migration logic here — these are fresh
# collections created for this experiment, not a pre-existing L2 index.
_COSINE = {"hnsw:space": "cosine"}


class MemoryCollection:
    """A single ChromaDB collection, embedded and queried via EmbeddingManager."""

    def __init__(
        self,
        client: chromadb.ClientAPI,
        name: str,
        description: str,
        embedding_manager: EmbeddingManager,
    ):
        self.name = name
        self.embedding_manager = embedding_manager
        self.collection = client.get_or_create_collection(
            name=name,
            metadata={"description": description, **_COSINE},
        )
        logger.info(
            "[MemoryCollection] '%s' ready — %d entr%s.",
            name, self.collection.count(), "y" if self.collection.count() == 1 else "ies",
        )

    def add(self, uid: str, text: str, metadata: dict) -> bool:
        """Store one memory. Returns False if uid already exists (idempotent)."""
        existing = self.collection.get(ids=[uid])["ids"]
        if existing:
            logger.debug("[MemoryCollection:%s] '%s' already stored — skipping.", self.name, uid)
            return False
        embedding = self.embedding_manager.generate_embedding([text])[0]
        self.collection.add(
            ids=[uid],
            embeddings=[embedding.tolist()],
            documents=[text],
            metadatas=[metadata],
        )
        logger.info("[MemoryCollection:%s] stored '%s'.", self.name, uid)
        return True

    def search(self, query: str, k: int = 4) -> list[dict]:
        """Return up to k semantically similar memories, most similar first."""
        count = self.collection.count()
        if count == 0:
            return []
        embedding = self.embedding_manager.generate_embedding([query])[0]
        results = self.collection.query(
            query_embeddings=[embedding.tolist()],
            n_results=min(k, count),
        )
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]
        return [
            {"content": doc, "metadata": meta, "distance": dist}
            for doc, meta, dist in zip(docs, metas, dists)
        ]
