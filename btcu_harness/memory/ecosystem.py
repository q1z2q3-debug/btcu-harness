"""
Memory ecosystem: living memory over the 19683-state space.

This layer turns raw traces and repositories into a cognitive ecology.
Key mechanisms:
    - resonance: current state matches historical traces by proximity
    - suspension: memories can be held in the EMPTY state
    - value-driven reinforcement: +1 strengthen, 0 suspend, -1 suppress
    - attractor detection: frequently visited states become stable centers
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from btcu_harness.core.btcu import T, Z, O
from btcu_harness.core.encoding import encode, decode
from btcu_harness.core.space import Space19683
from btcu_harness.memory.trace import MemoryTrace
from btcu_harness.storage.mongo_client import MongoManager
from btcu_harness.storage.repositories import (
    StateSpaceRepository,
    ExperimentLogRepository,
    LifeCourseRepository,
    CapabilityRepository,
)


@dataclass
class MemoryRecord:
    """An in-ecosystem memory record with value state."""

    state_id: int
    content: Optional[Any] = None
    value: int = Z  # +1 strengthen, 0 suspend, -1 suppress
    activation: float = 1.0

    def is_active(self, threshold: float = 0.2) -> bool:
        return self.value >= Z and self.activation >= threshold

    def is_suspended(self) -> bool:
        return self.value == Z

    def is_suppressed(self) -> bool:
        return self.value == T


class MemoryEcosystem:
    """
    A living memory system on top of the 19683-state space.

    The ecosystem maintains:
        - records indexed by state id
        - one or more traces per agent
        - attractor statistics from the traces
    """

    def __init__(
        self,
        manager: Optional[MongoManager] = None,
        space: Optional[Space19683] = None,
    ) -> None:
        self.space = space or Space19683()
        self.manager = manager or MongoManager()
        self.states = StateSpaceRepository(self.manager)
        self.logs = ExperimentLogRepository(self.manager)
        self.life_course = LifeCourseRepository(self.manager)
        self.capabilities = CapabilityRepository(self.manager)

        self.traces: dict[str, MemoryTrace] = {}
        self.records: dict[int, MemoryRecord] = {}

    # ------------------------------------------------------------------
    # Trace management
    # ------------------------------------------------------------------

    def get_trace(self, agent_id: str = "default") -> MemoryTrace:
        """Return or create the trace for an agent."""
        if agent_id not in self.traces:
            self.traces[agent_id] = MemoryTrace(agent_id=agent_id, space=self.space)
        return self.traces[agent_id]

    def record_state(
        self,
        state: int | Sequence[int],
        *,
        agent_id: str = "default",
        note: Optional[str] = None,
        content: Optional[Any] = None,
        value: int = Z,
    ) -> dict[str, Any]:
        """Record a state into both the trace and the memory record map."""
        state_id = state if isinstance(state, int) else encode(state)
        trace = self.get_trace(agent_id)
        trace.record(state_id, note=note)

        record = self.records.get(state_id)
        if record is None:
            record = MemoryRecord(state_id=state_id, content=content, value=value)
            self.records[state_id] = record
        else:
            if content is not None:
                record.content = content
            if value != Z:
                record.value = value
            record.activation = min(record.activation + 0.1, 1.0)

        # Persist the state vector
        self.states.save_state(
            self.space.decode(state_id),
            label=note,
            metadata={"agent_id": agent_id, "value": value},
        )

        return {
            "state_id": state_id,
            "vector": self.space.decode(state_id),
            "agent_id": agent_id,
            "note": note,
        }

    # ------------------------------------------------------------------
    # Resonance
    # ------------------------------------------------------------------

    def resonate(
        self,
        state: int | Sequence[int],
        *,
        top_k: int = 5,
        max_distance: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Find memory records that resonate with the given state.

        Resonance is measured by Hamming distance in the 19683 space.
        Records within max_distance are returned, nearest first.
        """
        state_id = state if isinstance(state, int) else encode(state)
        results: list[dict[str, Any]] = []

        for record in self.records.values():
            if not record.is_active():
                continue
            distance = self.space.distance(state_id, record.state_id)
            if distance <= max_distance:
                results.append(
                    {
                        "state_id": record.state_id,
                        "distance": distance,
                        "value": record.value,
                        "activation": record.activation,
                        "content": record.content,
                    }
                )

        results.sort(key=lambda x: (x["distance"], -x["activation"]))
        return results[:top_k]

    # ------------------------------------------------------------------
    # Value-driven memory operations
    # ------------------------------------------------------------------

    def strengthen(self, state_id: int) -> None:
        """Reinforce a memory (+1 value, increased activation)."""
        record = self.records.get(state_id)
        if record is None:
            record = MemoryRecord(state_id=state_id)
            self.records[state_id] = record
        record.value = O
        record.activation = min(record.activation + 0.3, 1.0)

    def suspend(self, state_id: int) -> None:
        """Suspend a memory into the EMPTY state (0 value)."""
        record = self.records.get(state_id)
        if record is None:
            record = MemoryRecord(state_id=state_id)
            self.records[state_id] = record
        record.value = Z

    def suppress(self, state_id: int) -> None:
        """
        Suppress a memory (-1 value) without deleting it.

        Suppressed memories remain dormant and may be re-activated.
        """
        record = self.records.get(state_id)
        if record is None:
            record = MemoryRecord(state_id=state_id)
            self.records[state_id] = record
        record.value = T
        record.activation = max(record.activation - 0.5, 0.0)

    # ------------------------------------------------------------------
    # Attractors
    # ------------------------------------------------------------------

    def attractors(self, agent_id: str = "default", top_k: int = 10) -> list[dict[str, Any]]:
        """
        Return the most frequently visited states for an agent.

        Attractors represent stable cognitive centers: the agent's
        default tendencies and identity anchors.
        """
        trace = self.get_trace(agent_id)
        counter = Counter(s.state_id for s in trace.steps)
        total = max(len(trace.steps), 1)

        result = []
        for state_id, count in counter.most_common(top_k):
            result.append(
                {
                    "state_id": state_id,
                    "count": count,
                    "frequency": count / total,
                    "vector": self.space.decode(state_id),
                    "region": self.space.interpret(state_id)["region"],
                }
            )
        return result

    # ------------------------------------------------------------------
    # State space coverage
    # ------------------------------------------------------------------

    def unmapped_regions(self, sample_size: int = 50) -> list[int]:
        """
        Return indices that have never been recorded in the ecosystem.

        These are the unmapped regions: fertile ground for creation and
        unknown-discovery.
        """
        known = set(self.records.keys())
        unknown = [i for i in range(self.space.size) if i not in known]
        return unknown[:sample_size]

    def coverage(self) -> float:
        """Ratio of mapped states to the full 19683-state space."""
        return len(self.records) / self.space.size

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self, agent_id: str = "default") -> dict[str, Any]:
        """Return a compact ecosystem summary."""
        attractors = self.attractors(agent_id, top_k=3)
        return {
            "agent_id": agent_id,
            "total_traces": len(self.traces),
            "total_records": len(self.records),
            "coverage": round(self.coverage(), 6),
            "top_attractors": attractors,
            "states_persisted": self.states.count(),
            "life_events": len(self.life_course.list_events()),
            "capabilities": len(self.capabilities.list_all()),
        }
