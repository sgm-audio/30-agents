"""
ChromaDB-backed memory layer for all agents.
Supports semantic search, persistent storage, and per-agent namespacing.
"""
import asyncio
import uuid
from typing import Any, Optional

import chromadb
import structlog

from core.config import settings
from core.ollama_client import get_ollama

log = structlog.get_logger(__name__)


class MemoryManager:
    """
    Vector memory using ChromaDB.
    Each agent has its own collection; a shared 'global' collection also exists.
    """

    def __init__(self):
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collections: dict[str, chromadb.Collection] = {}
        log.info("memory.init", path=settings.chroma_persist_dir)

    def _get_collection(self, namespace: str = "global") -> chromadb.Collection:
        key = f"agents_{namespace}"
        if key not in self._collections:
            self._collections[key] = self._client.get_or_create_collection(
                name=key,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[key]

    async def store(
        self,
        text: str,
        metadata: Optional[dict] = None,
        doc_id: Optional[str] = None,
        namespace: str = "global",
    ) -> str:
        """Embed and store a text document. Returns the document ID."""
        ollama = get_ollama()
        embedding = await ollama.embed(settings.model_embed, text)

        doc_id = doc_id or str(uuid.uuid4())
        meta = metadata or {}
        meta["namespace"] = namespace

        col = self._get_collection(namespace)
        await asyncio.to_thread(
            col.upsert,
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta],
        )
        log.debug("memory.stored", id=doc_id, namespace=namespace)
        return doc_id

    async def search(
        self,
        query: str,
        n_results: int = 5,
        namespace: str = "global",
        where: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns list of {id, text, metadata, distance}."""
        ollama = get_ollama()
        embedding = await ollama.embed(settings.model_embed, query)

        col = self._get_collection(namespace)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(n_results, col.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = await asyncio.to_thread(col.query, **kwargs)
        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            output.append(
                {
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                }
            )
        return output

    def delete(self, doc_id: str, namespace: str = "global"):
        col = self._get_collection(namespace)
        try:
            col.delete(ids=[doc_id])
        except Exception as e:
            log.error("memory.delete.failed", doc_id=doc_id, error=str(e))

    def count(self, namespace: str = "global") -> int:
        return self._get_collection(namespace).count()

    def list_namespaces(self) -> list[str]:
        return [
            c.name.removeprefix("agents_")
            for c in self._client.list_collections()
        ]


# Singleton
# NOTE: same async single-threaded race as get_graph(); acceptable here
_memory: Optional[MemoryManager] = None


def get_memory() -> MemoryManager:
    global _memory
    if _memory is None:
        _memory = MemoryManager()
    return _memory
