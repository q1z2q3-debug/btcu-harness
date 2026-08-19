"""
MongoStore - MongoDB adapter for BTCU Harness.

Primary collections:
    state_space       - cognitive state slots (0..19682)
    memory_traces     - state transition paths
    dimension_sets    - flexible dimension definitions
    decisions         - decision paths and actions
    experiment_logs   - daily project memory / lab notebook
    life_course       - agent growth records
    capabilities      - skill and workflow index

If MongoDB is unavailable, an in-memory fallback keeps the harness
operational. This honors the local-first, zero-hard-dependency ethos.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from btcu_harness.config import StorageConfig


class InMemoryCollection:
    """Minimal in-memory collection with MongoDB-like semantics."""

    def __init__(self) -> None:
        self._docs: list[dict[str, Any]] = []

    def insert_one(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc = dict(doc)
        doc.setdefault("_id", f"mem-{int(time.time() * 1000)}-{len(self._docs)}")
        self._docs.append(doc)
        return doc

    def find_one(self, query: dict[str, Any]) -> Optional[dict[str, Any]]:
        for doc in self._docs:
            if self._matches(doc, query):
                return doc
        return None

    def find(self, query: Optional[dict[str, Any]] = None, limit: int = 0) -> list[dict[str, Any]]:
        query = query or {}
        out: list[dict[str, Any]] = []
        for doc in self._docs:
            if self._matches(doc, query):
                out.append(doc)
                if limit and len(out) >= limit:
                    break
        return out

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self._docs:
            if self._matches(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                return

    def delete_one(self, query: dict[str, Any]) -> None:
        for i, doc in enumerate(self._docs):
            if self._matches(doc, query):
                del self._docs[i]
                return

    def count_documents(self, query: Optional[dict[str, Any]] = None) -> int:
        query = query or {}
        return sum(1 for doc in self._docs if self._matches(doc, query))

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            if doc.get(key) != value:
                return False
        return True


class MongoStore:
    """
    Unified storage facade.

    Attempts to connect to MongoDB. On failure, falls back to an
    in-memory store so cognitive operations remain available.
    """

    def __init__(self, config: Optional[StorageConfig] = None) -> None:
        self.config = config or StorageConfig()
        self._client = None
        self._db = None
        self._collections: dict[str, Any] = {}
        self._in_memory: bool = False
        self._init_store()

    def _init_store(self) -> None:
        """Connect to MongoDB or enable in-memory fallback."""
        try:
            from pymongo import MongoClient

            self._client = MongoClient(
                self.config.mongo_uri, serverSelectionTimeoutMS=1500
            )
            # Force connection check
            self._client.admin.command("ping")
            self._db = self._client[self.config.mongo_db_name]
            self._in_memory = False
            self._ensure_collections()
        except Exception:
            self._client = None
            self._db = None
            self._in_memory = True
            self._collections = {}
            for name in self._collection_names():
                self._collections[name] = InMemoryCollection()

    @staticmethod
    def _collection_names() -> list[str]:
        return [
            "state_space",
            "memory_traces",
            "dimension_sets",
            "decisions",
            "experiment_logs",
            "life_course",
            "capabilities",
        ]

    def _ensure_collections(self) -> None:
        if self._db is None:
            return
        for name in self._collection_names():
            self._collections[name] = self._db[name]

    def _collection(self, name: str):
        if name not in self._collections:
            raise KeyError(f"Unknown collection: {name}")
        return self._collections[name]

    @property
    def is_in_memory(self) -> bool:
        """True when using in-memory fallback."""
        return self._in_memory

    # ------------------------------------------------------------------
    # Generic document API
    # ------------------------------------------------------------------

    def insert(self, collection: str, doc: dict[str, Any]) -> dict[str, Any]:
        return self._collection(collection).insert_one(doc)

    def find_one(self, collection: str, query: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._collection(collection).find_one(query)

    def find(
        self, collection: str, query: Optional[dict[str, Any]] = None, limit: int = 0
    ) -> list[dict[str, Any]]:
        return self._collection(collection).find(query, limit=limit)

    def update(self, collection: str, query: dict[str, Any], set_fields: dict[str, Any]) -> None:
        self._collection(collection).update_one(query, {"$set": set_fields})

    def delete(self, collection: str, query: dict[str, Any]) -> None:
        self._collection(collection).delete_one(query)

    def count(self, collection: str, query: Optional[dict[str, Any]] = None) -> int:
        return self._collection(collection).count_documents(query)
