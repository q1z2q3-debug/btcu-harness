"""
Cognitive Laziness Defense System for the BTCU dual-system architecture.

Kahneman-style cognitive bias detection that prevents System 1 from falling
into four common failure modes:

    1. Pattern rigidity       -- applying cached intuition to dissimilar states
    2. State space blindness -- avoiding unexplored cognitive regions
    3. Feedback loop traps   -- sub-optimal patterns reinforcing themselves
    4. Over-reliance bias    -- missing novel situations due to cached shortcuts

These defenses act as a "safety guard" around System 1, forcing escalation to
System 2 (LLM deliberation) when fast intuition is likely to err.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..core.state import CognitiveState, SPACE_SIZE
from .system1 import CognitivePattern, System1PatternLibrary

logger = logging.getLogger("btcu_harness.cognition.defense")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SafetyConstants:
    """Tunable hyper-parameters for the cognitive safety guard.

    All values are chosen to balance exploration vs exploitation in the
    19683-state ternary cognitive space.
    """

    DEFAULT_RIGIDITY_THRESHOLD: int = 3
    MAX_ACCEPTABLE_DISTANCE: int = 6
    LOW_COVERAGE_THRESHOLD: float = 0.10
    COVERAGE_BOOST_FACTOR: float = 2.0
    DEFAULT_EPSILON: float = 0.10
    FEEDBACK_TRAP_LOOKBACK: int = 5
    FEEDBACK_TRAP_DECLINE_THRESHOLD: float = 0.05  # minimum declining slope to flag
    BLIND_SPOT_MIN_DENSITY: float = 0.01
    BLIND_SPOT_WINDOW_SIZE: int = 100
    MAX_BLIND_SPOTS: int = 10
    EARLY_SESSION_DECISIONS: int = 10
    EARLY_SESSION_EPSILON: float = 0.25


# ---------------------------------------------------------------------------
# CognitiveSafetyGuard
# ---------------------------------------------------------------------------

class CognitiveSafetyGuard:
    """Detects and prevents cognitive laziness in System 1 pattern matching.

    Responsibilities
    ----------------
    - **Pattern rigidity**: Detect when a pattern is applied to a cognitive
      state that is too distant from the state where it was originally learned.
    - **Exploration maintenance**: Force System 2 probabilistically (epsilon-
      greedy) and boost exploration when state-space coverage is critically low.
    - **Feedback loop traps**: Detect when a pattern is used repeatedly with
      declining success, indicating a self-reinforcing sub-optimal loop.
    - **Coverage blindness**: Identify contiguous regions of the 19683-state
      space that have never been visited, so exploration can be directed there.

    The guard is stateless -- all required state is passed in as arguments or
    read from the ``System1PatternLibrary``.
    """

    def __init__(self, constants: Optional[SafetyConstants] = None) -> None:
        self.constants = constants or SafetyConstants()

    # ------------------------------------------------------------------
    # 1. Pattern rigidity detection
    # ------------------------------------------------------------------

    def detect_rigidity(
        self,
        current_state: CognitiveState,
        matched_pattern_state: Optional[CognitiveState],
        threshold: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Detect pattern rigidity between current and matched pattern states.

        If the cognitive distance between the current input's state and the
        matched pattern's stored state exceeds ``threshold``, the pattern is
        being applied inappropriately (same intuition for a different
        situation).  This is the core defence against *pattern rigidity*.

        Args:
            current_state: the actual cognitive state of the current input.
            matched_pattern_state: the state stored in the matched pattern;
                ``None`` if no pattern was matched.
            threshold: maximum acceptable distance before rigidity is flagged;
                defaults to ``SafetyConstants.DEFAULT_RIGIDITY_THRESHOLD``.

        Returns:
            dict with keys:

            - ``rigid`` (bool): ``True`` when the pattern is being applied too
              far from its home state.
            - ``distance`` (int): the computed cognitive distance
              (``-1`` when no pattern was matched).
            - ``recommendation`` (str): human-readable guidance.
        """
        threshold = threshold or self.constants.DEFAULT_RIGIDITY_THRESHOLD

        if matched_pattern_state is None:
            return {
                "rigid": False,
                "distance": -1,
                "recommendation": "No pattern matched -- cannot assess rigidity.",
            }

        distance = current_state.distance(matched_pattern_state)

        if distance > threshold:
            recommendation = (
                f"Pattern rigidity detected: distance={distance} "
                f"(threshold={threshold}). "
                "The same pattern is being applied to a dissimilar state. "
                "Recommend System 2 deliberation."
            )
            logger.warning("[CognitiveSafetyGuard] %s", recommendation)
            return {
                "rigid": True,
                "distance": distance,
                "recommendation": recommendation,
            }

        return {
            "rigid": False,
            "distance": distance,
            "recommendation": (
                f"Distance {distance} <= threshold {threshold}. "
                "Pattern application is appropriate."
            ),
        }

    # ------------------------------------------------------------------
    # 2. Epsilon-exploration strategy
    # ------------------------------------------------------------------

    def should_explore(
        self,
        epsilon: Optional[float] = None,
        session_stats: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Determine whether to force System 2 exploration.

        Exploration is triggered probabilistically (epsilon-greedy).  The
        probability is boosted when state-space coverage is critically low,
        ensuring the system does not get stuck in a tiny corner of the
        19683-dimensional space.

        Args:
            epsilon: base exploration probability in ``[0.0, 1.0]``;
                defaults to ``SafetyConstants.DEFAULT_EPSILON``.
            session_stats: dict with optional keys:

                - ``coverage`` (float): current state coverage ratio ``[0, 1]``.
                - ``total_decisions`` (int): decisions made this session.

        Returns:
            ``True`` if System 2 should be forced for exploration.
        """
        epsilon = epsilon if epsilon is not None else self.constants.DEFAULT_EPSILON
        session_stats = session_stats or {}

        coverage = float(session_stats.get("coverage", 0.0))
        total_decisions = int(session_stats.get("total_decisions", 0))

        # Boost epsilon when coverage is critically low
        if coverage < self.constants.LOW_COVERAGE_THRESHOLD:
            effective_epsilon = min(
                1.0, epsilon * self.constants.COVERAGE_BOOST_FACTOR
            )
            logger.info(
                "[CognitiveSafetyGuard] Coverage %.2f%% < threshold %.2f%% -- "
                "boosting epsilon %.2f -> %.2f",
                coverage * 100,
                self.constants.LOW_COVERAGE_THRESHOLD * 100,
                epsilon,
                effective_epsilon,
            )
        else:
            effective_epsilon = epsilon

        # Deterministic exploration for very early sessions
        if total_decisions < self.constants.EARLY_SESSION_DECISIONS:
            effective_epsilon = max(effective_epsilon, self.constants.EARLY_SESSION_EPSILON)

        explore = random.random() < effective_epsilon

        if explore:
            logger.info(
                "[CognitiveSafetyGuard] Epsilon-exploration triggered "
                "(effective_epsilon=%.3f)",
                effective_epsilon,
            )

        return explore

    # ------------------------------------------------------------------
    # 3. Feedback loop trap detection
    # ------------------------------------------------------------------

    def detect_feedback_trap(
        self,
        pattern: Optional[CognitivePattern],
        recent_decisions: Sequence[Dict[str, Any]],
        lookback: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Detect if a pattern is trapped in a self-reinforcing decline.

        When the same pattern is used repeatedly and its success rate or
        confidence declines over time, it indicates a *feedback loop trap*:
        the pattern keeps being selected despite worsening outcomes, because
        System 1 has no mechanism to question itself.

        Args:
            pattern: the pattern to evaluate; ``None`` if no pattern matched.
            recent_decisions: sequence of recent decision records.  Each item
                should be a dict with keys:

                - ``pattern_hash`` (str): hash of the pattern used.
                - ``confidence`` (float): confidence of that decision.
                - ``success`` (bool): whether the decision was successful.

            lookback: number of recent decisions to analyse;
                defaults to ``SafetyConstants.FEEDBACK_TRAP_LOOKBACK``.

        Returns:
            dict with keys:

            - ``trapped`` (bool): ``True`` when a trap is detected.
            - ``decline_rate`` (float): magnitude of the decline (higher = worse).
        """
        lookback = lookback or self.constants.FEEDBACK_TRAP_LOOKBACK

        if pattern is None:
            return {"trapped": False, "decline_rate": 0.0}

        pattern_hash = pattern.input_hash
        pattern_decisions = [
            d
            for d in recent_decisions[-lookback:]
            if d.get("pattern_hash") == pattern_hash
        ]

        if len(pattern_decisions) < lookback:
            # Not enough data for this pattern within the lookback window
            return {"trapped": False, "decline_rate": 0.0}

        confidences = [float(d.get("confidence", 0.5)) for d in pattern_decisions]
        successes = [1.0 if d.get("success", False) else 0.0 for d in pattern_decisions]

        # Simple linear-regression slope for confidence trend
        n = len(confidences)
        x_mean = (n - 1) / 2.0
        y_mean = sum(confidences) / n

        numerator = sum(
            (i - x_mean) * (confidences[i] - y_mean) for i in range(n)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0.0

        # Success-rate trend (first vs last)
        success_decline = (successes[-1] - successes[0]) / max(1, n - 1)

        # Combined decline metric: negative confidence slope + declining success
        decline_rate = -slope + (-success_decline)

        trapped = decline_rate > self.constants.FEEDBACK_TRAP_DECLINE_THRESHOLD

        if trapped:
            logger.warning(
                "[CognitiveSafetyGuard] Feedback loop trap detected for "
                "pattern %s: decline_rate=%.3f",
                pattern_hash[:8],
                decline_rate,
            )

        return {"trapped": trapped, "decline_rate": decline_rate}

    # ------------------------------------------------------------------
    # 4. Coverage blindness monitor
    # ------------------------------------------------------------------

    def get_blind_spots(
        self,
        pattern_library: System1PatternLibrary,
        min_density: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Identify cognitive regions that have never been explored.

        Scans the 19683-dimensional state space in sliding windows and reports
        contiguous regions with zero or near-zero pattern density.  These
        *blind spots* represent cognitive territory that System 1 has never
        visited, increasing the risk of poor decisions in novel situations.

        Args:
            pattern_library: the System 1 pattern library to analyse.
            min_density: minimum acceptable density ratio ``[0, 1]``;
                defaults to ``SafetyConstants.BLIND_SPOT_MIN_DENSITY``.

        Returns:
            List of blind-spot dicts, each with keys:

            - ``state_range`` (Tuple[int, int]): inclusive start/end state indices.
            - ``density`` (float): ratio of explored states in the window.
            - ``size`` (int): number of states in the blind-spot region.
        """
        min_density = min_density or self.constants.BLIND_SPOT_MIN_DENSITY
        window_size = self.constants.BLIND_SPOT_WINDOW_SIZE

        covered: set = getattr(pattern_library, "_covered_states", set())
        if not covered:
            return [
                {
                    "state_range": (0, SPACE_SIZE - 1),
                    "density": 0.0,
                    "size": SPACE_SIZE,
                }
            ]

        blind_spots: List[Dict[str, Any]] = []
        current_start: Optional[int] = None
        current_empty = 0

        for start in range(0, SPACE_SIZE, window_size):
            end = min(start + window_size - 1, SPACE_SIZE - 1)
            window_states = set(range(start, end + 1))
            explored = len(window_states & covered)
            total = len(window_states)
            density = explored / total if total > 0 else 0.0

            if density < min_density:
                if current_start is None:
                    current_start = start
                    current_empty = total
                else:
                    current_empty += total
            else:
                if current_start is not None:
                    blind_spots.append(
                        {
                            "state_range": (current_start, start - 1),
                            "density": 0.0,
                            "size": current_empty,
                        }
                    )
                    current_start = None
                    current_empty = 0

        # Close final trailing window
        if current_start is not None:
            blind_spots.append(
                {
                    "state_range": (current_start, SPACE_SIZE - 1),
                    "density": 0.0,
                    "size": current_empty,
                }
            )

        # Limit to top N largest blind spots
        blind_spots.sort(key=lambda x: x["size"], reverse=True)
        return blind_spots[: self.constants.MAX_BLIND_SPOTS]

    # ------------------------------------------------------------------
    # 5. Aggregate safety summary
    # ------------------------------------------------------------------

    def get_coverage_summary(
        self,
        pattern_library: System1PatternLibrary,
        recent_decisions: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a comprehensive cognitive-safety summary.

        This is a convenience method that runs all four defence mechanisms and
        returns a single dict suitable for logging or dashboard display.

        Args:
            pattern_library: the System 1 pattern library.
            recent_decisions: recent decision history for trap detection.

        Returns:
            dict with keys: ``coverage``, ``coverage_pct``,
            ``blind_spots_count``, ``blind_spots_total_states``,
            ``blind_spots_pct``, ``feedback_trap_detected``,
            ``feedback_trap_decline_rate``, ``recommendation``.
        """
        blind_spots = self.get_blind_spots(pattern_library)
        total_blind = sum(s["size"] for s in blind_spots)

        coverage = pattern_library.get_state_coverage()

        # Find the most-used recent pattern and test it for traps
        recent_hashes = [
            d.get("pattern_hash")
            for d in recent_decisions[-self.constants.FEEDBACK_TRAP_LOOKBACK :]
            if d.get("pattern_hash")
        ]

        trap_result = {"trapped": False, "decline_rate": 0.0}
        if recent_hashes:
            from collections import Counter

            most_common_hash = Counter(recent_hashes).most_common(1)[0][0]
            target_pattern: Optional[CognitivePattern] = None
            for p in getattr(pattern_library, "_patterns", []):
                if p.input_hash == most_common_hash:
                    target_pattern = p
                    break
            trap_result = self.detect_feedback_trap(target_pattern, recent_decisions)

        recommendation = (
            "High exploration recommended"
            if coverage < self.constants.LOW_COVERAGE_THRESHOLD
            else "Normal operation"
        )

        return {
            "coverage": coverage,
            "coverage_pct": coverage * 100,
            "blind_spots_count": len(blind_spots),
            "blind_spots_total_states": total_blind,
            "blind_spots_pct": total_blind / SPACE_SIZE * 100,
            "feedback_trap_detected": trap_result["trapped"],
            "feedback_trap_decline_rate": trap_result["decline_rate"],
            "recommendation": recommendation,
        }
