"""
CognitiveTrajectory: Records and analyzes the agent's path through 19683 space.

The trajectory is the agent's cognitive biography - where it has been,
what it thought, and how its cognition evolved. Unlike raw memory (which
stores individual state visits), the trajectory captures the SEQUENCE
and FLOW of cognition over time.

Key features:
- Timeline: ordered sequence of cognitive states with timestamps
- Velocity: how fast the agent moves through the space
- Clusters: regions where the agent spends disproportionate time
- Cycles: repeating patterns in the cognitive trajectory
- Drift: slow movement of the cognitive center over time

The trajectory enables:
- Visualizing the agent's cognitive history
- Detecting cognitive habits (repeated paths)
- Identifying cognitive growth (expanding exploration)
- Recognizing cognitive stagnation (stuck in a region)
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.state import CognitiveState, NUM_DIMENSIONS


@dataclass
class TrajectoryPoint:
    """A single point in the cognitive trajectory."""

    timestamp: str
    state_index: int
    state_values: Tuple[int, ...]
    context: str = ""  # brief context of what triggered this state
    trigger: str = ""  # what caused the transition
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CognitiveCluster:
    """A region of the space where the agent spends significant time."""

    center_index: int
    member_indices: List[int] = field(default_factory=list)
    visit_count: int = 0
    time_span: str = ""  # first to last visit
    label: str = ""  # emergent label (to be filled by sense-making)


@dataclass
class CognitiveCycle:
    """A repeating pattern in the cognitive trajectory."""

    pattern: List[int]  # sequence of state indices
    occurrences: int = 0  # how many times this pattern appeared
    period: int = 0  # average steps between occurrences
    label: str = ""


class CognitiveTrajectory:
    """
    Records and analyzes the agent's cognitive path through 19683 space.

    The trajectory is append-only - states are added as the agent
    processes inputs. Analysis methods can be called at any time
    to extract patterns.
    """

    def __init__(self, max_points: int = 10000) -> None:
        self.points: List[TrajectoryPoint] = []
        self.max_points = max_points

    def record(
        self,
        state: CognitiveState,
        context: str = "",
        trigger: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrajectoryPoint:
        """Record a new point in the cognitive trajectory."""
        point = TrajectoryPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            state_index=state.index,
            state_values=state.values,
            context=context,
            trigger=trigger,
            metadata=metadata or {},
        )
        self.points.append(point)
        if len(self.points) > self.max_points:
            self.points = self.points[-self.max_points:]
        return point

    @property
    def length(self) -> int:
        return len(self.points)

    @property
    def unique_states(self) -> int:
        return len(set(p.state_index for p in self.points))

    @property
    def coverage(self) -> float:
        """Fraction of 19683 space visited."""
        return self.unique_states / 19683

    def state_sequence(self) -> List[int]:
        """Ordered list of state indices."""
        return [p.state_index for p in self.points]

    def velocity(self, window: int = 10) -> float:
        """
        Average cognitive velocity over recent history.

        Velocity = average distance between consecutive states.
        High velocity = rapid cognitive shifts.
        Low velocity = staying in one region.
        """
        if len(self.points) < 2:
            return 0.0

        recent = self.points[-window:]
        distances = []
        for i in range(1, len(recent)):
            s1 = CognitiveState.from_index(recent[i-1].state_index)
            s2 = CognitiveState.from_index(recent[i].state_index)
            distances.append(s1.distance(s2))

        return sum(distances) / len(distances) if distances else 0.0

    def cognitive_center(self, window: int = 50) -> CognitiveState:
        """
        The agent's recent cognitive center of gravity.

        Computed by averaging each dimension over recent states,
        then rounding to nearest trit.
        """
        if not self.points:
            return CognitiveState.all_void()

        recent = self.points[-window:]
        dim_sums = [0.0] * NUM_DIMENSIONS

        for point in recent:
            for i, val in enumerate(point.state_values):
                dim_sums[i] += val

        dim_avgs = [s / len(recent) for s in dim_sums]

        # Round to nearest trit
        center_vals = []
        for avg in dim_avgs:
            if avg > 0.3:
                center_vals.append(1)
            elif avg < -0.3:
                center_vals.append(-1)
            else:
                center_vals.append(0)

        return CognitiveState.from_values(center_vals)

    def drift(self, window: int = 50) -> int:
        """
        How much the cognitive center has drifted recently.

        Compares the center of the last `window` points to the
        center of the `window` points before that.
        """
        if len(self.points) < window * 2:
            return 0

        recent_center = self.cognitive_center(window)
        older_points = self.points[-window*2:-window]
        older_sums = [0.0] * NUM_DIMENSIONS
        for point in older_points:
            for i, val in enumerate(point.state_values):
                older_sums[i] += val
        older_avgs = [s / len(older_points) for s in older_sums]
        older_vals = []
        for avg in older_avgs:
            if avg > 0.3:
                older_vals.append(1)
            elif avg < -0.3:
                older_vals.append(-1)
            else:
                older_vals.append(0)
        older_center = CognitiveState.from_values(older_vals)

        return older_center.distance(recent_center)

    def detect_clusters(self, radius: int = 3) -> List[CognitiveCluster]:
        """
        Find regions where the agent spends disproportionate time.

        A cluster is a state that the agent visits frequently,
        along with its nearby states that are also visited.
        """
        if not self.points:
            return []

        # Count visits per state
        visit_counts = Counter(p.state_index for p in self.points)
        total_visits = sum(visit_counts.values())

        # Expected visits per state if uniform
        expected = total_visits / 19683

        # Find states with significantly more visits than expected
        hot_states = [
            idx for idx, count in visit_counts.items()
            if count > max(3, expected * 10)  # at least 10x expected
        ]

        clusters = []
        for hot in hot_states:
            hot_state = CognitiveState.from_index(hot)
            members = [hot]

            # Find nearby visited states
            for other_idx, other_count in visit_counts.items():
                if other_idx == hot or other_count == 0:
                    continue
                other = CognitiveState.from_index(other_idx)
                if hot_state.distance(other) <= radius:
                    members.append(other_idx)

            timestamps = [
                p.timestamp for p in self.points
                if p.state_index in members
            ]

            clusters.append(CognitiveCluster(
                center_index=hot,
                member_indices=members,
                visit_count=visit_counts[hot],
                time_span=f"{min(timestamps)} to {max(timestamps)}" if timestamps else "",
            ))

        return sorted(clusters, key=lambda c: c.visit_count, reverse=True)

    def detect_cycles(self, min_length: int = 2, max_length: int = 5) -> List[CognitiveCycle]:
        """
        Find repeating subsequences in the cognitive trajectory.

        These are "cognitive habits" - patterns the agent repeats.
        """
        if len(self.points) < min_length * 2:
            return []

        seq = self.state_sequence()
        cycles: Dict[Tuple[int, ...], List[int]] = {}

        for length in range(min_length, min(max_length + 1, len(seq) // 2)):
            for i in range(len(seq) - length):
                pattern = tuple(seq[i:i+length])
                if pattern not in cycles:
                    cycles[pattern] = [i]
                else:
                    cycles[pattern].append(i)

        # Filter to patterns that repeat at least 2 times
        result = []
        for pattern, positions in cycles.items():
            if len(positions) >= 2:
                # Compute average period
                periods = [
                    positions[j+1] - positions[j]
                    for j in range(len(positions) - 1)
                ]
                avg_period = sum(periods) / len(periods) if periods else 0

                result.append(CognitiveCycle(
                    pattern=list(pattern),
                    occurrences=len(positions),
                    period=int(avg_period),
                ))

        return sorted(result, key=lambda c: c.occurrences, reverse=True)[:10]

    def explore_ratio(self) -> float:
        """
        Ratio of unique states to total visits.

        High ratio = exploratory cognition (visiting new states).
        Low ratio = exploitative cognition (staying in familiar territory).
        """
        if not self.points:
            return 0.0
        return self.unique_states / self.length

    def summary(self) -> str:
        lines = [
            f"=== Cognitive Trajectory ===",
            f"Length: {self.length} steps",
            f"Unique states: {self.unique_states}/19683 ({self.coverage:.4%})",
            f"Explore ratio: {self.explore_ratio():.2%}",
            f"Recent velocity: {self.velocity():.1f}",
            f"Recent drift: {self.drift()}",
            f"Center: #{self.cognitive_center().index} [{self.cognitive_center()}]",
        ]

        clusters = self.detect_clusters()
        if clusters:
            lines.append(f"\nClusters ({len(clusters)}):")
            for c in clusters[:5]:
                lines.append(f"  Center #{c.center_index}: {c.visit_count} visits, "
                           f"{len(c.member_indices)} members")

        cycles = self.detect_cycles()
        if cycles:
            lines.append(f"\nCycles ({len(cycles)}):")
            for cy in cycles[:3]:
                lines.append(f"  Pattern {cy.pattern}: {cy.occurrences} times, "
                           f"period={cy.period}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": [
                {
                    "timestamp": p.timestamp,
                    "state_index": p.state_index,
                    "state_values": list(p.state_values),
                    "context": p.context,
                    "trigger": p.trigger,
                    "metadata": p.metadata,
                }
                for p in self.points
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveTrajectory":
        traj = cls()
        for p_data in data.get("points", []):
            traj.points.append(TrajectoryPoint(
                timestamp=p_data["timestamp"],
                state_index=p_data["state_index"],
                state_values=tuple(p_data["state_values"]),
                context=p_data.get("context", ""),
                trigger=p_data.get("trigger", ""),
                metadata=p_data.get("metadata", {}),
            ))
        return traj

    def __repr__(self) -> str:
        return f"CognitiveTrajectory(length={self.length}, unique={self.unique_states})"
