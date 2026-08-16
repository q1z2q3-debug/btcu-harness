"""Token economy simulation for BTCU Harness benchmark suite.

Simulates LLM cost reduction as BTCU learns patterns across cognitive inputs.

Metrics tracked every N steps:
    - llm_calls: Cumulative LLM invocations
    - pattern_count: Total patterns learned
    - reuse_rate: Successful pattern matches / total lookups
    - unique_states: Distinct cognitive states visited
    - llm_calls_per_batch: LLM calls in this batch window
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from btcu_harness.agent import BTCUAgent
from btcu_harness.llm.bridge import LLMBridge


def _mock_llm(prompt: str) -> str:
    """Simulate an LLM that returns varied dimension assessments."""
    import hashlib

    h = hashlib.md5(prompt.encode()).hexdigest()
    assessments = []
    for i in range(9):
        v = (int(h[i * 2 : i * 2 + 2], 16) % 3) - 1
        assessments.append(
            {
                "dimension": f"d{i}",
                "value": v,
                "reason": f"sim-reason-{i}",
            }
        )
    return json.dumps({"assessments": assessments})


def _generate_inputs(count: int) -> List[str]:
    """Generate varied test inputs with some repetition for pattern learning."""
    base_inputs = [
        "Should I invest in high-growth tech?",
        "Is it safe to buy bonds now?",
        "Should we migrate to microservices?",
        "Is serverless the right choice?",
        "Should I switch to management?",
        "Is remote work sustainable?",
        "Should we adopt GraphQL?",
        "Is this the right time to buy gold?",
        "Should I go back to school?",
        "Is dollar-cost averaging good?",
    ]
    # Add variations for pattern learning
    variations = [
        "Invest in high-growth technology companies?",
        "Buy technology stocks for growth?",
        "Is bond investment safe currently?",
        "Government bonds as safe investment?",
        "Migrate our system to microservices?",
        "Should we break monolith into services?",
        "Serverless architecture adoption?",
        "Use serverless functions for backend?",
        "Move into management role?",
        "Technical leadership vs management?",
        "Remote work long term viability?",
        "Work from home career impact?",
        "Switch API to GraphQL?",
        "GraphQL vs REST for new project?",
        "Gold investment timing now?",
        "Buy physical gold or ETFs?",
        "Return to university for degree?",
        "MBA or technical certification?",
        "DCA strategy effectiveness?",
        "Systematic monthly investing?",
    ]
    all_inputs = base_inputs + variations
    # Repeat with noise to create learnable patterns
    result = []
    for i in range(count):
        idx = i % len(all_inputs)
        base = all_inputs[idx]
        # Add slight variation for uniqueness
        result.append(f"{base} [query-{i}]")
    return result


@dataclass
class StepSnapshot:
    """Snapshot of metrics at a given step."""

    step: int
    stage: str  # school / internalize / graduate
    llm_calls: int
    pattern_count: int
    total_lookups: int
    total_reuses: int
    reuse_rate: float
    unique_states: int
    llm_calls_this_batch: int


@dataclass
class SimulationResult:
    """Complete simulation results."""

    total_steps: int
    snapshots: List[StepSnapshot] = field(default_factory=list)
    final_llm_calls: int = 0
    final_patterns: int = 0
    final_reuse_rate: float = 0.0
    final_unique_states: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class TokenEconomySimulator:
    """Simulate BTCU's token economy over many inputs."""

    def __init__(self, total_steps: int = 1000, snapshot_interval: int = 50) -> None:
        self.total_steps = total_steps
        self.snapshot_interval = snapshot_interval
        self.result = SimulationResult(total_steps=total_steps)

    def run(self) -> SimulationResult:
        """Run the full simulation."""
        # Initialize agent
        agent = BTCUAgent(growth_stage="school")
        agent.init_project(
            domain="custom",
            dim_labels=[
                "Speed",
                "Quality",
                "Cost",
                "Risk",
                "Innovation",
                "Team",
                "Deadline",
                "Scope",
                "Impact",
            ],
        )
        agent.llm_bridge = LLMBridge(callback=_mock_llm)

        # Generate inputs
        inputs = _generate_inputs(self.total_steps)

        # Track metrics
        prev_llm_calls = 0
        prev_lookups = 0
        prev_reuses = 0

        for step, inp in enumerate(inputs):
            # Determine stage
            if step < self.total_steps * 0.2:
                stage = "school"
                if agent.growth_stage != "school":
                    agent.growth_stage = "school"
                    if agent.projector:
                        agent.projector.set_growth_stage("school")
            elif step < self.total_steps * 0.6:
                stage = "internalize"
                if agent.growth_stage != "internalize":
                    agent.growth_stage = "internalize"
                    if agent.projector:
                        agent.projector.set_growth_stage("internalize")
            else:
                stage = "graduate"
                if agent.growth_stage != "graduate":
                    agent.growth_stage = "graduate"
                    if agent.projector:
                        agent.projector.set_growth_stage("graduate")

            # Process input
            try:
                agent.process(inp)
            except Exception:
                # Some inputs may fail in school stage without proper LLM
                pass

            # Snapshot every N steps
            if (step + 1) % self.snapshot_interval == 0:
                pl = agent.pattern_learner
                llm_total = agent.llm_bridge.total_calls if agent.llm_bridge else 0
                lookups = pl.pattern_count if hasattr(pl, "pattern_count") else 0
                reuses = pl.total_reuses if hasattr(pl, "total_reuses") else 0

                snapshot = StepSnapshot(
                    step=step + 1,
                    stage=stage,
                    llm_calls=llm_total,
                    pattern_count=pl.pattern_count if hasattr(pl, "pattern_count") else 0,
                    total_lookups=lookups,
                    total_reuses=reuses,
                    reuse_rate=pl.reuse_rate if hasattr(pl, "reuse_rate") else 0.0,
                    unique_states=len(
                        set(
                            p.state_index
                            for p in (pl.patterns if hasattr(pl, "patterns") else [])
                        )
                    ),
                    llm_calls_this_batch=llm_total - prev_llm_calls,
                )
                self.result.snapshots.append(snapshot)
                prev_llm_calls = llm_total
                prev_lookups = lookups
                prev_reuses = reuses

        # Final metrics
        pl = agent.pattern_learner
        self.result.final_llm_calls = (
            agent.llm_bridge.total_calls if agent.llm_bridge else 0
        )
        self.result.final_patterns = (
            pl.pattern_count if hasattr(pl, "pattern_count") else 0
        )
        self.result.final_reuse_rate = (
            pl.reuse_rate if hasattr(pl, "reuse_rate") else 0.0
        )
        self.result.final_unique_states = len(
            set(
                p.state_index
                for p in (pl.patterns if hasattr(pl, "patterns") else [])
            )
        )
        self.result.metadata = {
            "total_steps": self.total_steps,
            "snapshot_interval": self.snapshot_interval,
            "stage_splits": {"school": 0.2, "internalize": 0.4, "graduate": 0.4},
        }

        return self.result

    def summary(self) -> str:
        """Generate human-readable summary."""
        if not self.result.snapshots:
            return "No simulation data. Run .run() first."

        lines = [
            "=" * 60,
            "BTCU Token Economy Simulation",
            "=" * 60,
            f"Total steps: {self.result.total_steps}",
            f"Final LLM calls: {self.result.final_llm_calls}",
            f"Final patterns: {self.result.final_patterns}",
            f"Final reuse rate: {self.result.final_reuse_rate:.1%}",
            f"Final unique states: {self.result.final_unique_states}",
            "",
            "Step-by-step:",
            f"{'Step':>6} {'Stage':>12} {'LLM':>6} {'Patns':>6} {'Reuse%':>8} {'States':>6}",
            "-" * 44,
        ]
        for s in self.result.snapshots:
            lines.append(
                f"{s.step:>6} {s.stage:>12} {s.llm_calls:>6} "
                f"{s.pattern_count:>6} {s.reuse_rate:>7.1%} {s.unique_states:>6}"
            )
        lines.append("=" * 60)
        return "\n".join(lines)

    def save_json(self, path: str) -> str:
        """Save results to JSON."""
        data = {
            "total_steps": self.result.total_steps,
            "final": {
                "llm_calls": self.result.final_llm_calls,
                "patterns": self.result.final_patterns,
                "reuse_rate": self.result.final_reuse_rate,
                "unique_states": self.result.final_unique_states,
            },
            "snapshots": [
                {
                    "step": s.step,
                    "stage": s.stage,
                    "llm_calls": s.llm_calls,
                    "pattern_count": s.pattern_count,
                    "total_lookups": s.total_lookups,
                    "total_reuses": s.total_reuses,
                    "reuse_rate": s.reuse_rate,
                    "unique_states": s.unique_states,
                    "llm_calls_this_batch": s.llm_calls_this_batch,
                }
                for s in self.result.snapshots
            ],
            "metadata": self.result.metadata,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path
