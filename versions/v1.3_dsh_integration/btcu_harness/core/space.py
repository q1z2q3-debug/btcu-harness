"""
CognitiveSpace: The 19683-state cognitive space with topology operations.

The space is a discrete, bounded, symmetric structure where:
- Each state has a unique index [0, 19682]
- States have distance, adjacency, and opposition relationships
- The space is centered on the void state (index 9841)
- All topology operations are O(1) or O(dimension) complexity

The space itself carries NO semantics. Dimension labels are attached
per-project and remain fixed for that project's lifetime. The 19683
states are empty rooms waiting to be filled by emergent experience.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from .state import CognitiveState, NUM_DIMENSIONS, SPACE_SIZE
from .trit import Trit


class CognitiveSpace:
    """
    The 19683-state cognitive space.

    This is a structural container - it defines the topology and relationships
    between states but does NOT store any memory or semantics. Those belong
    to the MemoryEcology layer.

    A CognitiveSpace is bound to a set of dimension labels (the "九维" for
    a specific project). Once created, the labels are fixed.

    Attributes:
        dim_labels: The 9 dimension names for this project (e.g.
                    ["past", "present", "future", "inner", "middle",
                     "outer", "cause", "condition", "effect"])
        dim_descriptions: Optional per-dimension descriptions for each trit.
    """

    def __init__(
        self,
        dim_labels: Sequence[str],
        dim_descriptions: Optional[Sequence[Dict[int, str]]] = None,
    ) -> None:
        """
        Create a cognitive space with fixed dimension labels.

        Args:
            dim_labels: Exactly 9 labels for the 9 dimensions.
            dim_descriptions: Optional list of 9 dicts, each mapping
                             {-1: desc, 0: desc, +1: desc} for that dimension.
        """
        if len(dim_labels) != NUM_DIMENSIONS:
            raise ValueError(
                f"Expected {NUM_DIMENSIONS} dimension labels, got {len(dim_labels)}"
            )
        self.dim_labels: Tuple[str, ...] = tuple(dim_labels)
        self.dim_descriptions = dim_descriptions

    # --- State access ---

    @staticmethod
    def state(index: int) -> CognitiveState:
        """Get state by index [0, 19682]."""
        return CognitiveState.from_index(index)

    @staticmethod
    def from_values(values: Sequence[int]) -> CognitiveState:
        """Create state from raw trit values."""
        return CognitiveState.from_values(values)

    @staticmethod
    def all_states() -> Iterator[CognitiveState]:
        """Iterate over all 19683 states in index order."""
        for i in range(SPACE_SIZE):
            yield CognitiveState.from_index(i)

    # --- Topology ---

    @staticmethod
    def distance(a: CognitiveState, b: CognitiveState) -> int:
        """Cognitive distance between two states [0, 18]."""
        return a.distance(b)

    @staticmethod
    def opposite(state: CognitiveState) -> CognitiveState:
        """The mirror state (all dimensions flipped)."""
        return state.opposite()

    @staticmethod
    def neighbors(state: CognitiveState) -> List[CognitiveState]:
        """All states one micro-step away (max 18)."""
        return state.neighbors()

    @staticmethod
    def states_within(
        state: CognitiveState, max_distance: int
    ) -> List[CognitiveState]:
        """
        All states within a given cognitive distance.

        Caution: grows rapidly with distance.
        d=0: 1 state, d=1: ~18, d=2: ~171, d=3: ~966
        """
        result = []
        for s in CognitiveSpace.all_states():
            if s.distance(state) <= max_distance:
                result.append(s)
        return result

    # --- Path finding ---

    @staticmethod
    def path(
        source: CognitiveState, target: CognitiveState
    ) -> List[CognitiveState]:
        """
        Find the shortest cognitive path from source to target.

        Uses greedy BFS. Each step changes one dimension by one trit-step.
        The path length equals the cognitive distance between source and target.

        The path represents a sequence of micro-cognitive shifts.
        Each step is a minimal change in perspective.

        Returns:
            List of states from source (inclusive) to target (inclusive).
        """
        if source == target:
            return [source]

        # Greedy: at each step, change the dimension that reduces distance most
        path = [source]
        current = source

        while current != target:
            diff_dims = current.diff_dimensions(target)

            # For each differing dimension, compute the direction to move
            best_next = None
            best_dist = current.distance(target)

            for dim_idx in diff_dims:
                current_val = current[dim_idx].value
                target_val = target[dim_idx].value

                # Move one step toward target
                if current_val < target_val:
                    step = 1
                else:
                    step = -1

                candidate = current.with_dimension(dim_idx, current_val + step)
                candidate_dist = candidate.distance(target)

                if candidate_dist < best_dist:
                    best_dist = candidate_dist
                    best_next = candidate

            if best_next is None:
                # Should not happen if source != target
                break

            path.append(best_next)
            current = best_next

        return path

    @staticmethod
    def path_through_void(
        source: CognitiveState, target: CognitiveState
    ) -> List[CognitiveState]:
        """
        Find a path from source to target that passes through the void state.

        This represents the philosophical principle that transformation from
        one extreme to another must pass through void (the creative gateway).

        YIN -> VOID -> YANG (not YIN -> YANG directly)

        This is longer but philosophically grounded: all extreme
        transformations require a return to creative potential (void)
        before crystallizing into a new form.
        """
        void_state = CognitiveState.all_void()
        return CognitiveSpace.path(source, void_state)[:-1] + \
               CognitiveSpace.path(void_state, target)

    # --- Space properties ---

    @staticmethod
    def void_state() -> CognitiveState:
        """The center of the space: all dimensions VOID."""
        return CognitiveState.all_void()

    @staticmethod
    def extreme_yin() -> CognitiveState:
        """The extreme negative: all dimensions YIN (index 0)."""
        return CognitiveState.all_yin()

    @staticmethod
    def extreme_yang() -> CognitiveState:
        """The extreme positive: all dimensions YANG (index 19682)."""
        return CognitiveState.all_yang()

    # --- Dimension info ---

    def describe_state(self, state: CognitiveState) -> str:
        """
        Human-readable description of a state using dimension labels.

        The labels are from this space's project configuration.
        The semantics of each trit are from dim_descriptions (if provided).
        """
        lines = []
        lines.append(f"State #{state.index} [{state}]")
        lines.append(
            f"  Polarity: {state.polarity:+d} | "
            f"YIN:{state.yin_count} VOID:{state.void_count} "
            f"YANG:{state.yang_count}"
        )
        for i, (label, dim) in enumerate(zip(self.dim_labels, state.dims)):
            desc = ""
            if self.dim_descriptions and i < len(self.dim_descriptions):
                desc = f" ({self.dim_descriptions[i].get(dim.value, '')})"
            lines.append(f"  Dim{i} {label}: {dim.name}{desc}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"CognitiveSpace(dim_labels={self.dim_labels})"
        )

    def __len__(self) -> int:
        return SPACE_SIZE
