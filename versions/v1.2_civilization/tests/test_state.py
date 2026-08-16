"""Tests for CognitiveState and CognitiveSpace."""
import pytest
from btcu_harness.core.state import (
    CognitiveState, NUM_DIMENSIONS, SPACE_SIZE,
    ALL_YIN_INDEX, ALL_VOID_INDEX, ALL_YANG_INDEX,
)
from btcu_harness.core.space import CognitiveSpace


class TestStateCreation:
    def test_from_values(self):
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        assert len(s) == 9

    def test_wrong_dimension_count(self):
        with pytest.raises(ValueError):
            CognitiveState.from_values([1, 0, -1])

    def test_special_states(self):
        assert CognitiveState.all_yin().index == ALL_YIN_INDEX
        assert CognitiveState.all_void().index == ALL_VOID_INDEX
        assert CognitiveState.all_yang().index == ALL_YANG_INDEX

    def test_space_size(self):
        assert SPACE_SIZE == 19683
        assert NUM_DIMENSIONS == 9


class TestStateEncoding:
    def test_all_yin_index(self):
        assert CognitiveState.all_yin().index == 0

    def test_all_yang_index(self):
        assert CognitiveState.all_yang().index == 19682

    def test_all_void_index(self):
        assert CognitiveState.all_void().index == 9841

    def test_roundtrip_all_indices(self):
        """Every index 0-19682 should round-trip correctly."""
        for idx in range(SPACE_SIZE):
            s = CognitiveState.from_index(idx)
            assert s.index == idx

    def test_roundtrip_random(self):
        import random
        for _ in range(500):
            idx = random.randint(0, SPACE_SIZE - 1)
            s = CognitiveState.from_index(idx)
            assert s.index == idx


class TestStateOpposite:
    def test_opposite_all_yin(self):
        assert CognitiveState.all_yin().opposite().index == 19682

    def test_opposite_all_yang(self):
        assert CognitiveState.all_yang().opposite().index == 0

    def test_opposite_all_void(self):
        """Void is invariant under opposition."""
        assert CognitiveState.all_void().opposite().index == 9841

    def test_double_opposite(self):
        import random
        for _ in range(100):
            idx = random.randint(0, SPACE_SIZE - 1)
            s = CognitiveState.from_index(idx)
            assert s.opposite().opposite().index == idx


class TestStateDistance:
    def test_self_distance(self):
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        assert s.distance(s) == 0

    def test_extreme_distance(self):
        assert CognitiveState.all_yin().distance(CognitiveState.all_yang()) == 18

    def test_void_to_extreme(self):
        assert CognitiveState.all_void().distance(CognitiveState.all_yang()) == 9
        assert CognitiveState.all_void().distance(CognitiveState.all_yin()) == 9


class TestStateNeighbors:
    def test_void_neighbors(self):
        s = CognitiveState.all_void()
        neighbors = s.neighbors()
        assert len(neighbors) == 18  # 9 dims x 2 directions

    def test_yin_neighbors(self):
        s = CognitiveState.all_yin()
        neighbors = s.neighbors()
        assert len(neighbors) == 9  # can only go toward 0

    def test_yang_neighbors(self):
        s = CognitiveState.all_yang()
        neighbors = s.neighbors()
        assert len(neighbors) == 9  # can only go toward 0


class TestStateProperties:
    def test_polarity(self):
        assert CognitiveState.all_yin().polarity == -9
        assert CognitiveState.all_void().polarity == 0
        assert CognitiveState.all_yang().polarity == 9

    def test_intensity(self):
        assert CognitiveState.all_yin().intensity == 9
        assert CognitiveState.all_void().intensity == 0

    def test_counts(self):
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        assert s.yang_count == 3
        assert s.void_count == 3
        assert s.yin_count == 3


class TestCognitiveSpace:
    def test_create_space(self, default_dims):
        space = CognitiveSpace(default_dims)
        assert len(space) == 19683

    def test_path_same_state(self, default_dims):
        space = CognitiveSpace(default_dims)
        s = CognitiveState.all_void()
        path = space.path(s, s)
        assert len(path) == 1

    def test_path_extremes(self, default_dims):
        space = CognitiveSpace(default_dims)
        path = space.path(CognitiveState.all_yin(), CognitiveState.all_yang())
        assert len(path) == 19  # 18 steps + source

    def test_path_through_void(self, default_dims):
        space = CognitiveSpace(default_dims)
        path = space.path_through_void(
            CognitiveState.all_yin(), CognitiveState.all_yang()
        )
        assert CognitiveState.all_void() in path

    def test_describe_state(self, default_dims):
        space = CognitiveSpace(default_dims)
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        desc = space.describe_state(s)
        assert "State #" in desc
        assert "past" in desc
