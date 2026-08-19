"""
MemoryTrace - state transition paths in the 19683 cognitive space.

A trace is not a static memory entry. It is a path:

    s0 -> s1 -> s2 -> ...

Each transition is a "trigram change" (卦变). The path lets the agent
reconstruct past cognitive states and project future ones.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from btcu_harness.storage.mongo_client import MongoStore


@dataclass
class TraceRecord:
    """One snapshot along a memory trace."""

    state_id: int
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "state_id": self.state_id,
            "timestamp": self.timestamp,
            "note": self.note,
        }


class MemoryTrace:
    """
    A single agent's evolving trace through cognitive space.

    The trace records state transitions over time, enabling:
        - reconstruction of past cognitive posture
        - trend detection
        - projection of likely future states
    """

    COLLECTION = "memory_traces"

    def __init__(self, store: MongoStore, agent_id: str = "agent_001") -> None:
        self.store = store
        self.agent_id = agent_id

    def record(
        self, state_id: int, note: Optional[str] = None
    ) -> dict:
        """Append a state snapshot to this agent's trace."""
        record = TraceRecord(state_id=state_id, note=note)
        doc = {
            "agent_id": self.agent_id,
            "path_id": f"trace-{self.agent_id}",
            **record.to_dict(),
        }
        return self.store.insert(self.COLLECTION, doc)

    def recent(self, limit: int = 10) -> list[dict]:
        """Return recent snapshots for this agent."""
        return self.store.find(
            self.COLLECTION, {"agent_id": self.agent_id}, limit=limit
        )

    def latest_state(self) -> Optional[int]:
        """Return the most recent state id, or None if no trace exists."""
        snapshots = self.recent(limit=1)
        return snapshots[0]["state_id"] if snapshots else None

    def path(self, limit: int = 20) -> list[int]:
        """Return state ids in chronological order as a path."""
        snapshots = self.recent(limit=limit)
        return [s["state_id"] for s in reversed(snapshots)]
