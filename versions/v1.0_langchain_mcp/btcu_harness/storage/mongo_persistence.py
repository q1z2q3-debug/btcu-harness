"""
MongoDB persistence backend for BTCU Harness.

Stores cognitive state in MongoDB for production use with concurrent access,
multi-agent scenarios, and long-running sessions.

Usage:
    from btcu_harness.storage.mongo_persistence import MongoPersistence

    store = MongoPersistence(uri="mongodb://localhost:27017", db_name="btcu")
    store.save(ecology, trajectory, pattern_learner, self_layer, dim_labels, "school")
    data = store.load()  # returns dict or None
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("btcu_harness.storage.mongo")


class MongoPersistence:
    """
    MongoDB-backed persistence for BTCU cognitive state.

    Each project is stored as a single document in the `cognitive_states`
    collection, keyed by project_id. This enables:
        - Concurrent access (MongoDB handles locking)
        - Multi-agent scenarios (each agent has its own project_id)
        - Historical snapshots (versioned documents)
        - Querying across projects
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        db_name: Optional[str] = None,
        project_id: str = "default",
    ) -> None:
        try:
            from pymongo import MongoClient  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "pymongo not installed. Install with: pip install 'btcu-harness[mongo]'"
            )

        from ..config import settings
        self.uri = uri or settings.mongo_uri
        self.db_name = db_name or settings.mongo_db
        self.project_id = project_id

        self._client = MongoClient(self.uri)
        self._db = self._client[self.db_name]
        self._collection = self._db["cognitive_states"]

        # Ensure index on project_id
        self._collection.create_index("project_id", unique=True)

    def save(
        self,
        ecology: Any,
        trajectory: Any,
        pattern_learner: Any,
        self_layer: Any,
        dim_labels: list,
        growth_stage: str,
        metadata: Optional[Dict[str, Any]] = None,
        climate: Any = None,
    ) -> str:
        """Save the complete cognitive state to MongoDB."""
        doc = {
            "project_id": self.project_id,
            "version": "1.1",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "dimension_labels": dim_labels,
            "growth_stage": growth_stage,
            "memory_ecology": ecology.export_legacy(),
            "trajectory": trajectory.to_dict(),
            "pattern_learner": pattern_learner.to_dict(),
            "self_layer": self_layer.to_dict() if self_layer else None,
            "climate": climate.to_dict() if climate else None,
            "metadata": metadata or {},
        }

        self._collection.replace_one(
            {"project_id": self.project_id},
            doc,
            upsert=True,
        )
        logger.info("Saved cognitive state for project '%s'", self.project_id)
        return self.project_id

    def load(self) -> Optional[Dict[str, Any]]:
        """Load cognitive state from MongoDB. Returns None if not found."""
        doc = self._collection.find_one({"project_id": self.project_id})
        if doc is None:
            return None
        # Remove MongoDB internal fields
        doc.pop("_id", None)
        return doc

    def delete(self) -> bool:
        """Delete the cognitive state for this project."""
        result = self._collection.delete_one({"project_id": self.project_id})
        return result.deleted_count > 0

    def list_projects(self) -> list[Dict[str, Any]]:
        """List all projects with summary info."""
        cursor = self._collection.find(
            {},
            {
                "project_id": 1,
                "saved_at": 1,
                "growth_stage": 1,
                "dimension_labels": 1,
            },
        )
        projects = []
        for doc in cursor:
            doc.pop("_id", None)
            projects.append(doc)
        return projects

    @property
    def exists(self) -> bool:
        return self._collection.find_one({"project_id": self.project_id}) is not None

    def info(self) -> str:
        """Human-readable info about the persisted state."""
        data = self.load()
        if not data:
            return f"MongoPersistence: no state for project '{self.project_id}'"

        eco_stats = data.get("memory_ecology", {}).get("stats", {})
        traj = data.get("trajectory", {})
        patterns = data.get("pattern_learner", {})

        lines = [
            f"MongoPersistence: project='{self.project_id}' ({self.db_name})",
            f"  Version: {data.get('version', 'unknown')}",
            f"  Saved: {data.get('saved_at', 'unknown')}",
            f"  Growth stage: {data.get('growth_stage', 'unknown')}",
            f"  Dimensions: {data.get('dimension_labels', [])}",
            f"  Memory: {eco_stats.get('visited_states', 0)} states, "
            f"{eco_stats.get('total_visits', 0)} visits",
            f"  Trajectory: {len(traj.get('points', []))} points",
            f"  Patterns: {len(patterns.get('patterns', []))} learned",
        ]
        return "\n".join(lines)

    def close(self) -> None:
        """Close the MongoDB connection."""
        self._client.close()
