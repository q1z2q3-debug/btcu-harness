"""Tests for the benchmark suite."""
import pytest

from btcu_harness.benchmark.scenarios import SCENARIOS, get_scenario, list_scenarios
from btcu_harness.benchmark.runner import BenchmarkRunner


class TestScenarios:
    def test_scenario_list(self):
        names = list_scenarios()
        assert "investment" in names
        assert "technology" in names
        assert "career" in names
        assert len(names) == 3

    def test_get_scenario(self):
        s = get_scenario("investment")
        assert s.name == "Investment Decision"
        assert len(s.inputs) == 10
        assert len(s.conflict_pairs) == 2

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown scenario"):
            get_scenario("nonexistent")


class TestBenchmarkRunner:
    def test_run_btcu(self):
        runner = BenchmarkRunner(seed=42)
        result = runner.run_btcu("investment")

        assert result.agent_name == "btcu"
        assert result.scenario_name == "investment"
        assert result.total_inputs == 10
        assert result.total_llm_calls == 20  # 10 inputs × 2 (projection + advise in school stage)
        assert result.trajectory_length == 10
        assert result.unique_states > 0
        assert result.consistency_score >= 0.0
        assert result.consistency_score <= 1.0

    def test_run_baseline(self):
        runner = BenchmarkRunner(seed=42)
        result = runner.run_baseline("investment")

        assert result.agent_name == "baseline"
        assert result.scenario_name == "investment"
        assert result.total_inputs == 10
        assert result.total_llm_calls == 10
        assert result.unique_states == 0  # baseline has no state tracking
        assert result.third_choice_quality == 0.0

    def test_compare(self):
        runner = BenchmarkRunner(seed=42)
        runner.run_btcu("technology")
        runner.run_baseline("technology")

        comp = runner.compare("technology")
        assert "scenario" in comp
        assert comp["scenario"] == "technology"
        assert comp["llm_calls"]["btcu"] == 20  # 10 inputs × 2 calls each in school stage
        assert comp["llm_calls"]["baseline"] == 10
        assert comp["unique_states"]["btcu"] > 0
        assert comp["unique_states"]["baseline"] == 0

    def test_summary(self):
        runner = BenchmarkRunner(seed=42)
        runner.run_btcu("career")
        runner.run_baseline("career")

        summary = runner.summary()
        assert "BTCU Harness Benchmark Results" in summary
        assert "career" in summary

    def test_run_all(self):
        runner = BenchmarkRunner(seed=42)
        results = runner.run_all()

        assert len(results) == 6  # 3 scenarios × 2 agents
        btcu_results = [r for r in results if r.agent_name == "btcu"]
        assert len(btcu_results) == 3


class TestBenchmarkReport:
    def test_to_dict(self):
        runner = BenchmarkRunner(seed=42)
        runner.run_btcu("investment")
        runner.run_baseline("investment")

        from btcu_harness.benchmark.report import BenchmarkReport
        report = BenchmarkReport(runner.results)
        data = report.to_dict()
        assert "results" in data
        assert len(data["results"]) == 2

    def test_summary(self):
        runner = BenchmarkRunner(seed=42)
        runner.run_btcu("investment")
        runner.run_baseline("investment")

        from btcu_harness.benchmark.report import BenchmarkReport
        report = BenchmarkReport(runner.results)
        md = report.summary()
        assert "BTCU Harness Benchmark Report" in md
        assert "investment" in md
