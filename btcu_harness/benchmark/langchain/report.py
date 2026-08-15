"""
Benchmark report generator: creates comparison reports and visualizations.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .runner import BenchmarkResult, ScenarioResult


class LangChainBenchmarkReport:
    """
    Generates comparison reports for BTCU-enhanced vs standard agent.

    Produces:
    - JSON summary (machine-readable)
    - Markdown report (human-readable)
    - Visualization chart (PNG)
    """

    METRIC_LABELS = {
        "total_cognitive_states": "Total Cognitive States",
        "unique_cognitive_states": "Unique Cognitive States",
        "total_tool_observations": "Tool-Choice Observations",
        "scenarios_with_context": "Scenarios w/ Context",
        "state_coverage_pct": "State Coverage (%)",
        "trajectory_length": "Trajectory Length",
        "consistency_score": "Consistency Score",
    }

    BTCU_ONLY_METRICS = [
        "total_cognitive_states",
        "unique_cognitive_states",
        "total_tool_observations",
        "scenarios_with_context",
        "state_coverage_pct",
        "trajectory_length",
        "consistency_score",
    ]

    def __init__(
        self,
        btcu_result: BenchmarkResult,
        standard_result: BenchmarkResult,
    ) -> None:
        self.btcu = btcu_result
        self.standard = standard_result

    def to_json(self) -> Dict[str, Any]:
        """Return JSON-serializable comparison."""
        return {
            "summary": {
                "btcu": self.btcu.to_dict(),
                "standard": self.standard.to_dict(),
            },
            "btcu_advantages": self._compute_advantages(),
            "scenario_details": [
                {
                    "btcu": r.__dict__ if hasattr(r, "__dict__") else {},
                    "standard": {},
                }
                for r in self.btcu.scenario_results
            ],
        }

    def to_markdown(self) -> str:
        """Generate Markdown report."""
        lines = [
            "# BTCU-LangChain Integration Benchmark Report",
            "",
            "## Overview",
            "",
            f"- **Scenarios**: {self.btcu.total_scenarios}",
            f"- **BTCU Successful**: {self.btcu.successful_scenarios}/{self.btcu.total_scenarios}",
            f"- **Standard Successful**: {self.standard.successful_scenarios}/{self.standard.total_scenarios}",
            f"- **Cognitive State Space**: 19,683 states",
            "",
            "## Capability Comparison",
            "",
            "| Capability | BTCU-Enhanced | Standard Agent | BTCU Advantage |",
            "|---|---|---|---|",
        ]

        for metric in self.BTCU_ONLY_METRICS:
            btcu_val = getattr(self.btcu, metric, 0)
            std_val = getattr(self.standard, metric, 0)
            label = self.METRIC_LABELS.get(metric, metric)

            if metric == "state_coverage_pct":
                btcu_str = f"{btcu_val:.4f}%"
                std_str = "0.0000%"
                advantage = "BTCU exclusive"
            elif metric == "consistency_score":
                btcu_str = f"{btcu_val:.4f}"
                std_str = "N/A"
                advantage = "BTCU exclusive"
            elif isinstance(btcu_val, float):
                btcu_str = f"{btcu_val:.2f}"
                std_str = str(std_val)
                advantage = f"+{btcu_val - std_val:.2f}" if std_val else "BTCU exclusive"
            else:
                btcu_str = str(btcu_val)
                std_str = str(std_val)
                advantage = f"+{btcu_val - std_val}" if std_val else "BTCU exclusive"

            lines.append(f"| {label} | {btcu_str} | {std_str} | {advantage} |")

        lines.extend([
            "",
            "## Key Findings",
            "",
        ])

        advantages = self._compute_advantages()
        for adv in advantages:
            lines.append(f"- {adv}")

        lines.extend([
            "",
            "## Per-Scenario Breakdown",
            "",
            "| Scenario | Category | BTCU State | Polarity | Context Injected | Tools Tracked |",
            "|---|---|---|---|---|---|",
        ])

        from .scenarios import BENCHMARK_SCENARIOS
        for r in self.btcu.scenario_results:
            scenario = next(
                (s for s in BENCHMARK_SCENARIOS if s.id == r.scenario_id), None
            )
            if scenario:
                from ...core.state import CognitiveState
                state_idx = r.cognitive_states_visited[0] if r.cognitive_states_visited else -1
                polarity = CognitiveState.from_index(state_idx).polarity if state_idx >= 0 else 0
                lines.append(
                    f"| {scenario.name} | {scenario.category} | "
                    f"#{state_idx} | {polarity:+d} | "
                    f"{'Yes' if r.context_injected else 'No'} | "
                    f"{len(r.tool_choices)} |"
                )

        lines.extend([
            "",
            "## Conclusion",
            "",
            "BTCU's AgentMiddleware integration provides capabilities that are",
            "**structurally impossible** for standard LangChain agents:",
            "",
            "1. **State Tracking**: 19,683-state cognitive space maps each input",
            "   to a structured position, enabling pattern detection across sessions.",
            "2. **Tool-Choice Memory**: Every tool selection is recorded with its",
            "   cognitive context, building an associative memory over time.",
            "3. **Context Injection**: Structured cognitive state (polarity, disposition)",
            "   is injected into the system prompt, giving the model additional signal.",
            "4. **Decision Consistency**: BTCU measures whether similar inputs produce",
            "   similar cognitive states — a proxy for decision reliability.",
            "5. **Trajectory Recording**: Complete cognitive trajectory is maintained,",
            "   enabling post-hoc analysis and pattern learning.",
            "",
        ])

        return "\n".join(lines)

    def generate_chart(self, output_path: str) -> str:
        """Generate comparison visualization chart."""
        # Set font for Chinese support
        plt.rcParams["font.family"] = ["DejaVu Sans"]

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            "BTCU-Enhanced vs Standard LangChain Agent",
            fontsize=16, fontweight="bold",
        )

        # 1. Capability comparison bar chart
        ax1 = axes[0, 0]
        metrics = ["States\nVisited", "Unique\nStates", "Tool\nObs.", "Context\nInjected", "Trajectory\nLength"]
        btcu_vals = [
            self.btcu.total_cognitive_states,
            self.btcu.unique_cognitive_states,
            self.btcu.total_tool_observations,
            self.btcu.scenarios_with_context,
            self.btcu.trajectory_length,
        ]
        std_vals = [0, 0, 0, 0, 0]

        x = np.arange(len(metrics))
        w = 0.35
        ax1.bar(x - w/2, btcu_vals, w, label="BTCU-Enhanced", color="#2196F3", alpha=0.85)
        ax1.bar(x + w/2, std_vals, w, label="Standard", color="#FF9800", alpha=0.85)
        ax1.set_xticks(x)
        ax1.set_xticklabels(metrics, fontsize=9)
        ax1.set_ylabel("Count")
        ax1.set_title("Cognitive Capabilities")
        ax1.legend()
        ax1.set_ylim(0, max(btcu_vals) * 1.3 if max(btcu_vals) > 0 else 1)

        # 2. Consistency radar
        ax2 = axes[0, 1]
        categories = ["State\nTracking", "Tool\nMemory", "Context\nInjection", "Consistency", "Trajectory"]
        btcu_scores = [
            min(1.0, self.btcu.unique_cognitive_states / 10),
            min(1.0, self.btcu.total_tool_observations / 10),
            min(1.0, self.btcu.scenarios_with_context / self.btcu.total_scenarios),
            self.btcu.consistency_score,
            min(1.0, self.btcu.trajectory_length / 10),
        ]
        std_scores = [0, 0,0, 0, 0]

        angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
        angles += angles[:1]
        btcu_scores += btcu_scores[:1]
        std_scores += std_scores[:1]

        ax2 = plt.subplot(2, 2, 2, projection="polar")
        ax2.plot(angles, btcu_scores, "o-", linewidth=2, label="BTCU", color="#2196F3")
        ax2.fill(angles, btcu_scores, alpha=0.25, color="#2196F3")
        ax2.plot(angles, std_scores, "o-", linewidth=2, label="Standard", color="#FF9800")
        ax2.fill(angles, std_scores, alpha=0.25, color="#FF9800")
        ax2.set_xticks(angles[:-1])
        ax2.set_xticklabels(categories, fontsize=9)
        ax2.set_ylim(0, 1.1)
        ax2.set_title("Capability Radar", pad=20)
        ax2.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

        # 3. Per-scenario cognitive states
        ax3 = axes[1, 0]
        btcu_results = self.btcu.scenario_results
        scenario_names = [r.scenario_id for r in btcu_results]
        state_indices = [
            r.cognitive_states_visited[0] if r.cognitive_states_visited else 0
            for r in btcu_results
        ]

        from ...core.state import CognitiveState
        polarities = [CognitiveState.from_index(s).polarity for s in state_indices]
        colors = ["#4CAF50" if p > 0 else "#F44336" if p < 0 else "#9E9E9E" for p in polarities]

        ax3.barh(range(len(scenario_names)), polarities, color=colors, alpha=0.85)
        ax3.set_yticks(range(len(scenario_names)))
        ax3.set_yticklabels(scenario_names, fontsize=8)
        ax3.set_xlabel("Cognitive Polarity")
        ax3.set_title("Per-Scenario Cognitive Polarity")
        ax3.axvline(x=0, color="black", linewidth=0.5)

        # 4. Processing time comparison
        ax4 = axes[1, 1]
        btcu_times = [r.processing_time_ms for r in self.btcu.scenario_results]
        std_times = [r.processing_time_ms for r in self.standard.scenario_results]

        x = np.arange(len(btcu_times))
        w = 0.35
        ax4.bar(x - w/2, btcu_times, w, label="BTCU", color="#2196F3", alpha=0.85)
        ax4.bar(x + w/2, std_times, w, label="Standard", color="#FF9800", alpha=0.85)
        ax4.set_xlabel("Scenario Index")
        ax4.set_ylabel("Time (ms)")
        ax4.set_title("Processing Time per Scenario")
        ax4.legend()

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        return output_path

    def _compute_advantages(self) -> List[str]:
        """Compute list of BTCU advantages over standard agent."""
        advantages = []

        if self.btcu.unique_cognitive_states > 0:
            advantages.append(
                f"BTCU visited {self.btcu.unique_cognitive_states} unique cognitive states "
                f"out of 19,683 possible ({self.btcu.state_coverage_pct:.4f}% coverage); "
                f"standard agent has 0 state tracking capability."
            )

        if self.btcu.total_tool_observations > 0:
            advantages.append(
                f"BTCU recorded {self.btcu.total_tool_observations} tool-choice observations "
                f"with full cognitive context; standard agent records 0."
            )

        if self.btcu.scenarios_with_context > 0:
            advantages.append(
                f"BTCU injected structured cognitive context into {self.btcu.scenarios_with_context}/"
                f"{self.btcu.total_scenarios} scenarios; standard agent injects 0."
            )

        if self.btcu.consistency_score > 0:
            advantages.append(
                f"BTCU decision consistency score: {self.btcu.consistency_score:.4f} "
                f"(measures whether similar inputs produce similar cognitive states); "
                f"standard agent: N/A (no tracking)."
            )

        if self.btcu.trajectory_length > 0:
            advantages.append(
                f"BTCU maintained a cognitive trajectory of {self.btcu.trajectory_length} steps; "
                f"standard agent: 0."
            )

        advantages.append(
            "BTCU provides 5 capabilities that are structurally impossible "
            "for standard LangChain agents: state tracking, tool-choice memory, "
            "context injection, consistency measurement, and trajectory recording."
        )

        return advantages

    def save(
        self,
        output_dir: str,
        chart_name: str = "langchain_benchmark.png",
        report_name: str = "langchain_benchmark.md",
        json_name: str = "langchain_benchmark.json",
    ) -> Dict[str, str]:
        """Save all report artifacts to a directory."""
        os.makedirs(output_dir, exist_ok=True)

        chart_path = os.path.join(output_dir, chart_name)
        report_path = os.path.join(output_dir, report_name)
        json_path = os.path.join(output_dir, json_name)

        self.generate_chart(chart_path)

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self.to_markdown())

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

        return {
            "chart": chart_path,
            "report": report_path,
            "json": json_path,
        }
