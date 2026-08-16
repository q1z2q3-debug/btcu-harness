"""Benchmark runner: executes scenarios and collects metrics."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..agent import BTCUAgent
from ..core.state import CognitiveState
from ..llm.bridge import LLMBridge
from .scenarios import BenchmarkScenario, SCENARIOS, get_scenario


def _mock_llm_callback(scenario_name: str) -> Callable[[str], str]:
    """Create a deterministic mock LLM that produces varied states per input."""
    def cb(prompt: str) -> str:
        assessments = []
        # Use hash of prompt to create variation across inputs
        prompt_hash = hash(prompt) % 10000
        for i in range(9):
            # Mix scenario bias + prompt variation + dimension offset
            base = hash(f"{scenario_name}:{i}") % 3
            variation = (prompt_hash + i * 7) % 3
            value = [-1, 0, 1][(base + variation) % 3]
            assessments.append({
                "dimension": f"d{i}",
                "value": value,
                "reason": f"benchmark-reason-{i}",
            })
        return json.dumps({"assessments": assessments})
    return cb


@dataclass
class BenchmarkResult:
    """Results for a single scenario run."""

    scenario_name: str
    agent_name: str  # "btcu" or "baseline"

    # Execution metrics
    total_inputs: int = 0
    total_llm_calls: int = 0
    total_third_choices: int = 0
    avg_processing_time_ms: float = 0.0

    # State metrics
    unique_states: int = 0
    trajectory_length: int = 0
    state_coverage_pct: float = 0.0
    avg_polarity: float = 0.0

    # Quality metrics
    consistency_score: float = 0.0  # state stability across runs
    third_choice_quality: float = 0.0  # avg score of generated candidates
    path_efficiency: float = 0.0  # shortest / actual path length

    metadata: Dict[str, Any] = field(default_factory=dict)


class BenchmarkRunner:
    """Runs BTCU benchmark scenarios against baselines."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.results: List[BenchmarkResult] = []

    def run_btcu(
        self,
        scenario_name: str,
        dim_labels: Optional[List[str]] = None,
    ) -> BenchmarkResult:
        """Run BTCU agent on a scenario."""
        scenario = get_scenario(scenario_name)
        agent = BTCUAgent(growth_stage="school")

        labels = dim_labels or [f"dim{i}" for i in range(9)]
        agent.init_project(domain="custom", dim_labels=labels)
        agent.llm_bridge = LLMBridge(callback=_mock_llm_callback(scenario_name))

        start_time = time.perf_counter_ns()
        llm_calls_before = agent.llm_bridge.total_calls if agent.llm_bridge else 0

        # Process all inputs
        states: List[int] = []
        third_choice_total = 0
        third_choice_scores: List[float] = []

        for idx, inp in enumerate(scenario.inputs):
            response = agent.process(inp)
            states.append(response.current_state.index)

            # Generate third choices for every other input
            if idx % 2 == 0 and len(scenario.conflict_pairs) > 0:
                a_text, b_text = scenario.conflict_pairs[idx % len(scenario.conflict_pairs)]
                # Create two opposing states
                state_a = CognitiveState.from_values(
                    [1 if i < 4 else -1 for i in range(9)]
                )
                state_b = CognitiveState.from_values(
                    [-1 if i < 4 else 1 for i in range(9)]
                )
                candidates = agent.third_choice_gen.generate_all(state_a, state_b)
                third_choice_total += len(candidates)
                if candidates:
                    third_choice_scores.extend(c.total_score for c in candidates[:3])

        end_time = time.perf_counter_ns()
        llm_calls = (agent.llm_bridge.total_calls if agent.llm_bridge else 0) - llm_calls_before

        # Compute metrics
        unique = len(set(states))
        avg_polarity = sum(
            CognitiveState.from_index(i).polarity for i in states
        ) / len(states) if states else 0.0

        consistency = self._compute_consistency(states)

        result = BenchmarkResult(
            scenario_name=scenario_name,
            agent_name="btcu",
            total_inputs=len(scenario.inputs),
            total_llm_calls=llm_calls,
            total_third_choices=third_choice_total,
            avg_processing_time_ms=(end_time - start_time) / 1e6,
            unique_states=unique,
            trajectory_length=agent.trajectory.length,
            state_coverage_pct=unique / 19683 * 100,
            avg_polarity=avg_polarity,
            consistency_score=consistency,
            third_choice_quality=(
                sum(third_choice_scores) / len(third_choice_scores)
                if third_choice_scores else 0.0
            ),
            metadata={
                "seed": self.seed,
                "states": states,
            },
        )
        self.results.append(result)
        return result

    def run_baseline(
        self,
        scenario_name: str,
    ) -> BenchmarkResult:
        """Run baseline (mock unstructured) on a scenario."""
        scenario = get_scenario(scenario_name)
        callback = _mock_llm_callback(scenario_name)

        start_time = time.perf_counter_ns()
        responses: List[str] = []

        for inp in scenario.inputs:
            # Baseline: just call the mock LLM directly, no state tracking
            resp = callback(f"Analyze: {inp}")
            responses.append(resp)

        end_time = time.perf_counter_ns()

        # Baseline has no states, no trajectory, no third choice
        result = BenchmarkResult(
            scenario_name=scenario_name,
            agent_name="baseline",
            total_inputs=len(scenario.inputs),
            total_llm_calls=len(scenario.inputs),
            total_third_choices=0,
            avg_processing_time_ms=(end_time - start_time) / 1e6,
            unique_states=0,
            trajectory_length=0,
            state_coverage_pct=0.0,
            avg_polarity=0.0,
            consistency_score=0.0,
            third_choice_quality=0.0,
            metadata={"responses": responses[:3]},  # sample
        )
        self.results.append(result)
        return result

    def _compute_consistency(self, states: List[int]) -> float:
        """Measure how stable the state projections are."""
        if len(states) < 2:
            return 1.0

        # Consistency = 1 - (avg distance between consecutive states / max distance)
        total_dist = 0
        for i in range(len(states) - 1):
            a = CognitiveState.from_index(states[i])
            b = CognitiveState.from_index(states[i + 1])
            total_dist += a.distance(b)

        avg_dist = total_dist / (len(states) - 1)
        return max(0.0, 1.0 - avg_dist / 18.0)

    def run_all(self) -> List[BenchmarkResult]:
        """Run BTCU + baseline for all scenarios."""
        for name in SCENARIOS:
            print(f"Running scenario: {name}")
            self.run_btcu(name)
            self.run_baseline(name)
        return self.results

    def compare(self, scenario_name: str) -> Dict[str, Any]:
        """Compare BTCU vs baseline for a specific scenario."""
        btcu = next(
            (r for r in self.results if r.scenario_name == scenario_name and r.agent_name == "btcu"),
            None,
        )
        baseline = next(
            (r for r in self.results if r.scenario_name == scenario_name and r.agent_name == "baseline"),
            None,
        )
        if not btcu or not baseline:
            raise ValueError(f"Results not found for scenario: {scenario_name}")

        return {
            "scenario": scenario_name,
            "llm_calls": {"btcu": btcu.total_llm_calls, "baseline": baseline.total_llm_calls},
            "unique_states": {"btcu": btcu.unique_states, "baseline": baseline.unique_states},
            "state_coverage_pct": {"btcu": btcu.state_coverage_pct, "baseline": baseline.state_coverage_pct},
            "consistency": {"btcu": btcu.consistency_score, "baseline": baseline.consistency_score},
            "third_choices": {"btcu": btcu.total_third_choices, "baseline": baseline.total_third_choices},
            "third_choice_quality": {"btcu": btcu.third_choice_quality, "baseline": baseline.third_choice_quality},
            "processing_time_ms": {"btcu": btcu.avg_processing_time_ms, "baseline": baseline.avg_processing_time_ms},
        }

    def summary(self) -> str:
        """Human-readable summary of all results."""
        lines = [
            "=" * 60,
            "BTCU Harness Benchmark Results",
            "=" * 60,
        ]
        for scenario_name in SCENARIOS:
            try:
                comp = self.compare(scenario_name)
                lines.extend([
                    f"\nScenario: {scenario_name}",
                    f"  LLM calls:        BTCU={comp['llm_calls']['btcu']:2d}  vs  Baseline={comp['llm_calls']['baseline']:2d}",
                    f"  Unique states:    BTCU={comp['unique_states']['btcu']:2d}  vs  Baseline={comp['unique_states']['baseline']:2d}",
                    f"  State coverage:   BTCU={comp['state_coverage_pct']['btcu']:.4f}%  vs  Baseline=N/A",
                    f"  Consistency:      BTCU={comp['consistency']['btcu']:.2f}  vs  Baseline=N/A",
                    f"  Third choices:    BTCU={comp['third_choices']['btcu']:2d}  vs  Baseline={comp['third_choices']['baseline']:2d}",
                    f"  3C quality:       BTCU={comp['third_choice_quality']['btcu']:.2f}  vs  Baseline=N/A",
                ])
            except ValueError:
                lines.append(f"\nScenario: {scenario_name} — results not available")
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
