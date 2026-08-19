"""
MongoPersistenceLayer: MongoDB-backed persistence for BTCU cognitive state.

This is the production-grade counterpart to PersistenceLayer (JSON).

Design:
- Full cognitive snapshots are stored in one collection (`agent_snapshots`)
  so an agent can be restored exactly.
- Hot, queryable sub-records (states, trajectory points, patterns, self layer,
  climate) are also written into their own collections for cheap retrieval
  without loading the full snapshot.

Collections (prefixed by the configured database):
    agent_snapshots   - complete cognitive state, versioned
    memory_states     - visited cognitive states
    trajectory_points - chronological cognitive path
    learned_patterns  - input -> state patterns for LLM cost reduction
    self_levels       - NLP self-layer levels
    climate_snapshots - cognitive climate

pymongo is optional. Importing this module does not fail when pymongo is
missing; constructing MongoPersistenceLayer with a real URI will raise a
clear RuntimeError unless pymongo is installed.

This keeps the core package dependency-light while allowing
`pip install .[mongo]` to enable the MongoDB backend.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .persistence import PersistenceLayer, _now_iso


def _get_pymongo():
    """Return the pymongo module or raise a helpful RuntimeError."""
    try:
        import pymongo  # type: ignore
        return pymongo
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "pymongo is required for MongoDB persistence. "
            "Install it with: pip install 'btcu-harness[mongo]'"
        ) from exc


class MongoPersistenceLayer(PersistenceLayer):
    """
    MongoDB-backed persistence for the complete BTCU cognitive state.

    Keeps the same high-level save/load/restore_* API as the JSON
    PersistenceLayer, so it can be used as a drop-in replacement.
    """

    COLLECTION_SNAPSHOTS = "agent_snapshots"
    COLLECTION_MEMORY_STATES = "memory_states"
    COLLECTION_TRAJECTORY = "trajectory_points"
    COLLECTION_PATTERNS = "learned_patterns"
    COLLECTION_SELF_LEVELS = "self_levels"
    COLLECTION_CLIMATE = "climate_snapshots"

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017",
        database_name: str = "btcu_harness",
        agent_id: str = "default-agent",
    ) -> None:
        self.mongo_uri = mongo_uri
        self.database_name = database_name
        self.agent_id = agent_id

        pymongo = _get_pymongo()
        self._client = pymongo.MongoClient(mongo_uri)
        self._db = self._client[database_name]

        # Storage path is unused in MongoDB mode, but PersistenceLayer
        # exposes it for introspection. Keep a stable synthetic path.
        self.storage_path = f"mongodb://{database_name}/{agent_id}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _snapshot_collection(self):
        return self._db[self.COLLECTION_SNAPSHOTS]

    def _memory_states_collection(self):
        return self._db[self.COLLECTION_MEMORY_STATES]

    def _trajectory_collection(self):
        return self._db[self.COLLECTION_TRAJECTORY]

    def _patterns_collection(self):
        return self._db[self.COLLECTION_PATTERNS]

    def _self_levels_collection(self):
        return self._db[self.COLLECTION_SELF_LEVELS]

    def _climate_collection(self):
        return self._db[self.COLLECTION_CLIMATE]

    def _agent_filter(self) -> Dict[str, Any]:
        return {"agent_id": self.agent_id}

    def _write_sub_collections(self, data: Dict[str, Any]) -> None:
        """Write the queryable sub-records from a full snapshot."""
        agent = self.agent_id
        saved_at = data.get("saved_at") or _now_iso()

        eco = data.get("memory_ecology", {})
        for state_index, state_data in (eco.get("states", {}) or {}).items():
            doc = {
                "agent_id": agent,
                "saved_at": saved_at,
                "state_index": state_index,
                "data": state_data,
            }
            self._memory_states_collection().replace_one(
                {"agent_id": agent, "state_index": state_index},
                doc,
                upsert=True,
            )

        traj = data.get("trajectory", {})
        for point in traj.get("points", []) or []:
            point = dict(point) if isinstance(point, dict) else point
            point["agent_id"] = agent
            point["saved_at"] = saved_at
            self._trajectory_collection().insert_one(point)

        patterns = data.get("pattern_learner", {})
        for pattern in patterns.get("patterns", []) or []:
            pattern = dict(pattern) if isinstance(pattern, dict) else pattern
            pattern["agent_id"] = agent
            pattern["saved_at"] = saved_at
            self._patterns_collection().insert_one(pattern)

        self_layer = data.get("self_layer", {})
        if self_layer:
            for level_name, level_data in (self_layer.get("levels", {}) or {}).items():
                doc = {
                    "agent_id": agent,
                    "saved_at": saved_at,
                    "level_name": level_name,
                    "data": level_data,
                }
                self._self_levels_collection().replace_one(
                    {"agent_id": agent, "level_name": level_name},
                    doc,
                    upsert=True,
                )

        climate = data.get("climate")
        if climate:
            doc = {
                "agent_id": agent,
                "saved_at": saved_at,
                "data": climate,
            }
            self._climate_collection().insert_one(doc)

    # ------------------------------------------------------------------
    # Persistence API
    # ------------------------------------------------------------------
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
        """
        Save the complete cognitive state to MongoDB.

        Returns the id of the stored snapshot.
        """
        data = {
            "agent_id": self.agent_id,
            "version": "0.3",
            "saved_at": _now_iso(),
            "dimension_labels": list(dim_labels),
            "growth_stage": growth_stage,
            "memory_ecology": ecology.export_legacy(),
            "trajectory": trajectory.to_dict(),
            "pattern_learner": pattern_learner.to_dict(),
            "self_layer": self_layer.to_dict() if self_layer else None,
            "climate": climate.to_dict() if climate else None,
            "metadata": metadata or {},
        }

        result = self._snapshot_collection().insert_one(data)
        data["_id"] = result.inserted_id
        self._write_sub_collections(data)
        return str(result.inserted_id)

    def load(self) -> Optional[Dict[str, Any]]:
        """Load the most recent complete snapshot for this agent."""
        cursor = (
            self._snapshot_collection()
            .find(self._agent_filter())
            .sort("saved_at", -1)
            .limit(1)
        )
        doc = next(cursor, None)
        if doc is None:
            return None
        # Strip the MongoDB _id so the result behaves like a plain dict.
        doc = dict(doc)
        doc.pop("_id", None)
        return doc

    # ------------------------------------------------------------------
    # Convenience queries over the hot collections
    # ------------------------------------------------------------------
    def query_states(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recently visited cognitive states for this agent."""
        cursor = (
            self._memory_states_collection()
            .find(self._agent_filter())
            .sort("saved_at", -1)
            .limit(limit)
        )
        return list(cursor)

    def query_trajectory(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent trajectory points for this agent."""
        cursor = (
            self._trajectory_collection()
            .find(self._agent_filter())
            .sort("saved_at", -1)
            .limit(limit)
        )
        return list(cursor)

    def query_patterns(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recently learned patterns for this agent."""
        cursor = (
            self._patterns_collection()
            .find(self._agent_filter())
            .sort("saved_at", -1)
            .limit(limit)
        )
        return list(cursor)

    @property
    def exists(self) -> bool:
        return self._snapshot_collection().count_documents(self._agent_filter()) > 0

    def info(self) -> str:
        """Human-readable info about the persisted state."""
        snapshots = self._snapshot_collection().count_documents(self._agent_filter())
        states = self._memory_states_collection().count_documents(self._agent_filter())
        traj = self._trajectory_collection().count_documents(self._agent_filter())
        patterns = self._patterns_collection().count_documents(self._agent_filter())
        levels = self._self_levels_collection().count_documents(self._agent_filter())

        lines = [
            f"MongoPersistenceLayer: {self.storage_path}",
            f"  Database: {self.database_name}",
            f"  Agent: {self.agent_id}",
            f"  Snapshots: {snapshots}",
            f"  States: {states}",
            f"  Trajectory points: {traj}",
            f"  Patterns: {patterns}",
            f"  Self levels: {levels}",
        ]
        return "\n".join(lines)

    def close(self) -> None:
        """Close the MongoDB client connection."""
        self._client.close()
