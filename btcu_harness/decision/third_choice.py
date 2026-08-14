"""
Enhanced ThirdChoiceGenerator: Multi-strategy synthesis from binary conflicts.

v0.3 upgrades:
- Multiple synthesis strategies (void, fusion, dominance, emergent)
- Candidate scoring and ranking
- Memory-aware generation (uses ecology to evaluate candidates)
- Self-aware generation (uses NLP self layer for alignment)
- Multi-candidate output with ranked alternatives

The third choice is still NOT a compromise. It's a creative synthesis
that transcends the binary opposition. The enhanced version generates
multiple synthesis candidates using different strategies, then scores
them based on:
- Equidistance from A and B (fairness)
- Memory success rate (experience)
- Self alignment (personality fit)
- Void ratio (creative potential)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..core.space import CognitiveSpace
from ..core.state import CognitiveState
from ..core.trit import Trit, VOID
from ..memory.ecology import MemoryEcology


@dataclass
class ConflictAnalysis:
    """Analysis of a binary conflict between two cognitive states."""

    state_a: CognitiveState
    state_b: CognitiveState
    agreeing_dims: List[int] = field(default_factory=list)
    disagreeing_dims: List[int] = field(default_factory=list)
    opposite_dims: List[int] = field(default_factory=list)  # exact opposites
    adjacent_dims: List[int] = field(default_factory=list)  # -1 vs 0 or 0 vs +1

    @property
    def has_conflict(self) -> bool:
        return len(self.disagreeing_dims) > 0

    @property
    def is_extreme_conflict(self) -> bool:
        return len(self.opposite_dims) > 0

    @property
    def conflict_intensity(self) -> float:
        if not self.disagreeing_dims:
            return 0.0
        total = len(self.state_a)
        return len(self.disagreeing_dims) / total

    @property
    def opposition_ratio(self) -> float:
        """Ratio of exact opposites among all conflicts."""
        if not self.disagreeing_dims:
            return 0.0
        return len(self.opposite_dims) / len(self.disagreeing_dims)


@dataclass
class ThirdChoiceCandidate:
    """A single third choice candidate with scoring metadata."""

    state: CognitiveState
    strategy: str  # "void", "fusion", "dominance_a", "dominance_b", "emergent"
    rationale: str = ""
    preserved_dims: List[int] = field(default_factory=list)
    voided_dims: List[int] = field(default_factory=list)
    transcended_dims: List[int] = field(default_factory=list)

    # Scoring
    equidistance_score: float = 0.0  # how equidistant from A and B
    memory_score: float = 0.0  # success rate from memory
    self_alignment_score: float = 0.0  # alignment with self attractor
    void_ratio: float = 0.0  # fraction of void dimensions
    total_score: float = 0.0  # weighted combination

    def summary(self) -> str:
        lines = [
            f"Third Choice [{self.strategy}] State #{self.state.index} [{self.state}]",
            f"  Scores: eq={self.equidistance_score:.2f} mem={self.memory_score:.2f} "
            f"self={self.self_alignment_score:.2f} void={self.void_ratio:.2f} "
            f"total={self.total_score:.2f}",
            f"  Preserved: {self.preserved_dims} | Voided: {self.voided_dims} | "
            f"Transcended: {self.transcended_dims}",
            f"  {self.rationale}",
        ]
        return "\n".join(lines)


class ThirdChoiceGenerator:
    """
    Enhanced third choice generator with multiple strategies.

    Strategies:
    1. void: Void all conflicting dimensions (original approach)
    2. fusion: For adjacent conflicts (0 vs +1), take the non-zero value
    3. dominance_a: Lean toward A's values on half the conflicts
    4. dominance_b: Lean toward B's values on half the conflicts
    5. emergent: Find unvisited states near the void center
    """

    def __init__(
        self,
        space: Optional[CognitiveSpace] = None,
        ecology: Optional[MemoryEcology] = None,
        self_layer: Optional[Any] = None,
    ) -> None:
        self.space = space
        self.ecology = ecology
        self.self_layer = self_layer

        # Scoring weights
        self.w_equidistance = 0.25
        self.w_memory = 0.25
        self.w_self = 0.20
        self.w_void = 0.30

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
                if val_a + val_b == 0:  # exact opposite
                    analysis.opposite_dims.append(i)
                else:
                    analysis.adjacent_dims.append(i)

        return analysis

    def generate(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
    ) -> ThirdChoiceCandidate:
        """Generate the base void-strategy third choice (backward compatible)."""
        candidates = self.generate_all(state_a, state_b)
        if candidates:
            return candidates[0]
        # Fallback
        analysis = self.analyze_conflict(state_a, state_b)
        return self._strategy_void(state_a, state_b, analysis)

    def generate_all(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        max_candidates: int = 8,
    ) -> List[ThirdChoiceCandidate]:
        """
        Generate multiple third choice candidates using different strategies.

        Returns candidates sorted by total score (best first).
        """
        analysis = self.analyze_conflict(state_a, state_b)

        if not analysis.has_conflict:
            # No conflict - return state_a as-is
            return [ThirdChoiceCandidate(
                state=state_a,
                strategy="no_conflict",
                rationale="No conflict detected between the two states.",
                preserved_dims=list(range(len(state_a))),
            )]

        candidates: List[ThirdChoiceCandidate] = []

        # Strategy 1: Void all conflicts
        c1 = self._strategy_void(state_a, state_b, analysis)
        candidates.append(c1)

        # Strategy 2: Fusion (resolve adjacent conflicts by taking non-zero)
        if analysis.adjacent_dims:
            c2 = self._strategy_fusion(state_a, state_b, analysis)
            candidates.append(c2)

        # Strategy 3: Dominance A (lean toward A on conflicts)
        c3 = self._strategy_dominance(state_a, state_b, analysis, dominant="a")
        candidates.append(c3)

        # Strategy 4: Dominance B (lean toward B on conflicts)
        c4 = self._strategy_dominance(state_a, state_b, analysis, dominant="b")
        candidates.append(c4)

        # Strategy 5: Emergent (find interesting neighbors of void)
        c5_list = self._strategy_emergent(state_a, state_b, analysis, max_count=3)
        candidates.extend(c5_list)

        # Score all candidates
        for c in candidates:
            self._score_candidate(c, state_a, state_b)

        # Sort by total score
        candidates.sort(key=lambda c: c.total_score, reverse=True)

        # Deduplicate by state index
        seen = set()
        unique = []
        for c in candidates:
            if c.state.index not in seen:
                seen.add(c.state.index)
                unique.append(c)

        return unique[:max_candidates]

    def _strategy_void(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        analysis: ConflictAnalysis,
    ) -> ThirdChoiceCandidate:
        """Void all conflicting dimensions, preserve agreements."""
        values = [0] * len(state_a)

        for i in analysis.agreeing_dims:
            values[i] = state_a[i].value
        for i in analysis.disagreeing_dims:
            values[i] = 0  # void

        state = CognitiveState.from_values(values)

        return ThirdChoiceCandidate(
            state=state,
            strategy="void",
            rationale=(
                f"Void all {len(analysis.disagreeing_dims)} conflicting dimensions. "
                f"Preserve {len(analysis.agreeing_dims)} agreements. "
                f"Maximum creative potential."
            ),
            preserved_dims=list(analysis.agreeing_dims),
            voided_dims=list(analysis.disagreeing_dims),
            transcended_dims=list(analysis.opposite_dims),
        )

    def _strategy_fusion(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        analysis: ConflictAnalysis,
    ) -> ThirdChoiceCandidate:
        """
        Fusion: for adjacent conflicts (0 vs ±1), take the non-zero value.
        For opposite conflicts (-1 vs +1), still void.

        This resolves "uncertainty vs commitment" conflicts by choosing
        commitment, while still voiding true oppositions.
        """
        values = [0] * len(state_a)

        for i in analysis.agreeing_dims:
            values[i] = state_a[i].value

        for i in analysis.opposite_dims:
            values[i] = 0  # still void exact opposites

        for i in analysis.adjacent_dims:
            # Take the non-zero value
            val_a = state_a[i].value
            val_b = state_b[i].value
            values[i] = val_a if val_a != 0 else val_b

        state = CognitiveState.from_values(values)

        return ThirdChoiceCandidate(
            state=state,
            strategy="fusion",
            rationale=(
                f"Fuse {len(analysis.adjacent_dims)} adjacent conflicts by "
                f"taking the committed value. Void {len(analysis.opposite_dims)} "
                f"true oppositions. Preserve {len(analysis.agreeing_dims)} agreements."
            ),
            preserved_dims=list(analysis.agreeing_dims),
            voided_dims=list(analysis.opposite_dims),
            transcended_dims=list(analysis.opposite_dims),
        )

    def _strategy_dominance(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        analysis: ConflictAnalysis,
        dominant: str,
    ) -> ThirdChoiceCandidate:
        """
        Dominance: preserve agreements, and on conflicts take values
        from the dominant state for half the dimensions, void the rest.

        This creates a "leaning" synthesis - not fully A or B, but
        influenced more by one side while still keeping void space.
        """
        values = [0] * len(state_a)

        for i in analysis.agreeing_dims:
            values[i] = state_a[i].value

        # Split conflicting dims into two halves
        conflicts = list(analysis.disagreeing_dims)
        mid = len(conflicts) // 2

        for j, i in enumerate(conflicts):
            if j < mid:
                # Dominant side
                values[i] = state_a[i].value if dominant == "a" else state_b[i].value
            else:
                # Void
                values[i] = 0

        state = CognitiveState.from_values(values)

        return ThirdChoiceCandidate(
            state=state,
            strategy=f"dominance_{dominant}",
            rationale=(
                f"Lean toward {dominant.upper()} on {mid} conflict dimensions, "
                f"void the remaining {len(conflicts) - mid}. "
                f"Preserve {len(analysis.agreeing_dims)} agreements."
            ),
            preserved_dims=list(analysis.agreeing_dims),
            voided_dims=conflicts[mid:],
            transcended_dims=list(analysis.opposite_dims),
        )

    def _strategy_emergent(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        analysis: ConflictAnalysis,
        max_count: int = 3,
    ) -> List[ThirdChoiceCandidate]:
        """
        Emergent: find states near the void-center that haven't been explored.

        These are "creative" candidates - states the agent has never visited
        that lie in the synthesis space between A and B.
        """
        # Start from the void strategy
        base = self._strategy_void(state_a, state_b, analysis)

        if not self.space:
            return []

        candidates = []
        neighbors = base.state.neighbors()
        seen = {base.state.index, state_a.index, state_b.index}

        for neighbor in neighbors:
            if neighbor.index in seen:
                continue
            seen.add(neighbor.index)

            # Must be roughly equidistant from A and B
            dist_a = neighbor.distance(state_a)
            dist_b = neighbor.distance(state_b)
            if abs(dist_a - dist_b) > 3:
                continue

            # Check if unvisited (creative potential)
            is_unvisited = True
            if self.ecology:
                mem = self.ecology.state_store.get_or_none(neighbor.index)
                if mem and not mem.is_empty:
                    is_unvisited = False

            strategy_name = "emergent_novel" if is_unvisited else "emergent_known"

            candidates.append(ThirdChoiceCandidate(
                state=neighbor,
                strategy=strategy_name,
                rationale=(
                    f"Emergent candidate: dist_A={dist_a}, dist_B={dist_b}, "
                    f"{'unvisited' if is_unvisited else 'previously visited'}. "
                    f"Near the void center, offering a unique synthesis path."
                ),
                preserved_dims=list(analysis.agreeing_dims),
                voided_dims=list(analysis.disagreeing_dims),
                transcended_dims=list(analysis.opposite_dims),
            ))

            if len(candidates) >= max_count:
                break

        return candidates

    def _score_candidate(
        self,
        candidate: ThirdChoiceCandidate,
        state_a: CognitiveState,
        state_b: CognitiveState,
    ) -> None:
        """Score a candidate on four dimensions."""

        # 1. Equidistance: how balanced is the candidate between A and B
        dist_a = candidate.state.distance(state_a)
        dist_b = candidate.state.distance(state_b)
        max_dist = 18
        balance = 1.0 - abs(dist_a - dist_b) / max_dist
        candidate.equidistance_score = balance

        # 2. Memory: success rate at this state (if ecology available)
        if self.ecology:
            mem = self.ecology.state_store.get_or_none(candidate.state.index)
            if mem and not mem.is_empty and (mem.success_count + mem.failure_count) > 0:
                candidate.memory_score = mem.success_rate
            else:
                # Unvisited states get neutral score with slight bonus for novelty
                candidate.memory_score = 0.5
        else:
            candidate.memory_score = 0.5

        # 3. Self alignment: how aligned with agent's personality
        if self.self_layer:
            candidate.self_alignment_score = self.self_layer.alignment_score(candidate.state)
        else:
            candidate.self_alignment_score = 0.5

        # 4. Void ratio: fraction of void dimensions (creative potential)
        candidate.void_ratio = candidate.state.void_count / len(candidate.state)

        # Total score (weighted combination)
        candidate.total_score = (
            self.w_equidistance * candidate.equidistance_score
            + self.w_memory * candidate.memory_score
            + self.w_self * candidate.self_alignment_score
            + self.w_void * candidate.void_ratio
        )

    def generate_with_exploration(
        self,
        state_a: CognitiveState,
        state_b: CognitiveState,
        max_neighbors: int = 5,
    ) -> List[ThirdChoiceCandidate]:
        """Backward compatible wrapper for generate_all."""
        return self.generate_all(state_a, state_b, max_candidates=max_neighbors + 5)

    def __repr__(self) -> str:
        return (
            f"ThirdChoiceGenerator(space={'set' if self.space else 'none'}, "
            f"ecology={'set' if self.ecology else 'none'}, "
            f"self={'set' if self.self_layer else 'none'})"
        )
