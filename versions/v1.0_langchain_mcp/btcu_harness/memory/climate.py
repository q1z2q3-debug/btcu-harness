"""
Cognitive Climate: Long-term temporal dynamics of the 19683 space.

While CognitiveSeason captures static patterns (attractor, trap, etc.),
CognitiveClimate tracks how those patterns evolve over time:

- Polarity trend: is the agent becoming more yang or more yin?
- Exploration rate: is the agent still discovering new states?
- Cognitive rhythm: are there periodic patterns in state visits?
- Climate zones: which regions of the space are "warm" (active) vs "cold" (dormant)?
- Drift: is the agent's cognitive center of gravity shifting?

This is the "weather report" for the 19683 cognitive space.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ecology import MemoryEcology, CognitiveSeason
from .trajectory import CognitiveTrajectory
from ..core.state import CognitiveState


@dataclass
class PolaritySnapshot:
    """A snapshot of the agent's polarity balance at a point in time."""

    step: int
    state_index: int
    yang_count: int
    yin_count: int
    void_count: int
    polarity: int  # yang - yin

    @classmethod
    def from_state(cls, step: int, state: CognitiveState) -> "PolaritySnapshot":
        return cls(
            step=step,
            state_index=state.index,
            yang_count=state.yang_count,
            yin_count=state.yin_count,
            void_count=state.void_count,
            polarity=state.polarity,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "state_index": self.state_index,
            "yang": self.yang_count,
            "yin": self.yin_count,
            "void": self.void_count,
            "polarity": self.polarity,
        }


@dataclass
class ClimateZone:
    """A region of the cognitive space with a temperature (activity level)."""

    center_index: int
    member_indices: List[int]
    temperature: float  # 0.0 (cold/dormant) to 1.0 (hot/active)
    visit_count: int
    avg_polarity: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": self.center_index,
            "members": len(self.member_indices),
            "temperature": round(self.temperature, 3),
            "visits": self.visit_count,
            "avg_polarity": round(self.avg_polarity, 2),
        }


@dataclass
class ClimateReport:
    """A comprehensive cognitive climate report."""

    # Overall stats
    total_steps: int = 0
    unique_states: int = 0
    exploration_rate: float = 0.0

    # Polarity trend
    avg_polarity: float = 0.0
    polarity_trend: float = 0.0  # slope: positive = more yang over time
    polarity_volatility: float = 0.0

    # Exploration dynamics
    recent_new_state_rate: float = 0.0  # new states in last N steps
    exploration_phase: str = "unknown"  # "expanding", "consolidating", "stagnant"

    # Climate zones
    zones: List[ClimateZone] = field(default_factory=list)

    # Rhythm
    dominant_period: Optional[int] = None  # most common cycle length
    rhythm_regularity: float = 0.0  # 0-1, how regular the rhythm is

    # Drift
    drift_magnitude: float = 0.0
    drift_direction: Optional[CognitiveState] = None

    # Summary
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_steps": self.total_steps,
            "unique_states": self.unique_states,
            "exploration_rate": round(self.exploration_rate, 4),
            "avg_polarity": round(self.avg_polarity, 2),
            "polarity_trend": round(self.polarity_trend, 4),
            "polarity_volatility": round(self.polarity_volatility, 2),
            "recent_new_state_rate": round(self.recent_new_state_rate, 4),
            "exploration_phase": self.exploration_phase,
            "zones": [z.to_dict() for z in self.zones],
            "dominant_period": self.dominant_period,
            "rhythm_regularity": round(self.rhythm_regularity, 3),
            "drift_magnitude": round(self.drift_magnitude, 2),
            "drift_direction": (
                self.drift_direction.index if self.drift_direction else None
            ),
            "summary": self.summary,
        }


class CognitiveClimate:
    """
    Tracks long-term temporal dynamics of cognitive states.

    Usage:
        climate = CognitiveClimate()
        # After each cognitive step:
        climate.snapshot(state)
        # Generate report:
        report = climate.report()
    """

    def __init__(self, window_size: int = 20) -> None:
        """
        Args:
            window_size: Size of the sliding window for recent analysis.
        """
        self.window_size = window_size
        self._snapshots: List[PolaritySnapshot] = []
        self._visited: set[int] = set()
        self._step: int = 0

    def snapshot(self, state: CognitiveState) -> PolaritySnapshot:
        """Record a polarity snapshot for the current state."""
        snap = PolaritySnapshot.from_state(self._step, state)
        self._snapshots.append(snap)
        self._visited.add(state.index)
        self._step += 1
        return snap

    def report(
        self,
        ecology: Optional[MemoryEcology] = None,
        trajectory: Optional[CognitiveTrajectory] = None,
    ) -> ClimateReport:
        """Generate a comprehensive climate report."""
        report = ClimateReport()
        report.total_steps = len(self._snapshots)

        if report.total_steps == 0:
            report.summary = "No cognitive activity recorded yet."
            return report

        # Unique states
        report.unique_states = len(self._visited)
        report.exploration_rate = len(self._visited) / max(1, report.total_steps)

        # Polarity analysis
        polarities = [s.polarity for s in self._snapshots]
        report.avg_polarity = sum(polarities) / len(polarities)
        report.polarity_trend = self._compute_trend(polarities)
        report.polarity_volatility = self._compute_volatility(polarities)

        # Exploration dynamics (recent window)
        window = self._snapshots[-self.window_size :] if len(self._snapshots) >= self.window_size else self._snapshots
        window_states = {s.state_index for s in window}
        new_in_window = len(window_states - self._visited.union(window_states) | window_states - self._visited)
        # Simpler: count states in window that weren't seen before the window
        pre_window_visited = {s.state_index for s in self._snapshots[: -len(window)]} if len(self._snapshots) > len(window) else set()
        new_in_window = len(window_states - pre_window_visited)
        report.recent_new_state_rate = new_in_window / max(1, len(window))

        if report.recent_new_state_rate > 0.3:
            report.exploration_phase = "expanding"
        elif report.recent_new_state_rate > 0.1:
            report.exploration_phase = "consolidating"
        else:
            report.exploration_phase = "stagnant"

        # Climate zones: cluster visited states by proximity
        report.zones = self._identify_zones()

        # Rhythm analysis
        if trajectory and trajectory.length > 4:
            cycles = trajectory.detect_cycles()
            if cycles:
                # Most common period
                period_counts = Counter(c.period for c in cycles)
                report.dominant_period = period_counts.most_common(1)[0][0]
                # Regularity: how many cycles share the dominant period
                dominant_count = period_counts.most_common(1)[0][1]
                report.rhythm_regularity = dominant_count / len(cycles)

        # Drift: compare first-half center to second-half center
        if len(self._snapshots) >= 4:
            first_half = self._snapshots[: len(self._snapshots) // 2]
            second_half = self._snapshots[len(self._snapshots) // 2 :]
            first_center = self._compute_center(first_half)
            second_center = self._compute_center(second_half)
            if first_center and second_center:
                report.drift_magnitude = first_center.distance(second_center)
                report.drift_direction = second_center

        # Summary
        report.summary = self._generate_summary(report)
        return report

    def _compute_trend(self, values: Sequence[float]) -> float:
        """Compute linear trend slope (simple least squares)."""
        n = len(values)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def _compute_volatility(self, values: Sequence[float]) -> float:
        """Compute standard deviation of consecutive differences."""
        if len(values) < 2:
            return 0.0
        diffs = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
        mean_diff = sum(diffs) / len(diffs)
        variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
        return variance ** 0.5

    def _compute_center(self, snapshots: List[PolaritySnapshot]) -> Optional[CognitiveState]:
        """Compute the cognitive center of a set of snapshots."""
        if not snapshots:
            return None
        # Average the trit values across all snapshots
        total = [0] * 9
        for snap in snapshots:
            state = CognitiveState.from_index(snap.state_index)
            for i in range(9):
                total[i] += state[i].value
        n = len(snapshots)
        avg = [round(t / n) for t in total]
        # Clamp to valid trit range
        avg = [max(-1, min(1, v)) for v in avg]
        return CognitiveState.from_values(avg)

    def _identify_zones(self) -> List[ClimateZone]:
        """Identify active climate zones using simple proximity clustering."""
        if not self._snapshots:
            return []

        # Count visits per state
        visit_counts: Dict[int, int] = {}
        for snap in self._snapshots:
            visit_counts[snap.state_index] = visit_counts.get(snap.state_index, 0) + 1

        # Simple zone identification: group by proximity
        visited_indices = sorted(visit_counts.keys())
        if not visited_indices:
            return []

        zones: List[ClimateZone] = []
        assigned: set[int] = set()

        # Pick top visited as zone centers
        sorted_by_visits = sorted(visit_counts.items(), key=lambda x: -x[1])
        max_zones = min(5, len(sorted_by_visits))

        for center_idx, center_visits in sorted_by_visits[:max_zones]:
            if center_idx in assigned:
                continue
            # Find nearby states within radius
            members = [center_idx]
            assigned.add(center_idx)
            total_visits = center_visits
            total_polarity = CognitiveState.from_index(center_idx).polarity

            for idx in visited_indices:
                if idx in assigned:
                    continue
                state = CognitiveState.from_index(center_idx)
                other = CognitiveState.from_index(idx)
                if state.distance(other) <= 3:
                    members.append(idx)
                    assigned.add(idx)
                    total_visits += visit_counts[idx]
                    total_polarity += other.polarity

            if len(members) > 0:
                total_steps = len(self._snapshots)
                temperature = total_visits / total_steps if total_steps > 0 else 0.0
                zones.append(ClimateZone(
                    center_index=center_idx,
                    member_indices=members,
                    temperature=min(1.0, temperature),
                    visit_count=total_visits,
                    avg_polarity=total_polarity / len(members),
                ))

        return zones

    def _generate_summary(self, report: ClimateReport) -> str:
        """Generate a human-readable climate summary."""
        parts: List[str] = []

        # Polarity
        if report.avg_polarity > 2:
            parts.append("Yang-dominant (assertive/active)")
        elif report.avg_polarity < -2:
            parts.append("Yin-dominant (reflective/receptive)")
        else:
            parts.append("Balanced polarity")

        if report.polarity_trend > 0.3:
            parts.append("trending toward more yang")
        elif report.polarity_trend < -0.3:
            parts.append("trending toward more yin")

        # Exploration
        parts.append(f"exploration phase: {report.exploration_phase}")
        parts.append(f"{report.unique_states} unique states visited "
                     f"({report.exploration_rate:.0%} uniqueness rate)")

        # Zones
        if report.zones:
            hot_zones = [z for z in report.zones if z.temperature > 0.1]
            parts.append(f"{len(hot_zones)} active cognitive zones")

        # Drift
        if report.drift_magnitude > 5:
            parts.append(f"significant cognitive drift ({report.drift_magnitude:.1f})")
        elif report.drift_magnitude > 0:
            parts.append(f"minor cognitive drift ({report.drift_magnitude:.1f})")

        # Rhythm
        if report.dominant_period:
            parts.append(f"rhythm period ~{report.dominant_period} steps "
                        f"(regularity: {report.rhythm_regularity:.0%})")

        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for persistence."""
        return {
            "window_size": self.window_size,
            "snapshots": [s.to_dict() for s in self._snapshots],
            "visited": list(self._visited),
            "step": self._step,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveClimate":
        """Deserialize from dict."""
        climate = cls(window_size=data.get("window_size", 20))
        climate._step = data.get("step", 0)
        climate._visited = set(data.get("visited", []))
        climate._snapshots = [
            PolaritySnapshot(
                step=s["step"],
                state_index=s["state_index"],
                yang_count=s["yang"],
                yin_count=s["yin"],
                void_count=s["void"],
                polarity=s["polarity"],
            )
            for s in data.get("snapshots", [])
        ]
        return climate

    def __repr__(self) -> str:
        return (
            f"CognitiveClimate(steps={self._step}, "
            f"unique={len(self._visited)}, "
            f"window={self.window_size})"
        )
