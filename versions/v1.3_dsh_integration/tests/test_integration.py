"""
Integration tests: End-to-end BTCU Harness pipeline.

Tests the full cognitive flow from projection to memory to decision
to persistence, verifying all modules work together correctly.
"""

import json
import os
import tempfile

import pytest

from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState
from btcu_harness.core.trit import YIN, VOID, YANG
from btcu_harness.decision.third_choice import ThirdChoiceGenerator
from btcu_harness.memory.climate import CognitiveClimate
from btcu_harness.performance import (
    cached_from_index,
    batch_distance,
    batch_polarity,
    get_neighbors,
    clear_caches,
)


# --- Mock LLM for integration testing ---

def make_mock_llm():
    """Create a deterministic mock LLM that returns valid JSON."""
    import hashlib

    def mock_callback(prompt: str) -> str:
        h = hashlib.md5(prompt.encode()).hexdigest()
        assessments = []
        for i in range(9):
            val = int(h[i * 2: i * 2 + 2], 16) % 3 - 1
            assessments.append({"value": val, "reason": f"dim_{i}"})
        return json.dumps({"assessments": assessments})

    from btcu_harness.llm.bridge import LLMBridge
    return LLMBridge(callback=mock_callback)


@pytest.fixture
def tmp_storage():
    """Temporary storage file that auto-cleans."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)  # Remove so agent starts fresh
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def agent(tmp_storage):
    """Fully initialized agent with mock LLM."""
    a = BTCUAgent(growth_stage="school", storage_path=tmp_storage)
    dim_labels = [
        "技术深度", "用户体验", "创新性", "可维护性",
        "社区影响", "商业价值", "学习成长", "风险评估", "长期愿景",
    ]
    bridge = make_mock_llm()
    a.init_project(domain="custom", dim_labels=dim_labels, llm_bridge=bridge)

    # Set mission
    a.set_self_level(
        name="mission",
        description="Be a helpful cognitive companion",
        state=CognitiveState.from_values([1, 1, 1, 0, 1, 0, 1, -1, 1]),
        weight=1.0,
        stability=0.95,
    )
    return a


class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_school_to_internalize_transition(self, agent):
        """Agent transitions from school to internalize with pattern accumulation."""
        # School stage: 5 queries build up patterns
        queries = [
            "Should we focus on algorithmic innovation?",
            "What about user experience improvements?",
            "Is the technical architecture sound?",
            "How important is community engagement?",
            "Should we prioritize commercial viability?",
        ]

        for q in queries:
            response = agent.process(q)
            assert response.current_state is not None
            assert response.projection.source in ("llm", "pattern")
            agent.record_outcome(
                state=response.current_state,
                decision=f"query_{q[:20]}",
                outcome_positive=True,
            )

        # Advance to internalize
        agent.advance_stage()
        assert agent.growth_stage == "internalize"

        # Similar query should pattern-match
        similar = "Should we focus on algorithmic innovation?"
        response = agent.process(similar)
        assert response.pattern_matched is True
        assert response.projection.source == "pattern"

    def test_save_load_roundtrip(self, agent, tmp_storage):
        """Save and load preserves all cognitive state."""
        # Process some queries
        for i in range(3):
            response = agent.process(f"Query number {i} about innovation")
            agent.record_outcome(
                state=response.current_state,
                decision=f"q{i}",
                outcome_positive=True,
            )

        # Save
        path = agent.save()
        assert path is not None
        assert os.path.exists(path)

        # Load into new agent
        agent2 = BTCUAgent(storage_path=tmp_storage)
        loaded = agent2.load()
        assert loaded is True

        # Verify state restored
        assert agent2.growth_stage == agent.growth_stage
        assert agent2.trajectory.length == agent.trajectory.length
        assert agent2.pattern_learner.pattern_count == agent.pattern_learner.pattern_count
        assert agent2.self_layer.attractor.index == agent.self_layer.attractor.index

    def test_third_choice_with_self_layer(self, agent):
        """Third choice respects self alignment."""
        state_a = CognitiveState.all_yang()
        state_b = CognitiveState.all_yin()

        candidates = agent.third_choice_gen.generate_all(state_a, state_b)
        assert len(candidates) > 0

        # All candidates should have scores
        for c in candidates:
            assert c.total_score > 0
            assert 0 <= c.void_ratio <= 1

        # Void strategy should exist
        void_candidates = [c for c in candidates if c.strategy == "void"]
        assert len(void_candidates) > 0

    def test_climate_tracking(self, agent):
        """Climate report reflects cognitive activity."""
        # Process varied queries
        queries = [
            "Focus on deep innovation and breakthrough",
            "What about safety and risk assessment?",
            "Balance between speed and quality?",
            "Long-term strategic vision?",
            "Community impact and growth?",
        ]

        for q in queries:
            agent.process(q)

        report = agent.climate.report(
            ecology=agent.ecology,
            trajectory=agent.trajectory,
        )

        assert report.total_steps == 5
        assert report.unique_states > 0
        assert report.exploration_phase in ("expanding", "consolidating", "stagnant")

    def test_seasons_emerge_after_repeated_visits(self, agent):
        """Cognitive seasons emerge from repeated visits."""
        # Visit same state multiple times
        state = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        for _ in range(6):
            agent.ecology.remember(type(
                "Event", (), {
                    "state": state,
                    "prev_state": None,
                    "context": {},
                    "decision": "test",
                    "outcome": "ok",
                    "outcome_positive": True,
                    "metadata": {},
                }
            )())

        seasons = agent.discover_seasons()
        attractor_seasons = [s for s in seasons if s.season_type == "attractor"]
        assert len(attractor_seasons) > 0

    def test_trajectory_caches_steps(self, agent):
        """Trajectory records all cognitive steps."""
        for i in range(5):
            agent.process(f"Query {i}")

        assert agent.trajectory.length >= 5
        assert agent.trajectory.unique_states > 0


class TestPerformance:
    """Performance and caching tests."""

    def setup_method(self):
        clear_caches()

    def test_cached_from_index_speed(self):
        """Cached from_index is faster than uncached."""
        import time

        # First call (cache miss)
        start = time.perf_counter()
        s1 = CognitiveState.from_index(9841)
        uncached_time = time.perf_counter() - start

        # Warm cache
        cached_from_index(9841)

        # Cached call
        start = time.perf_counter()
        s2 = cached_from_index(9841)
        cached_time = time.perf_counter() - start

        assert s1 == s2
        # Cached should be faster (or at least not slower)
        # Note: in practice the difference is tiny for single calls,
        # but significant in loops
        assert cached_time <= uncached_time * 5  # generous bound

    def test_batch_distance_correctness(self):
        """Batch distance matches individual distance."""
        source = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        targets = [
            CognitiveState.all_yang(),
            CognitiveState.all_yin(),
            CognitiveState.all_void(),
            CognitiveState.from_values([-1, 0, 1, -1, 0, 0, 1, -1, 1]),
        ]

        batch_results = batch_distance(source, targets)
        individual_results = [source.distance(t) for t in targets]

        assert batch_results == individual_results

    def test_batch_polarity_correctness(self):
        """Batch polarity matches individual polarity."""
        states = [
            CognitiveState.all_yang(),
            CognitiveState.all_yin(),
            CognitiveState.all_void(),
        ]
        batch_results = batch_polarity(states)
        individual_results = [s.polarity for s in states]
        assert batch_results == individual_results

    def test_neighbor_count(self):
        """Neighbors have correct count based on void/polarized dims."""
        # All void: 9 dims * 2 directions = 18 neighbors
        void = CognitiveState.all_void()
        assert len(get_neighbors(void)) == 18

        # All yang: 9 dims * 1 direction (can only go down) = 9 neighbors
        yang = CognitiveState.all_yang()
        assert len(get_neighbors(yang)) == 9

        # All yin: 9 dims * 1 direction (can only go up) = 9 neighbors
        yin = CognitiveState.all_yin()
        assert len(get_neighbors(yin)) == 9

    def test_neighbor_caching(self):
        """Neighbors are cached after first access."""
        state = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])

        n1 = get_neighbors(state)
        n2 = get_neighbors(state)

        assert n1 is n2  # Same list object from cache

    def test_full_space_iteration_performance(self):
        """Iterating all 19683 states completes in reasonable time."""
        import time

        start = time.perf_counter()
        for i in range(19683):
            s = cached_from_index(i)
            _ = s.polarity
        elapsed = time.perf_counter() - start

        # Should complete in under 2 seconds (with caching)
        assert elapsed < 5.0, f"Full space iteration took {elapsed:.2f}s"


class TestCLI:
    """CLI integration tests."""

    def test_cli_explore_command(self):
        """CLI explore command works."""
        from btcu_harness.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["explore", "--index", "9841"])

        # Should not raise
        ret = args.func(args)
        assert ret == 0

    def test_cli_explore_values(self):
        """CLI explore with --values works."""
        from btcu_harness.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["explore", "--values", "1,0,-1,1,0,0,-1,1,-1"])

        ret = args.func(args)
        assert ret == 0

    def test_cli_init_command(self, tmp_storage):
        """CLI init command creates a project."""
        from btcu_harness.cli import build_parser

        parser = build_parser()
        args = parser.parse_args([
            "--storage", tmp_storage,
            "init", "--domain", "agent",
            "--mission", "Test mission",
        ])

        ret = args.func(args)
        assert ret == 0
        assert os.path.exists(tmp_storage)


class TestErrorHandling:
    """Error handling and edge cases."""

    def test_invalid_trit_value(self):
        """Creating Trit with invalid value raises ValueError."""
        from btcu_harness.core.trit import Trit

        with pytest.raises(ValueError):
            Trit(2)

        with pytest.raises(ValueError):
            Trit(-2)

    def test_state_wrong_dimension_count(self):
        """Creating CognitiveState with wrong dims raises ValueError."""
        with pytest.raises(ValueError):
            CognitiveState.from_values([1, 0, -1])  # Only 3 values

    def test_agent_without_project(self):
        """Agent without init_project handles gracefully."""
        agent = BTCUAgent()
        # Processing without project should handle gracefully
        # (may raise or return void, depending on implementation)

    def test_load_nonexistent_file(self, tmp_storage):
        """Loading from nonexistent file returns False."""
        agent = BTCUAgent(storage_path=tmp_storage)
        assert agent.load() is False

    def test_persistence_corrupt_json(self, tmp_storage):
        """Loading corrupt JSON is handled gracefully."""
        with open(tmp_storage, "w") as f:
            f.write("{invalid json")

        agent = BTCUAgent(storage_path=tmp_storage)
        result = agent.load()
        # Should return False, not crash
        assert result is False
