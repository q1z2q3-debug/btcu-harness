"""
DecisionPathfinder: Generates cognitive state transition paths.

Decision in BTCU is not "selecting an option from a list" - it's
"generating a path from current state to target state."

The pathfinder uses:
1. Topology of the 19683 space (distance, adjacency)
2. Memory ecology (known virtues, traps, resonance)
3. Cognitive principles (void traversal, minimal change)

A path represents a sequence of micro-cognitive shifts. Each step
is a minimal change in one dimension. The agent "walks" through
the cognitive space from where it is to where it wants to be.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.space import CognitiveSpace
from ..core.state import CognitiveState
from ..memory.ecology import MemoryEcology


@dataclass
class DecisionPath:
    """
    A cognitive decision path from source to target.

    Attributes:
        states: Ordered list of states from source to target.
        dimension_changes: Which dimension changed at each step.
        through_void: Whether this path passes through the void state.
        memory_warnings: Cautions from memory (traps on the path).
        memory_guidance: Guidance from memory (virtues on the path).
        estimated_length: Number of steps (distance).
    """

    states: List[CognitiveState] = field(default_factory=list)
    dimension_changes: List[int] = field(default_factory=list)
    through_void: bool = False
    memory_warnings: List[str] = field(default_factory=list)
    memory_guidance: List[str] = field(default_factory=list)
    estimated_length: int = 0

    @property
    def source(self) -> Optional[CognitiveState]:
        return self.states[0] if self.states else None

    @property
    def target(self) -> Optional[CognitiveState]:
        return self.states[-1] if self.states else None

    def summary(self) -> str:
        """Human-readable path summary."""
        lines = [
            f"Decision Path: #{self.source.index} -> #{self.target.index}",
            f"  Length: {self.estimated_length} steps",
            f"  Through void: {self.through_void}",
        ]
        if self.memory_warnings:
            lines.append(f"  Warnings: {len(self.memory_warnings)}")
            for w in self.memory_warnings:
                lines.append(f"    ! {w}")
        if self.memory_guidance:
            lines.append(f"  Guidance: {len(self.memory_guidance)}")
            for g in self.memory_guidance:
                lines.append(f"    > {g}")
        return "\n".join(lines)


class DecisionPathfinder:
    """
    Finds cognitive paths through the 19683 space.

    Uses topology + memory to find paths that:
    - Are short (minimal cognitive distance)
    - Avoid known traps
    - Leverage known virtues
    - Pass through void when transitioning between extremes
    """

    def __init__(
        self,
        space: CognitiveSpace,
        ecology: Optional[MemoryEcology] = None,
    ) -> None:
        self.space = space
        self.ecology = ecology

    def find_path(
        self,
        source: CognitiveState,
        target: CognitiveState,
        prefer_void: bool = False,
    ) -> DecisionPath:
        """
        Find the best cognitive path from source to target.

        Args:
            source: Current cognitive state.
            target: Desired cognitive state.
            prefer_void: If True, route through the void state
                        (for extreme transitions).

        Returns:
            DecisionPath with the route and memory annotations.
        """
        # Generate raw path
        if prefer_void:
            raw_path = self.space.path_through_void(source, target)
        else:
            raw_path = self.space.path(source, target)

        # Identify dimension changes at each step
        dim_changes = []
        for i in range(len(raw_path) - 1):
            diffs = raw_path[i].diff_dimensions(raw_path[i + 1])
            dim_changes.append(diffs[0] if diffs else -1)

        path = DecisionPath(
            states=raw_path,
            dimension_changes=dim_changes,
            through_void=CognitiveState.all_void() in raw_path,
            estimated_length=len(raw_path) - 1,
        )

        # Annotate with memory if ecology is available
        if self.ecology:
            self._annotate_with_memory(path)

        return path

    def _annotate_with_memory(self, path: DecisionPath) -> None:
        """Add memory-based warnings and guidance to the path."""
        for i, state in enumerate(path.states):
            idx = state.index

            # Check if this state has memory
            mem = self.ecology.state_store.get_or_none(idx)
            if mem is None or mem.is_empty:
                continue

            # Warnings for traps
            if mem.failure_count > mem.success_count and mem.failure_count >= 2:
                path.memory_warnings.append(
                    f"Step {i}: State #{idx} has poor track record "
                    f"({mem.failure_count} failures)"
                )

            # Guidance for virtues
            if mem.success_count > 0 and mem.failure_count == 0:
                path.memory_guidance.append(
                    f"Step {i}: State #{idx} has perfect record "
                    f"({mem.success_count} successes)"
                )

            # Check outgoing transitions for virtues/traps
            outgoing = self.ecology.transition_store.pathways_from(idx)
            for tm in outgoing:
                if i < len(path.states) - 1 and tm.to_index == path.states[i + 1].index:
                    if tm.is_trap:
                        path.memory_warnings.append(
                            f"Step {i}->{i+1}: This transition is a known trap "
                            f"(success rate: {tm.success_rate:.0%})"
                        )
                    elif tm.is_virtue:
                        path.memory_guidance.append(
                            f"Step {i}->{i+1}: This transition is a known virtue "
                            f"(success rate: {tm.success_rate:.0%})"
                        )

    def find_third_choice(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
    ) -> CognitiveState:
        """
        Find a third cognitive state that transcends a binary conflict.

        When the agent is torn between two states (A vs B), this method
        finds a third state C that:
        - Is equidistant from both A and B
        - Tends toward void (creative potential)
        - Represents a synthesis rather than a compromise

        This is the "third choice" mechanism - not A, not B, but C.
        """
        # Find dimensions where A and B agree vs disagree
        agree_dims = []  # A and B have same value
        disagree_dims = []  # A and B differ

        for i in range(len(state_a)):
            if state_a[i] == state_b[i]:
                agree_dims.append((i, state_a[i].value))
            else:
                disagree_dims.append((i, state_a[i].value, state_b[i].value))

        # Third choice:
        # - On agreeing dimensions: keep the agreement
        # - On disagreeing dimensions: move toward void (0)
        third_values = [0] * len(state_a)

        for i, val in agree_dims:
            third_values[i] = val

        for i, val_a, val_b in disagree_dims:
            # Move toward void: take the value closest to 0
            if abs(val_a) <= abs(val_b):
                third_values[i] = 0  # void on conflicting dims
            else:
                third_values[i] = 0

        return CognitiveState.from_values(third_values)

    def find_void_path(self, source: CognitiveState) -> DecisionPath:
        """
        Find path from current state to the void state.

        This represents "returning to creative potential" - letting go
        of current cognitive stance to allow new perspectives to emerge.
        """
        void = CognitiveState.all_void()
        return self.find_path(source, void, prefer_void=False)

    def __repr__(self) -> str:
        return f"DecisionPathfinder(space={self.space})"
