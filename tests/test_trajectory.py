"""Tests for CognitiveTrajectory: cognitive path recording and analysis."""
import pytest

from btcu_harness.core.state import CognitiveState, NUM_DIMENSIONS, SPACE_SIZE
from btcu_harness.memory.trajectory import (
    CognitiveTrajectory,
    TrajectoryPoint,
    CognitiveCluster,
    CognitiveCycle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(index: int) -> CognitiveState:
    return CognitiveState.from_index(index)


def _record_sequence(traj: CognitiveTrajectory, indices: list[int]) -> None:
    for idx in indices:
        traj.record(
            state=CognitiveState.from_index(idx),
            context=f"state-{idx}",
            trigger="test",
        )


# ---------------------------------------------------------------------------
# TrajectoryPoint
# ---------------------------------------------------------------------------

class TestTrajectoryPoint:
    def test_defaults(self):
        pt = TrajectoryPoint(
            timestamp="2025-01-01T00:00:00Z",
            state_index=42,
            state_values=(0, 1, -1, 0, 1, -1, 0, 1, -1),
        )
        assert pt.context == ""
        assert pt.trigger == ""
        assert pt.metadata == {}

    def test_with_fields(self):
        pt = TrajectoryPoint(
            timestamp="ts",
            state_index=0,
            state_values=tuple([-1] * NUM_DIMENSIONS),
            context="hello",
            trigger="prompt",
            metadata={"k": "v"},
        )
        assert pt.context == "hello"
        assert pt.metadata["k"] == "v"


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------

class TestRecord:
    def test_single_record(self):
        traj = CognitiveTrajectory()
        state = CognitiveState.from_index(100)
        pt = traj.record(state, context="ctx", trigger="trig", metadata={"a": 1})

        assert traj.length == 1
        assert pt.state_index == 100
        assert pt.context == "ctx"
        assert pt.trigger == "trig"
        assert pt.metadata == {"a": 1}
        assert pt.timestamp  # non-empty

    def test_record_appends(self):
        traj = CognitiveTrajectory()
        for i in range(5):
            traj.record(CognitiveState.from_index(i))
        assert traj.length == 5
        assert traj.state_sequence() == [0, 1, 2, 3, 4]

    def test_max_points_trims(self):
        traj = CognitiveTrajectory(max_points=3)
        for i in range(10):
            traj.record(CognitiveState.from_index(i))
        assert traj.length == 3
        # Should keep the last 3
        assert traj.state_sequence() == [7, 8, 9]

    def test_record_returns_point(self):
        traj = CognitiveTrajectory()
        state = CognitiveState.from_index(42)
        pt = traj.record(state)
        assert isinstance(pt, TrajectoryPoint)
        assert pt.state_values == state.values

    def test_empty_metadata_defaults(self):
        traj = CognitiveTrajectory()
        pt = traj.record(CognitiveState.from_index(0))
        assert pt.metadata == {}


# ---------------------------------------------------------------------------
# Properties: length, unique_states, coverage, state_sequence
# ---------------------------------------------------------------------------

class TestProperties:
    def test_empty_trajectory(self):
        traj = CognitiveTrajectory()
        assert traj.length == 0
        assert traj.unique_states == 0
        assert traj.coverage == 0.0
        assert traj.state_sequence() == []
        assert traj.explore_ratio() == 0.0

    def test_unique_states(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [5, 5, 5, 10, 10, 20])
        assert traj.length == 6
        assert traj.unique_states == 3

    def test_coverage(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [0, 1])
        expected = 2 / SPACE_SIZE
        assert abs(traj.coverage - expected) < 1e-12

    def test_explore_ratio_all_unique(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [1, 2, 3, 4, 5])
        assert traj.explore_ratio() == 1.0

    def test_explore_ratio_all_same(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [7, 7, 7, 7])
        assert traj.explore_ratio() == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# velocity()
# ---------------------------------------------------------------------------

class TestVelocity:
    def test_empty(self):
        traj = CognitiveTrajectory()
        assert traj.velocity() == 0.0

    def test_single_point(self):
        traj = CognitiveTrajectory()
        traj.record(CognitiveState.from_index(0))
        assert traj.velocity() == 0.0

    def test_same_state_zero_velocity(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [100, 100, 100, 100])
        assert traj.velocity() == 0.0

    def test_distance_between_adjacent(self):
        """States 0 and 1 differ by 1 in one dimension."""
        traj = CognitiveTrajectory()
        _record_sequence(traj, [0, 1])
        assert traj.velocity() == pytest.approx(1.0)

    def test_window_parameter(self):
        traj = CognitiveTrajectory()
        # Old points with high distance, recent with zero
        _record_sequence(traj, [0, 100, 0, 100, 50, 50, 50, 50])
        v_recent = traj.velocity(window=3)
        assert v_recent == 0.0  # last 3 are same state


# ---------------------------------------------------------------------------
# cognitive_center()
# ---------------------------------------------------------------------------

class TestCognitiveCenter:
    def test_empty_returns_all_void(self):
        traj = CognitiveTrajectory()
        center = traj.cognitive_center()
        assert center.index == SPACE_SIZE // 2  # all-void = 9841

    def test_all_same_state(self):
        traj = CognitiveTrajectory()
        state = CognitiveState.from_index(0)  # all YIN
        for _ in range(10):
            traj.record(state)
        center = traj.cognitive_center()
        assert center.index == 0

    def test_mixed_states(self):
        traj = CognitiveTrajectory()
        # Alternate between all-YIN (0) and all-YANG (19682)
        for i in range(10):
            idx = 0 if i % 2 == 0 else SPACE_SIZE - 1
            traj.record(CognitiveState.from_index(idx))
        center = traj.cognitive_center()
        # Average of -1 and +1 is 0 -> all VOID
        assert center.index == SPACE_SIZE // 2

    def test_window_limit(self):
        traj = CognitiveTrajectory()
        # First 20 records: all YIN
        for _ in range(20):
            traj.record(CognitiveState.from_index(0))
        # Last 5 records: all YANG
        for _ in range(5):
            traj.record(CognitiveState.from_index(SPACE_SIZE - 1))
        center = traj.cognitive_center(window=5)
        # Should reflect only last 5 -> all YANG
        assert center.index == SPACE_SIZE - 1


# ---------------------------------------------------------------------------
# drift()
# ---------------------------------------------------------------------------

class TestDrift:
    def test_empty(self):
        traj = CognitiveTrajectory()
        assert traj.drift() == 0

    def test_insufficient_points(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [0, 1, 2, 3])
        assert traj.drift(window=50) == 0  # < 100 points

    def test_no_drift(self):
        """Same states throughout -> drift = 0."""
        traj = CognitiveTrajectory()
        for _ in range(100):
            traj.record(CognitiveState.from_index(50))
        assert traj.drift(window=50) == 0

    def test_actual_drift(self):
        """First half all-YIN, second half all-YANG -> large drift."""
        traj = CognitiveTrajectory()
        for _ in range(50):
            traj.record(CognitiveState.from_index(0))
        for _ in range(50):
            traj.record(CognitiveState.from_index(SPACE_SIZE - 1))
        d = traj.drift(window=50)
        assert d == NUM_DIMENSIONS * 2  # all 9 dims flipped, each by 2


# ---------------------------------------------------------------------------
# detect_clusters()
# ---------------------------------------------------------------------------

class TestDetectClusters:
    def test_empty(self):
        traj = CognitiveTrajectory()
        assert traj.detect_clusters() == []

    def test_no_clusters(self):
        """Each state visited once -> no clusters."""
        traj = CognitiveTrajectory()
        _record_sequence(traj, list(range(20)))
        assert traj.detect_clusters() == []

    def test_finds_cluster(self):
        """Visit one state 10 times -> should be a cluster."""
        traj = CognitiveTrajectory()
        for _ in range(10):
            traj.record(CognitiveState.from_index(100))
        clusters = traj.detect_clusters()
        assert len(clusters) >= 1
        assert clusters[0].center_index == 100
        assert clusters[0].visit_count == 10

    def test_cluster_sorted_by_visits(self):
        """Most visited state should be first."""
        traj = CognitiveTrajectory()
        for _ in range(15):
            traj.record(CognitiveState.from_index(200))
        for _ in range(5):
            traj.record(CognitiveState.from_index(50))
        clusters = traj.detect_clusters()
        if len(clusters) >= 2:
            assert clusters[0].visit_count >= clusters[1].visit_count

    def test_cluster_includes_nearby(self):
        """States within radius should be included as members."""
        traj = CognitiveTrajectory()
        # State 0 and state 1 differ by 1 trit (distance=1)
        for _ in range(10):
            traj.record(CognitiveState.from_index(0))
        for _ in range(3):
            traj.record(CognitiveState.from_index(1))
        clusters = traj.detect_clusters(radius=3)
        if clusters:
            members = clusters[0].member_indices
            assert 0 in members
            assert 1 in members


# ---------------------------------------------------------------------------
# detect_cycles()
# ---------------------------------------------------------------------------

class TestDetectCycles:
    def test_empty(self):
        traj = CognitiveTrajectory()
        assert traj.detect_cycles() == []

    def test_too_short(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [0, 1])
        assert traj.detect_cycles() == []

    def test_finds_simple_cycle(self):
        """Pattern [0, 1] repeated 3 times."""
        traj = CognitiveTrajectory()
        _record_sequence(traj, [0, 1, 0, 1, 0, 1])
        cycles = traj.detect_cycles(min_length=2, max_length=2)
        assert len(cycles) >= 1
        cycle = cycles[0]
        assert cycle.pattern == [0, 1]
        assert cycle.occurrences >= 2

    def test_no_cycles_in_random_sequence(self):
        """Unique sequence should have no cycles."""
        traj = CognitiveTrajectory()
        _record_sequence(traj, list(range(20)))
        cycles = traj.detect_cycles(min_length=2, max_length=5)
        # All unique, so no pattern repeats
        for c in cycles:
            assert c.occurrences < 2

    def test_cycle_sorted_by_occurrences(self):
        """Most frequent cycle first."""
        traj = CognitiveTrajectory()
        # Pattern [5, 6] repeated 5 times
        for _ in range(5):
            _record_sequence(traj, [5, 6])
        cycles = traj.detect_cycles(min_length=2, max_length=2)
        if cycles:
            assert cycles[0].occurrences >= cycles[-1].occurrences

    def test_max_results(self):
        """Should return at most 10 cycles."""
        traj = CognitiveTrajectory()
        # Create many repeating patterns
        for _ in range(3):
            _record_sequence(traj, [1, 2, 3, 4, 5])
        cycles = traj.detect_cycles(min_length=2, max_length=5)
        assert len(cycles) <= 10


# ---------------------------------------------------------------------------
# Serialization: to_dict / from_dict
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_roundtrip_empty(self):
        traj = CognitiveTrajectory()
        data = traj.to_dict()
        restored = CognitiveTrajectory.from_dict(data)
        assert restored.length == 0

    def test_roundtrip_with_data(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [10, 20, 30])
        data = traj.to_dict()
        restored = CognitiveTrajectory.from_dict(data)
        assert restored.length == 3
        assert restored.state_sequence() == [10, 20, 30]
        # Check point fields preserved
        pt = restored.points[0]
        assert pt.context == "state-10"
        assert pt.trigger == "test"

    def test_from_dict_empty(self):
        restored = CognitiveTrajectory.from_dict({"points": []})
        assert restored.length == 0

    def test_from_dict_missing_points_key(self):
        restored = CognitiveTrajectory.from_dict({})
        assert restored.length == 0


# ---------------------------------------------------------------------------
# summary()
# ---------------------------------------------------------------------------

class TestSummary:
    def test_empty_summary(self):
        traj = CognitiveTrajectory()
        s = traj.summary()
        assert "Length: 0" in s
        assert "Unique states: 0" in s

    def test_summary_with_data(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [0, 1, 2])
        s = traj.summary()
        assert "Length: 3" in s
        assert "Unique states: 3" in s

    def test_summary_includes_clusters(self):
        traj = CognitiveTrajectory()
        for _ in range(10):
            traj.record(CognitiveState.from_index(42))
        s = traj.summary()
        assert "Clusters" in s

    def test_summary_includes_cycles(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [5, 6, 5, 6, 5, 6])
        s = traj.summary()
        assert "Cycles" in s


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr(self):
        traj = CognitiveTrajectory()
        _record_sequence(traj, [1, 2, 3])
        r = repr(traj)
        assert "length=3" in r
        assert "unique=3" in r

    def test_repr_empty(self):
        traj = CognitiveTrajectory()
        r = repr(traj)
        assert "length=0" in r
