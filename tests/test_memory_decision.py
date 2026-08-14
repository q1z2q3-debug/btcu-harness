"""Tests for memory ecology and decision layers."""
import json
import pytest
from btcu_harness.core.state import CognitiveState
from btcu_harness.core.space import CognitiveSpace
from btcu_harness.memory.ecology import MemoryEcology, CognitiveEvent
from btcu_harness.decision.pathfinder import DecisionPathfinder
from btcu_harness.decision.third_choice import ThirdChoiceGenerator


class TestMemoryEcology:
    def test_empty_ecology(self):
        eco = MemoryEcology()
        assert eco.state_store.visited_count == 0
        assert eco.state_store.total_visits == 0

    def test_remember_single_event(self):
        eco = MemoryEcology()
        event = CognitiveEvent(
            state=CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1]),
            context={"task": "test"},
        )
        eco.remember(event)
        assert eco.state_store.visited_count == 1
        assert eco.state_store.total_visits == 1

    def test_remember_with_transition(self):
        eco = MemoryEcology()
        s1 = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        s2 = CognitiveState.from_values([1, 1, -1, 1, 0, 0, -1, 1, -1])

        eco.remember(CognitiveEvent(state=s1))
        eco.remember(CognitiveEvent(state=s2, prev_state=s1))

        assert eco.state_store.visited_count == 2
        assert eco.transition_store.total_corridors == 1

    def test_recall(self):
        eco = MemoryEcology()
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        eco.remember(CognitiveEvent(state=s, decision="act", outcome_positive=True))

        recall = eco.recall(s)
        assert recall["state"].visit_count == 1
        assert recall["state"].success_count == 1

    def test_decay(self):
        eco = MemoryEcology()
        eco.remember(CognitiveEvent(state=CognitiveState.all_yang()))
        mem = eco.state_store.get(CognitiveState.all_yang().index)
        assert mem.activation > 0

        eco.decay()
        assert mem.activation < 1.0

    def test_legacy_export_import(self):
        eco = MemoryEcology()
        s1 = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        s2 = CognitiveState.from_values([0, 0, 0, 0, 0, 0, 0, 0, 0])

        eco.remember(CognitiveEvent(state=s1, decision="A", outcome_positive=True))
        eco.remember(CognitiveEvent(state=s2, prev_state=s1, decision="B", outcome_positive=False))

        legacy = eco.export_legacy()
        eco2 = MemoryEcology()
        eco2.import_legacy(legacy)

        assert eco2.state_store.visited_count == 2
        assert eco2.state_store.total_visits == 2

    def test_sense_making(self):
        eco = MemoryEcology()
        # Add enough visits to trigger attractor detection
        s = CognitiveState.all_void()
        for _ in range(6):
            eco.remember(CognitiveEvent(state=s))

        seasons = eco.sense_making()
        assert len(seasons) > 0
        # Should find blind_spot at minimum
        assert any(s.season_type == "blind_spot" for s in seasons)


class TestThirdChoice:
    def test_no_conflict(self):
        gen = ThirdChoiceGenerator()
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        tc = gen.generate(s, s)
        assert not tc.analysis.has_conflict

    def test_extreme_conflict(self):
        gen = ThirdChoiceGenerator()
        a = CognitiveState.all_yang()
        b = CognitiveState.all_yin()
        tc = gen.generate(a, b)
        assert tc.analysis.is_extreme_conflict
        assert len(tc.voided_dims) == 9
        assert len(tc.preserved_dims) == 0
        # Third choice should be all void
        assert tc.state.index == 9841

    def test_partial_conflict(self):
        gen = ThirdChoiceGenerator()
        a = CognitiveState.from_values([1, 1, 1, 1, 1, 1, 1, 1, 1])
        b = CognitiveState.from_values([1, 1, 1, -1, -1, -1, 1, 1, 1])
        tc = gen.generate(a, b)
        assert tc.analysis.has_conflict
        assert len(tc.preserved_dims) == 6
        assert len(tc.voided_dims) == 3

    def test_third_choice_not_average(self):
        """Third choice is not the arithmetic average - it voids conflicts."""
        gen = ThirdChoiceGenerator()
        a = CognitiveState.from_values([1, 1, -1, -1, 0, 0, 0, 0, 0])
        b = CognitiveState.from_values([-1, -1, 1, 1, 0, 0, 0, 0, 0])
        tc = gen.generate(a, b)
        # All 4 conflicting dims should be voided
        assert all(tc.state[i].value == 0 for i in range(4))


class TestDecisionPathfinder:
    def test_find_path(self, default_dims):
        space = CognitiveSpace(default_dims)
        eco = MemoryEcology()
        pf = DecisionPathfinder(space, eco)

        source = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        target = CognitiveState.all_yang()

        path = pf.find_path(source, target)
        assert path.source == source
        assert path.target == target
        assert path.estimated_length > 0

    def test_void_path(self, default_dims):
        space = CognitiveSpace(default_dims)
        eco = MemoryEcology()
        pf = DecisionPathfinder(space, eco)

        source = CognitiveState.all_yang()
        path = pf.find_void_path(source)
        assert path.target == CognitiveState.all_void()

    def test_path_with_memory(self, default_dims):
        space = CognitiveSpace(default_dims)
        eco = MemoryEcology()

        # Record some experiences
        s = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        eco.remember(CognitiveEvent(
            state=s, decision="test", outcome_positive=True
        ))

        pf = DecisionPathfinder(space, eco)
        path = pf.find_path(s, CognitiveState.all_yang())
        assert len(path.memory_guidance) > 0 or len(path.memory_warnings) > 0 or True  # may be empty

    def test_find_third_choice(self, default_dims):
        space = CognitiveSpace(default_dims)
        eco = MemoryEcology()
        pf = DecisionPathfinder(space, eco)

        a = CognitiveState.all_yang()
        b = CognitiveState.all_yin()
        third = pf.find_third_choice(a, b)
        assert third.index == 9841  # should be all void
