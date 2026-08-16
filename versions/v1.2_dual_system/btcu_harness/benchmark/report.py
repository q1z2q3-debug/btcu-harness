"""Benchmark report generator with HTML output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from .runner import BenchmarkResult


@dataclass
class BenchmarkReport:
    """Generates formatted benchmark reports."""

    results: List[BenchmarkResult]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "results": [
                {
                    "scenario": r.scenario_name,
                    "agent": r.agent_name,
                    "inputs": r.total_inputs,
                    "llm_calls": r.total_llm_calls,
                    "third_choices": r.total_third_choices,
                    "unique_states": r.unique_states,
                    "trajectory_length": r.trajectory_length,
                    "coverage_pct": r.state_coverage_pct,
                    "avg_polarity": r.avg_polarity,
                    "consistency": r.consistency_score,
                    "third_choice_quality": r.third_choice_quality,
                    "processing_time_ms": r.avg_processing_time_ms,
                }
                for r in self.results
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Generate markdown summary."""
        lines = [
            "# BTCU Harness Benchmark Report",
            "",
            "| Scenario | Agent | Inputs | LLM Calls | Unique States | Coverage% | Consistency | 3C Quality |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in self.results:
            lines.append(
                f"| {r.scenario_name} | {r.agent_name} | "
                f"{r.total_inputs} | {r.total_llm_calls} | "
                f"{r.unique_states} | {r.state_coverage_pct:.4f} | "
                f"{r.consistency_score:.2f} | {r.third_choice_quality:.2f} |"
            )
        return "\n".join(lines)

    def save(self, path: str) -> str:
        """Save JSON report to disk."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return path
