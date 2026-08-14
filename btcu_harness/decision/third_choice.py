"""
ThirdChoiceGenerator: Generates third choices from binary conflicts.

When the agent detects a binary conflict (should I do A or B?),
the third choice mechanism kicks in:

1. Detect conflict dimensions (where the two options disagree)
2. Enter void state on those dimensions (suspend judgment)
3. Generate a new candidate state that transcends the opposition
4. Validate the candidate in the 19683 space
5. Output the third choice

The third choice is NOT a compromise (average of A and B).
It is a SYNTHESIS - keeping what both agree on, voiding what they
disagree on, and allowing new cognition to emerge from the void.

This is the practical implementation of the void (0) as the
gateway to creativity and transformation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.space import CognitiveSpace
from ..core.state import CognitiveState
from ..core.trit import Trit, VOID


@dataclass
class ConflictAnalysis:
    """Analysis of a binary conflict between two cognitive states."""

    state_a: CognitiveState
    state_b: CognitiveState
    agreeing_dims: List[int] = field(default_factory=list)     # same value
    disagreeing_dims: List[int] = field(default_factory=list)  # different values
    opposite_dims: List[int] = field(default_factory=list)     # exact opposites (-1 vs +1)

    @property
    def has_conflict(self) -> bool:
        return len(self.disagreeing_dims) > 0

    @property
    def is_extreme_conflict(self) -> bool:
        """True if any dimension is directly opposed (-1 vs +1)."""
        return len(self.opposite_dims) > 0

    @property
    def conflict_intensity(self) -> float:
        """How intense the conflict is [0.0, 1.0]."""
        if not self.disagreeing_dims:
            return 0.0
        total = len(state_a_values := self.state_a.values)
        return len(self.disagreeing_dims) / total


@dataclass
class ThirdChoice:
    """The result of third choice generation."""

    state: CognitiveState
    analysis: ConflictAnalysis
    rationale: str = ""
    transcended_dims: List[int] = field(default_factory=list)
    preserved_dims: List[int] = field(default_factory=list)
    voided_dims: List[int] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Third Choice: State #{self.state.index} [{self.state}]",
            f"  Rationale: {self.rationale}",
            f"  Preserved dimensions: {self.preserved_dims}",
            f"  Voided dimensions: {self.voided_dims}",
            f"  Transcended dimensions: {self.transcended_dims}",
        ]
        return "\n".join(lines)


class ThirdChoiceGenerator:
    """
    Generates third choices from binary conflicts.

    The third choice mechanism is BTCU's key differentiator. Instead of
    choosing between A and B, the agent:

    1. Identifies what A and B agree on -> preserve
    2. Identifies where A and B conflict -> void (enter creative potential)
    3. From the void, a new state emerges that transcends both
    """

    def __init__(
        self,
        space: Optional[CognitiveSpace] = None,
    ) -> None:
        self.space = space

    def analyze_conflict(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
    ) -> ConflictAnalysis:
        """Analyze the conflict between two cognitive states."""
        analysis = ConflictAnalysis(state_a=state_a, state_b=state_b)

        for i in range(len(state_a)):
            val_a = state_a[i].value
            val_b = state_b[i].value

            if val_a == val_b:
                analysis.agreeing_dims.append(i)
            else:
                analysis.disagreeing_dims.append(i)
                if val_a + val_b == 0:  # -1 + 1 = 0, exact opposite
                    analysis.opposite_dims.append(i)

        return analysis

    def generate(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
    ) -> ThirdChoice:
        """
        Generate a third choice from a binary conflict.

        The algorithm:
        1. Where A and B agree -> keep the agreed value (preserve)
        2. Where A and B conflict -> set to 0 (void, creative potential)
        3. The resulting state IS the third choice

        This is not averaging - it's selective voiding.
        The voided dimensions become open for new cognition to emerge.
        """
        analysis = self.analyze_conflict(state_a, state_b)

        third_values = [0] * len(state_a)

        # Preserve agreed dimensions
        for i in analysis.agreeing_dims:
            third_values[i] = state_a[i].value

        # Void conflicting dimensions
        for i in analysis.disagreeing_dims:
            third_values[i] = 0  # void

        third_state = CognitiveState.from_values(third_values)

        # Build rationale
        if analysis.is_extreme_conflict:
            rationale = (
                f"Binary conflict detected on {len(analysis.opposite_dims)} dimensions "
                f"(exact opposites). Third choice voids these dimensions, "
                f"preserving {len(analysis.agreeing_dims)} areas of agreement. "
                f"The voided dimensions become creative space for new cognition."
            )
        else:
            rationale = (
                f"Partial conflict on {len(analysis.disagreeing_dims)} dimensions. "
                f"Third choice preserves agreement on {len(analysis.agreeing_dims)} "
                f"dimensions and voids the rest, opening space for synthesis."
            )

        return ThirdChoice(
            state=third_state,
            analysis=analysis,
            rationale=rationale,
            preserved_dims=list(analysis.agreeing_dims),
            voided_dims=list(analysis.disagreeing_dims),
            transcended_dims=list(analysis.opposite_dims),
        )

    def generate_with_exploration(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        max_neighbors: int = 5,
    ) -> List[ThirdChoice]:
        """
        Generate multiple third choices by exploring around the base third choice.

        The base third choice voids all conflicting dimensions. This method
        also generates variations where some voided dimensions are tentatively
        set to +1 or -1, creating a small family of candidate third choices.

        This gives the agent multiple synthesis options to evaluate.
        """
        base = self.generate(state_a, state_b)
        results = [base]

        # Explore neighbors of the base third choice
        if self.space:
            neighbors = base.state.neighbors()
            seen_indices = {base.state.index}

            for neighbor in neighbors[:max_neighbors]:
                if neighbor.index in seen_indices:
                    continue
                seen_indices.add(neighbor.index)

                # Check if this neighbor is still "between" A and B
                dist_a = neighbor.distance(state_a)
                dist_b = neighbor.distance(state_b)

                # Good third choices are roughly equidistant from A and B
                if abs(dist_a - dist_b) <= 2:
                    tc = ThirdChoice(
                        state=neighbor,
                        analysis=base.analysis,
                        rationale=f"Exploration variant: distance to A={dist_a}, B={dist_b}",
                        preserved_dims=base.preserved_dims,
                        voided_dims=base.voided_dims,
                        transcended_dims=base.transcended_dims,
                    )
                    results.append(tc)

        return results

    def __repr__(self) -> str:
        return f"ThirdChoiceGenerator(space={'set' if self.space else 'none'})"
