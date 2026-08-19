"""
ThirdChoiceGenerator: when two states conflict, generate a third state.

The EMPTY (0) posture is the creative gateway. Instead of choosing A or
B, we stay in 0 and generate candidate states that transcend the binary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from btcu_harness.core.state import CognitiveState
from btcu_harness.core.trit import YIN, VOID, YANG


@dataclass
class ConflictAnalysis:
    """Result of analyzing two states for conflict."""

    has_conflict: bool = False
    is_extreme_conflict: bool = False
    conflict_dims: List[int] = field(default_factory=list)


@dataclass
class ThirdChoiceCandidate:
    """A generated third-choice candidate state."""

    strategy: str
    state: CognitiveState
    voided_dims: List[int] = field(default_factory=list)
    preserved_dims: List[int] = field(default_factory=list)
    total_score: float = 0.0
    equidistance_score: float = 0.0
    void_ratio: float = 0.0


class ThirdChoiceGenerator:
    """
    Generate third choices that void conflicting dimensions.

    Third choice is not the arithmetic average. Conflicting dimensions
    are set to VOID, while agreeing dimensions are preserved.
    """

    def analyze_conflict(
        self,
        a: CognitiveState,
        b: CognitiveState,
    ) -> ConflictAnalysis:
        """
        Determine whether and where a and b are in direct opposition.

        A conflict dimension is one where one state is YIN (-1) and the
        other is YANG (+1). VOID dimensions are not conflicts.
        """
        conflicts: List[int] = []

        for i in range(len(a)):
            va = a[i].value
            vb = b[i].value
            if (va == YIN and vb == YANG) or (va == YANG and vb == YIN):
                conflicts.append(i)

        return ConflictAnalysis(
            has_conflict=len(conflicts) > 0,
            is_extreme_conflict=len(conflicts) == len(a),
            conflict_dims=conflicts,
        )

    def generate_all(
        self,
        a: CognitiveState,
        b: CognitiveState,
    ) -> List[ThirdChoiceCandidate]:
        """
        Generate all third-choice candidates for a conflict.

        Strategies:
            void         - conflict dims become VOID, others preserved from a
            dominance_a  - keep state a entirely
            dominance_b  - keep state b entirely
        """
        analysis = self.analyze_conflict(a, b)
        conflict_dims = analysis.conflict_dims
        preserved_dims = [i for i in range(len(a)) if i not in conflict_dims]

        candidates: List[ThirdChoiceCandidate] = []

        # void strategy
        void_values = [a[i].value for i in range(len(a))]
        for dim in conflict_dims:
            void_values[dim] = VOID
        void_state = CognitiveState.from_values(void_values)

        candidates.append(
            self._make_candidate(
                strategy='void',
                state=void_state,
                a=a,
                b=b,
                voided_dims=conflict_dims,
                preserved_dims=preserved_dims,
            )
        )

        # dominance_a strategy
        candidates.append(
            self._make_candidate(
                strategy='dominance_a',
                state=a,
                a=a,
                b=b,
                voided_dims=[],
                preserved_dims=[i for i in range(len(a))],
            )
        )

        # dominance_b strategy
        candidates.append(
            self._make_candidate(
                strategy='dominance_b',
                state=b,
                a=a,
                b=b,
                voided_dims=[],
                preserved_dims=[i for i in range(len(a))],
            )
        )

        return candidates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_candidate(
        self,
        *,
        strategy: str,
        state: CognitiveState,
        a: CognitiveState,
        b: CognitiveState,
        voided_dims: List[int],
        preserved_dims: List[int],
    ) -> ThirdChoiceCandidate:
        equidistance = self._equidistance_score(state, a, b)
        void_ratio = len(voided_dims) / len(a) if len(a) else 0.0
        total = 0.5 * equidistance + 0.5 * void_ratio + 0.01

        return ThirdChoiceCandidate(
            strategy=strategy,
            state=state,
            voided_dims=voided_dims,
            preserved_dims=preserved_dims,
            total_score=round(total, 4),
            equidistance_score=round(equidistance, 4),
            void_ratio=round(void_ratio, 4),
        )

    @staticmethod
    def _equidistance_score(
        c: CognitiveState,
        a: CognitiveState,
        b: CognitiveState,
    ) -> float:
        """
        Return a score in [0, 1] measuring how equidistant c is from a and b.

        1.0 = perfectly equidistant, 0.0 = maximally biased toward one side.
        """
        da = c.distance(a)
        db = c.distance(b)

        total = da + db
        if total == 0:
            return 1.0

        diff = abs(da - db)
        return 1.0 - (diff / total)


# ----------------------------------------------------------------------
# Backwards-compatible helper (legacy integer-index interface)
# ----------------------------------------------------------------------

def generate_third_choice(
    conflict_state: int,
    alternative_state: int,
    limit: int = 5,
) -> List[int]:
    """
    Legacy helper returning candidate state indices.

    Kept for backwards compatibility with earlier BTCU experiments.
    """
    a = CognitiveState.from_index(conflict_state)
    b = CognitiveState.from_index(alternative_state)

    generator = ThirdChoiceGenerator()
    candidates = generator.generate_all(a, b)

    result: List[int] = []
    for candidate in candidates:
        index = candidate.state.index
        if index not in result and index != conflict_state:
            result.append(index)
        if len(result) >= limit:
            break

    return result
