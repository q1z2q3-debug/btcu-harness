"""
TransitionMemory: The accumulated experience of state-to-state transitions.

While StateMemory records what happens AT a state, TransitionMemory records
what happens BETWEEN states - the "corridors" connecting the 19683 rooms.

Over time, frequently-traversed corridors become cognitive pathways -
the agent's habitual thought patterns. Some pathways consistently lead
to good outcomes (cognitive virtues), others to bad ones (cognitive traps).

This is where "cognitive seasons" (认知节气) emerge: repeated transition
patterns that correlate with success or failure become the agent's
internal wisdom about when and how to shift perspective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TransitionRecord:
    """A single transition between two states."""

    timestamp: str
    from_index: int
    to_index: int
    changed_dimensions: List[int] = field(default_factory=list)
    trigger: Optional[str] = None       # What caused the transition
    decision: Optional[str] = None      # What decision was made
    outcome: Optional[str] = None       # What happened after
    outcome_positive: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransitionMemory:
    """
    Accumulated experience of transitions between two specific states.

    Attributes:
        from_index: Source state index.
        to_index: Target state index.
        records: All recorded transitions on this corridor.
        success_count: Transitions with positive outcome.
        failure_count: Transitions with negative outcome.
        changed_dimensions: Which dimensions typically change.
        activation: How "worn" this pathway is [0.0, 1.0].
    """

    from_index: int
    to_index: int
    records: List[TransitionRecord] = field(default_factory=list)
    activation: float = 0.0
    last_traversed: Optional[str] = None

    MAX_RECORDS: int = field(default=500, repr=False)

    @property
    def traverse_count(self) -> int:
        return len(self.records)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.records if r.outcome_positive is True)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.records if r.outcome_positive is False)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def is_pathway(self) -> bool:
        """True if this transition has been traversed enough to be a pathway."""
        return self.traverse_count >= 5

    @property
    def is_virtue(self) -> bool:
        """True if this is a cognitive virtue (frequently successful pathway)."""
        return self.is_pathway and self.success_rate >= 0.7

    @property
    def is_trap(self) -> bool:
        """True if this is a cognitive trap (frequently failing pathway)."""
        return self.is_pathway and self.success_rate <= 0.3

    @property
    def typical_changed_dims(self) -> List[int]:
        """Dimensions most frequently changed in this transition."""
        if not self.records:
            return []
        dim_counts: Dict[int, int] = {}
        for r in self.records:
            for d in r.changed_dimensions:
                dim_counts[d] = dim_counts.get(d, 0) + 1
        # Return dims sorted by frequency (most common first)
        return sorted(dim_counts, key=lambda d: dim_counts[d], reverse=True)

    def record(
        self,
        changed_dimensions: Optional[List[int]] = None,
        trigger: Optional[str] = None,
        decision: Optional[str] = None,
        outcome: Optional[str] = None,
        outcome_positive: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TransitionRecord:
        """Record a transition traversal."""
        now = datetime.now(timezone.utc).isoformat()

        rec = TransitionRecord(
            timestamp=now,
            from_index=self.from_index,
            to_index=self.to_index,
            changed_dimensions=changed_dimensions or [],
            trigger=trigger,
            decision=decision,
            outcome=outcome,
            outcome_positive=outcome_positive,
            metadata=metadata or {},
        )

        self.records.append(rec)
        if len(self.records) > self.MAX_RECORDS:
            self.records = self.records[-self.MAX_RECORDS:]

        self.last_traversed = now
        self.activation = min(1.0, self.activation + 0.2)

        return rec

    def decay(self, factor: float = 0.95) -> None:
        """Apply temporal decay."""
        self.activation *= factor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_index": self.from_index,
            "to_index": self.to_index,
            "records": [
                {
                    "timestamp": r.timestamp,
                    "changed_dimensions": r.changed_dimensions,
                    "trigger": r.trigger,
                    "decision": r.decision,
                    "outcome": r.outcome,
                    "outcome_positive": r.outcome_positive,
                    "metadata": r.metadata,
                }
                for r in self.records
            ],
            "activation": self.activation,
            "last_traversed": self.last_traversed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransitionMemory":
        tm = cls(
            from_index=data["from_index"],
            to_index=data["to_index"],
        )
        tm.records = [
            TransitionRecord(
                timestamp=r["timestamp"],
                from_index=r.get("from_index", data["from_index"]),
                to_index=r.get("to_index", data["to_index"]),
                changed_dimensions=r.get("changed_dimensions", []),
                trigger=r.get("trigger"),
                decision=r.get("decision"),
                outcome=r.get("outcome"),
                outcome_positive=r.get("outcome_positive"),
                metadata=r.get("metadata", {}),
            )
            for r in data.get("records", [])
        ]
        tm.activation = data.get("activation", 0.0)
        tm.last_traversed = data.get("last_traversed")
        return tm

    def __repr__(self) -> str:
        return (
            f"TransitionMemory({self.from_index}->{self.to_index}, "
            f"traverses={self.traverse_count}, "
            f"success={self.success_rate:.1%})"
        )


class TransitionStore:
    """
    Store for all transition memories.

    Indexed by (from_index, to_index) pairs. Only stores corridors
    that have been traversed at least once.
    """

    def __init__(self) -> None:
        self._corridors: Dict[Tuple[int, int], TransitionMemory] = {}

    def _key(self, from_idx: int, to_idx: int) -> Tuple[int, int]:
        return (from_idx, to_idx)

    def get(self, from_idx: int, to_idx: int) -> TransitionMemory:
        """Get or create transition memory for a corridor."""
        key = self._key(from_idx, to_idx)
        if key not in self._corridors:
            self._corridors[key] = TransitionMemory(
                from_index=from_idx, to_index=to_idx
            )
        return self._corridors[key]

    def get_or_none(
        self, from_idx: int, to_idx: int
    ) -> Optional[TransitionMemory]:
        """Get without creating."""
        return self._corridors.get(self._key(from_idx, to_idx))

    def record(
        self,
        from_idx: int,
        to_idx: int,
        changed_dimensions: Optional[List[int]] = None,
        trigger: Optional[str] = None,
        decision: Optional[str] = None,
        outcome: Optional[str] = None,
        outcome_positive: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TransitionRecord:
        """Record a transition."""
        return self.get(from_idx, to_idx).record(
            changed_dimensions=changed_dimensions,
            trigger=trigger,
            decision=decision,
            outcome=outcome,
            outcome_positive=outcome_positive,
            metadata=metadata,
        )

    def pathways_from(self, state_index: int) -> List[TransitionMemory]:
        """All outgoing pathways from a state."""
        return [
            tm for (f, _), tm in self._corridors.items()
            if f == state_index and tm.traverse_count > 0
        ]

    def pathways_to(self, state_index: int) -> List[TransitionMemory]:
        """All incoming pathways to a state."""
        return [
            tm for (_, t), tm in self._corridors.items()
            if t == state_index and tm.traverse_count > 0
        ]

    def virtues(self) -> List[TransitionMemory]:
        """All cognitive virtues (frequently successful pathways)."""
        return [tm for tm in self._corridors.values() if tm.is_virtue]

    def traps(self) -> List[TransitionMemory]:
        """All cognitive traps (frequently failing pathways)."""
        return [tm for tm in self._corridors.values() if tm.is_trap]

    @property
    def total_corridors(self) -> int:
        return len(self._corridors)

    def decay_all(self, factor: float = 0.95) -> None:
        for tm in self._corridors.values():
            tm.decay(factor)

    def to_dict(self) -> Dict[str, Any]:
        return {
            f"{f}_{t}": tm.to_dict()
            for (f, t), tm in self._corridors.items()
            if tm.traverse_count > 0
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransitionStore":
        store = cls()
        for key, tm_data in data.items():
            tm = TransitionMemory.from_dict(tm_data)
            store._corridors[(tm.from_index, tm.to_index)] = tm
        return store

    def __repr__(self) -> str:
        virtues = len(self.virtues())
        traps = len(self.traps())
        return (
            f"TransitionStore(corridors={self.total_corridors}, "
            f"virtues={virtues}, traps={traps})"
        )
