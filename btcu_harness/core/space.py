"""
CognitiveSpace and Space19683.

CognitiveSpace operates on CognitiveState objects (object-oriented API).
Space19683 operates on integer indices (legacy index-based API).

Both represent the same 19683-state balanced ternary cognitive space.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Sequence

from btcu_harness.core.state import (
    NUM_DIMENSIONS,
    SPACE_SIZE,
    CognitiveState,
)
from btcu_harness.core import encoding
from btcu_harness.core import ternary


class CognitiveSpace:
    """
    The nine-dimensional balanced ternary cognitive space.

    Every cognitive state is a CognitiveState. The space knows the
    topology (adjacency, distance, shortest path) and the semantic
    dimension labels (flexible per project).
    """

    def __init__(self, dimension_labels: Sequence[str] | None = None) -> None:
        if dimension_labels is None:
            dimension_labels = [f"dim_{i}" for i in range(NUM_DIMENSIONS)]

        self.dimension_labels: List[str] = list(dimension_labels)

        if len(self.dimension_labels) != NUM_DIMENSIONS:
            raise ValueError(
                f"CognitiveSpace requires exactly {NUM_DIMENSIONS} dimension "
                f"labels, got {len(self.dimension_labels)}"
            )

    def __len__(self) -> int:
        return SPACE_SIZE

    def __iter__(self) -> Iterator[CognitiveState]:
        for index in range(SPACE_SIZE):
            yield CognitiveState.from_index(index)

    def __contains__(self, state: object) -> bool:
        if not isinstance(state, CognitiveState):
            return False
        return 0 <= state.index < SPACE_SIZE

    def neighbors(self, state: CognitiveState) -> List[CognitiveState]:
        return state.neighbors()

    def distance(self, a: CognitiveState, b: CognitiveState) -> int:
        return a.distance(b)

    def path(
        self,
        source: CognitiveState,
        target: CognitiveState,
    ) -> List[CognitiveState]:
        path: List[CognitiveState] = [source]
        current = source

        for dim in range(NUM_DIMENSIONS):
            current_value = current[dim].value
            target_value = target[dim].value

            while current_value != target_value:
                current_value += 1 if current_value < target_value else -1
                current = current.with_dimension(dim, current_value)
                path.append(current)

        return path

    def path_through_void(
        self,
        source: CognitiveState,
        target: CognitiveState,
    ) -> List[CognitiveState]:
        void_state = CognitiveState.all_void()
        first_leg = self.path(source, void_state)
        second_leg = self.path(void_state, target)
        return first_leg + second_leg[1:]

    def describe_state(self, state: CognitiveState) -> str:
        lines = [f"State #{state.index}"]

        for label, trit in zip(self.dimension_labels, state.dims):
            lines.append(f"  {label}: {trit.name} ({trit.value})")

        lines.append(f"  polarity: {state.polarity}")
        lines.append(f"  intensity: {state.intensity}")
        lines.append(
            f"  counts: {state.yin_count} YIN, "
            f"{state.void_count} VOID, {state.yang_count} YANG"
        )

        return "\n".join(lines)

    def interpret(self, state: CognitiveState) -> Dict[str, object]:
        return {
            "index": state.index,
            "vector": state.values,
            "polarity": state.polarity,
            "intensity": state.intensity,
            "yin_count": state.yin_count,
            "void_count": state.void_count,
            "yang_count": state.yang_count,
            "is_void_dominant": state.is_void_dominant,
            "description": self.describe_state(state),
        }


class Space19683:
    """
    Index-based API for the 19683-state cognitive space.

    This class exists for backwards compatibility with earlier BTCU
    experiments. It operates on integer indices rather than
    CognitiveState objects.
    """

    size: int = SPACE_SIZE
    center: int = (SPACE_SIZE - 1) // 2
    min_index: int = 0
    max_index: int = SPACE_SIZE - 1
    center_index: int = center

    def __init__(self, dim: int = NUM_DIMENSIONS) -> None:
        # The index-based API only makes sense for nine dimensions.
        if dim != NUM_DIMENSIONS:
            raise ValueError(
                f"Space19683 requires exactly {NUM_DIMENSIONS} dimensions"
            )
        self.dim = dim

    def encode(self, vector: Sequence[int]) -> int:
        return encoding.encode(vector)

    def decode(self, index: int) -> list[int]:
        return encoding.decode(index)

    def mirror(self, index: int) -> int:
        return self.max_index - index

    def negate(self, index: int) -> int:
        return self.mirror(index)

    def polarity(self, index: int) -> int:
        return sum(self.decode(index))

    def empty_count(self, index: int) -> int:
        return sum(1 for v in self.decode(index) if v == 0)

    def neighbors(self, index: int) -> list[int]:
        state = CognitiveState.from_index(index)
        return [s.index for s in state.neighbors()]

    def distance(self, a: int, b: int) -> int:
        sa = CognitiveState.from_index(a)
        sb = CognitiveState.from_index(b)
        return sa.distance(sb)

    def similarity(self, a: int, b: int) -> int:
        return ternary.similarity(self.decode(a), self.decode(b))

    def is_center(self, index: int) -> bool:
        return index == self.center_index

    def is_extreme(self, index: int) -> bool:
        return index == self.min_index or index == self.max_index

    def iter_all(self) -> Iterator[int]:
        for index in range(self.size):
            yield index

    def interpret(self, index: int) -> dict[str, object]:
        vector = self.decode(index)
        p = sum(vector)

        if index == self.min_index:
            region = "all-yin"
        elif index == self.max_index:
            region = "all-yang"
        elif index == self.center_index:
            region = "all-empty"
        elif p < 0:
            region = "yin-leaning"
        elif p > 0:
            region = "yang-leaning"
        else:
            region = "balanced"

        return {
            "index": index,
            "vector": vector,
            "symbol": encoding.to_symbol_string(vector),
            "polarity": p,
            "empty_count": self.empty_count(index),
            "balanced_value": index - self.center_index,
            "region": region,
        }


__all__ = ["CognitiveSpace", "Space19683"]
