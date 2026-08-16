"""Tests for token economy simulator."""
import pytest

from btcu_harness.benchmark.token_economy import (
    TokenEconomySimulator,
    StepSnapshot,
    SimulationResult,
    _generate_inputs,
    _mock_llm,
)


class TestHelpers:
    def test_generate_inputs_count(self):
        inputs = _generate_inputs(100)
        assert len(inputs) == 100
        assert all(isinstance(i, str) for i in inputs)

    def test_generate_inputs_unique(self):
        inputs = _generate_inputs(50)
        assert len(set(inputs)) == 50  # all unique due to [query-N] suffix

    def test_mock_llm_returns_json(self):
        result = _mock_llm("test prompt")
        assert "assessments" in result
        assert len(result) > 0

    def test_mock_llm_varies(self):
        r1 = _mock_llm("prompt A")
        r2 = _mock_llm("prompt B")
        assert r1 != r2


class TestSimulator:
    def test_init(self):
        sim = TokenEconomySimulator(total_steps=100, snapshot_interval=10)
        assert sim.total_steps == 100
        assert sim.snapshot_interval == 10

    def test_run_small(self):
        sim = TokenEconomySimulator(total_steps=50, snapshot_interval=25)
        result = sim.run()

        assert isinstance(result, SimulationResult)
        assert result.total_steps == 50
        assert len(result.snapshots) == 2  # step 25 and 50

        # Check snapshots exist
        assert result.snapshots[0].step == 25
        assert result.snapshots[1].step == 50

    def test_stages_progression(self):
        sim = TokenEconomySimulator(total_steps=100, snapshot_interval=20)
        result = sim.run()

        stages = [s.stage for s in result.snapshots]
        # First half should be school/internalize, second half graduate
        assert "school" in stages
        assert "graduate" in stages

    def test_llm_calls_increase_in_school(self):
        sim = TokenEconomySimulator(total_steps=100, snapshot_interval=20)
        result = sim.run()

        school_snapshots = [s for s in result.snapshots if s.stage == "school"]
        if len(school_snapshots) >= 2:
            # LLM calls should increase in school stage
            assert school_snapshots[0].llm_calls > 0
            assert school_snapshots[-1].llm_calls >= school_snapshots[0].llm_calls

    def test_patterns_learned(self):
        sim = TokenEconomySimulator(total_steps=100, snapshot_interval=25)
        result = sim.run()

        # Should learn some patterns
        assert result.final_patterns > 0

    def test_reuse_rate_growth(self):
        sim = TokenEconomySimulator(total_steps=200, snapshot_interval=50)
        result = sim.run()

        # Reuse rate should increase over time
        rates = [s.reuse_rate for s in result.snapshots]
        if len(rates) >= 3:
            assert rates[-1] >= rates[0]  # final >= initial

    def test_summary(self):
        sim = TokenEconomySimulator(total_steps=50, snapshot_interval=25)
        sim.run()
        summary = sim.summary()

        assert "BTCU Token Economy Simulation" in summary
        assert "Total steps: 50" in summary

    def test_save_json(self, tmp_path):
        sim = TokenEconomySimulator(total_steps=50, snapshot_interval=25)
        sim.run()

        path = str(tmp_path / "test_token.json")
        sim.save_json(path)

        import json
        with open(path) as f:
            data = json.load(f)

        assert "total_steps" in data
        assert "final" in data
        assert "snapshots" in data
        assert len(data["snapshots"]) == 2

    def test_metadata(self):
        sim = TokenEconomySimulator(total_steps=100, snapshot_interval=20)
        result = sim.run()
        assert "total_steps" in result.metadata
        assert "stage_splits" in result.metadata
