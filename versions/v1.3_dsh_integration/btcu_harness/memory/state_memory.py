"""
StateMemory: The accumulated experience of a single cognitive state.

Each of the 19683 states has a "room" that starts empty. As the agent
visits states during cognitive practice, each room accumulates:

- Visit count (how many times this state was reached)
- Contexts (what situations led to this state)
- Decisions made from this state and their outcomes
- Insights distilled from accumulated experience
- Resonance links to other states (emergent, not predefined)

Memory is ecological, not static:
- Reinforcement: successful decisions strengthen the memory
- Suppression (not deletion): failed decisions are suppressed, not removed
- Decay: long-unvisited rooms fade, but can be reactivated
- Resonance: visiting one state can activate related states

The "book of changes" analogy: each state's accumulated experience
is like the accumulated commentary on a hexagram - it grows richer
with each generation of use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class VisitRecord:
    """A single visit to a cognitive state."""

    timestamp: str
    context: Dict[str, Any] = field(default_factory=dict)
    decision: Optional[str] = None
    outcome: Optional[str] = None
    outcome_positive: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateMemory:
    """
    The accumulated experience of one cognitive state (one "room").

    Attributes:
        state_index: The 0-19682 index of this state.
        visits: List of all visit records.
        visit_count: Total number of visits.
        success_count: Number of visits with positive outcome.
        failure_count: Number of visits with negative outcome.
        insights: Distilled wisdom from accumulated experience.
        resonance_links: Emergent connections to other states.
                         {other_index: resonance_strength}
        activation: Current activation level [0.0, 1.0].
                   Decays over time, reinforced by visits.
        last_visited: Timestamp of most recent visit.
        first_visited: Timestamp of first visit.
        suppressed_decisions: Decisions that led to bad outcomes,
                             suppressed but not deleted.
    """

    state_index: int
    visits: List[VisitRecord] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    resonance_links: Dict[int, float] = field(default_factory=dict)
    activation: float = 0.0
    last_visited: Optional[str] = None
    first_visited: Optional[str] = None
    suppressed_decisions: List[str] = field(default_factory=list)

    # Limits to prevent unbounded growth
    MAX_VISITS_KEPT: int = field(default=1000, repr=False)

    @property
    def visit_count(self) -> int:
        return len(self.visits)

    @property
    def success_count(self) -> int:
        return sum(1 for v in self.visits if v.outcome_positive is True)

    @property
    def failure_count(self) -> int:
        return sum(1 for v in self.visits if v.outcome_positive is False)

    @property
    def success_rate(self) -> float:
        """Success rate [0.0, 1.0]. Returns 0.0 if no outcomes recorded."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def is_empty(self) -> bool:
        """True if this state has never been visited."""
        return self.visit_count == 0

    @property
    def is_virgin(self) -> bool:
        """True if visited but no outcome recorded yet."""
        return (
            self.visit_count > 0
            and self.success_count == 0
            and self.failure_count == 0
        )

    def visit(
        self,
        context: Optional[Dict[str, Any]] = None,
        decision: Optional[str] = None,
        outcome: Optional[str] = None,
        outcome_positive: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VisitRecord:
        """
        Record a visit to this state.

        Updates activation, timestamps, and optionally suppresses
        failed decisions.
        """
        now = datetime.now(timezone.utc).isoformat()

        record = VisitRecord(
            timestamp=now,
            context=context or {},
            decision=decision,
            outcome=outcome,
            outcome_positive=outcome_positive,
            metadata=metadata or {},
        )

        self.visits.append(record)

        # Trim if exceeding limit (keep most recent)
        if len(self.visits) > self.MAX_VISITS_KEPT:
            self.visits = self.visits[-self.MAX_VISITS_KEPT:]

        # Update timestamps
        if self.first_visited is None:
            self.first_visited = now
        self.last_visited = now

        # Reinforce activation
        self._reinforce()

        # Suppress failed decisions
        if outcome_positive is False and decision:
            if decision not in self.suppressed_decisions:
                self.suppressed_decisions.append(decision)

        return record

    def add_insight(self, insight: str) -> None:
        """Add a distilled insight to this state's accumulated wisdom."""
        if insight not in self.insights:
            self.insights.append(insight)

    def add_resonance(self, other_index: int, strength: float = 0.5) -> None:
        """
        Add or strengthen a resonance link to another state.

        Resonance is emergent - it's discovered through practice, not
        predefined. When two states frequently co-occur or transition
        between each other, their resonance strengthens.

        Args:
            other_index: The state index this one resonates with.
            strength: Resonance strength [0.0, 1.0]. Adds to existing.
        """
        if other_index == self.state_index:
            return  # No self-resonance
        self.resonance_links[other_index] = min(
            1.0, self.resonance_links.get(other_index, 0.0) + strength
        )

    def decay(self, factor: float = 0.95) -> None:
        """
        Apply temporal decay to this state's activation.

        Decay is suppression, not deletion. The memory persists but
        becomes less accessible. A new visit can reactivate it fully.

        Args:
            factor: Decay factor per time step [0.0, 1.0].
                   0.95 = 5% decay, 1.0 = no decay.
        """
        self.activation *= factor
        # Decay resonance links too, but slower
        decayed_links = {}
        for idx, strength in self.resonance_links.items():
            new_strength = strength * (factor ** 0.5)  # slower decay
            if new_strength > 0.01:  # don't let it fully vanish
                decayed_links[idx] = new_strength
        self.resonance_links = decayed_links

    def _reinforce(self, amount: float = 0.3) -> None:
        """Reinforce activation on visit."""
        self.activation = min(1.0, self.activation + amount)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "state_index": self.state_index,
            "visits": [
                {
                    "timestamp": v.timestamp,
                    "context": v.context,
                    "decision": v.decision,
                    "outcome": v.outcome,
                    "outcome_positive": v.outcome_positive,
                    "metadata": v.metadata,
                }
                for v in self.visits
            ],
            "insights": self.insights,
            "resonance_links": self.resonance_links,
            "activation": self.activation,
            "last_visited": self.last_visited,
            "first_visited": self.first_visited,
            "suppressed_decisions": self.suppressed_decisions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateMemory":
        """Deserialize from dictionary."""
        mem = cls(state_index=data["state_index"])
        mem.visits = [
            VisitRecord(
                timestamp=v["timestamp"],
                context=v.get("context", {}),
                decision=v.get("decision"),
                outcome=v.get("outcome"),
                outcome_positive=v.get("outcome_positive"),
                metadata=v.get("metadata", {}),
            )
            for v in data.get("visits", [])
        ]
        mem.insights = data.get("insights", [])
        mem.resonance_links = {
            int(k): v for k, v in data.get("resonance_links", {}).items()
        }
        mem.activation = data.get("activation", 0.0)
        mem.last_visited = data.get("last_visited")
        mem.first_visited = data.get("first_visited")
        mem.suppressed_decisions = data.get("suppressed_decisions", [])
        return mem

    def __repr__(self) -> str:
        return (
            f"StateMemory(#{self.state_index}, "
            f"visits={self.visit_count}, "
            f"activation={self.activation:.2f}, "
            f"insights={len(self.insights)})"
        )


class StateMemoryStore:
    """
    In-memory store for all 19683 state memories.

    Initially all rooms are empty. States are accessed by index.
    Supports persistence to/from disk or database.

    This is the "19683 rooms" - the cognitive memory substrate.
    """

    def __init__(self) -> None:
        # Lazy initialization: only create rooms that are visited
        self._rooms: Dict[int, StateMemory] = {}

    def get(self, state_index: int) -> StateMemory:
        """Get or create the memory for a state."""
        if state_index not in self._rooms:
            self._rooms[state_index] = StateMemory(state_index=state_index)
        return self._rooms[state_index]

    def get_or_none(self, state_index: int) -> Optional[StateMemory]:
        """Get memory without creating if it doesn't exist."""
        return self._rooms.get(state_index)

    def visit(
        self,
        state_index: int,
        context: Optional[Dict[str, Any]] = None,
        decision: Optional[str] = None,
        outcome: Optional[str] = None,
        outcome_positive: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VisitRecord:
        """Convenience: visit a state directly."""
        return self.get(state_index).visit(
            context=context,
            decision=decision,
            outcome=outcome,
            outcome_positive=outcome_positive,
            metadata=metadata,
        )

    @property
    def visited_count(self) -> int:
        """Number of states that have been visited at least once."""
        return sum(1 for m in self._rooms.values() if m.visit_count > 0)

    @property
    def total_visits(self) -> int:
        """Total number of visits across all states."""
        return sum(m.visit_count for m in self._rooms.values())

    @property
    def coverage(self) -> float:
        """Fraction of the 19683 space that has been explored."""
        return self.visited_count / 19683

    def most_visited(self, n: int = 10) -> List[StateMemory]:
        """Top-N most visited states."""
        return sorted(
            self._rooms.values(),
            key=lambda m: m.visit_count,
            reverse=True,
        )[:n]

    def most_activated(self, n: int = 10) -> List[StateMemory]:
        """Top-N most activated states."""
        return sorted(
            self._rooms.values(),
            key=lambda m: m.activation,
            reverse=True,
        )[:n]

    def highest_success(self, n: int = 10, min_visits: int = 3) -> List[StateMemory]:
        """Top-N states by success rate (with minimum visit threshold)."""
        candidates = [
            m for m in self._rooms.values()
            if m.visit_count >= min_visits
            and (m.success_count + m.failure_count) > 0
        ]
        return sorted(candidates, key=lambda m: m.success_rate, reverse=True)[:n]

    def decay_all(self, factor: float = 0.95) -> None:
        """Apply temporal decay to all memories."""
        for mem in self._rooms.values():
            mem.decay(factor)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all non-empty rooms."""
        return {
            str(idx): mem.to_dict()
            for idx, mem in self._rooms.items()
            if mem.visit_count > 0
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateMemoryStore":
        """Deserialize from dictionary."""
        store = cls()
        for idx_str, mem_data in data.items():
            mem = StateMemory.from_dict(mem_data)
            store._rooms[int(idx_str)] = mem
        return store

    def __repr__(self) -> str:
        return (
            f"StateMemoryStore(visited={self.visited_count}/19683, "
            f"total_visits={self.total_visits}, "
            f"coverage={self.coverage:.4%})"
        )
