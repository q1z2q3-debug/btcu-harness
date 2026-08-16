"""
BTCU Agent v0.3: Upgraded with self layer, trajectory, pattern learner, persistence.

v0.3 upgrades:
- NLP Self Layer: identity/values as cognitive attractor
- Cognitive Trajectory: records cognitive path through 19683 space
- Pattern Learner: real pattern accumulation for LLM cost reduction
- Persistence Layer: save/load complete cognitive state
- Enhanced Third Choice: multi-strategy with scoring
- Self-aware reinforcement: outcomes shift the attractor

The agent now has:
- A soul (self layer)
- A biography (trajectory)
- Habits (pattern learner)
- Memory (ecology)
- Creativity (enhanced third choice)
- Continuity (persistence)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .core.space import CognitiveSpace
from .core.state import CognitiveState
from .core.trit import Trit, YIN, VOID, YANG
from .mapping.dimension_adapter import DimensionAdapter, DimensionSet
from .mapping.projector import InputProjector, ProjectionResult
from .mapping.pattern_learner import PatternLearner
from .memory.ecology import MemoryEcology, CognitiveEvent
from .memory.trajectory import CognitiveTrajectory
from .memory.climate import CognitiveClimate
from .decision.pathfinder import DecisionPathfinder, DecisionPath
from .decision.third_choice import ThirdChoiceGenerator, ThirdChoiceCandidate
from .self_layer import NLPSelfLayer
from .llm.bridge import LLMBridge
from .storage.persistence import PersistenceLayer


@dataclass
class AgentResponse:
    """The agent's response to a cognitive query (v0.3)."""

    input_text: str
    current_state: CognitiveState
    projection: ProjectionResult
    memory_recall: Dict[str, Any]
    decision: Optional[DecisionPath] = None
    third_choice_candidates: List[ThirdChoiceCandidate] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    llm_advice: Optional[str] = None
    growth_stage: str = "school"
    self_alignment: float = 0.0
    trajectory_length: int = 0
    pattern_matched: bool = False
    pattern_confidence: float = 0.0

    def summary(self) -> str:
        lines = [
            f"=== BTCU Agent Response (v0.3) ===",
            f"Input: {self.input_text[:100]}...",
            f"Growth Stage: {self.growth_stage}",
            f"Current State: #{self.current_state.index} [{self.current_state}]",
            f"  Polarity: {self.current_state.polarity:+d} | "
            f"YIN:{self.current_state.yin_count} "
            f"VOID:{self.current_state.void_count} "
            f"YANG:{self.current_state.yang_count}",
            f"Projection: {self.projection.source} "
            f"(confidence: {self.projection.confidence:.0%})",
            f"Self Alignment: {self.self_alignment:.1%}",
            f"Trajectory: {self.trajectory_length} steps",
        ]

        if self.pattern_matched:
            lines.append(f"Pattern Match: YES (confidence: {self.pattern_confidence:.0%})")
        else:
            lines.append(f"Pattern Match: no")

        if self.suggestions:
            lines.append(f"Suggestions:")
            for s in self.suggestions:
                lines.append(f"  - {s}")

        if self.decision:
            lines.append(f"Decision: {self.decision.summary()}")

        if self.third_choice_candidates:
            lines.append(f"Third Choice Candidates ({len(self.third_choice_candidates)}):")
            for i, tc in enumerate(self.third_choice_candidates[:3]):
                lines.append(f"  #{i+1} [{tc.strategy}] #{tc.state.index} "
                           f"score={tc.total_score:.2f}")

        if self.llm_advice:
            lines.append(f"LLM Advice: {self.llm_advice[:200]}...")

        return "\n".join(lines)


class BTCUAgent:
    """
    BTCU Harness Cognitive Agent v0.3.

    Integrates all layers:
    - Core: Trit, CognitiveState, CognitiveSpace
    - Mapping: DimensionAdapter, InputProjector, PatternLearner
    - Memory: MemoryEcology, CognitiveTrajectory
    - Decision: DecisionPathfinder, ThirdChoiceGenerator (enhanced)
    - Self: NLPSelfLayer (identity attractor)
    - LLM: LLMBridge
    - Storage: PersistenceLayer
    """

    def __init__(
        self,
        growth_stage: str = "school",
        resonance_radius: int = 3,
        decay_factor: float = 0.95,
        storage_path: Optional[str] = None,
    ) -> None:
        self.growth_stage = growth_stage
        self.dimension_set: Optional[DimensionSet] = None
        self.space: Optional[CognitiveSpace] = None
        self.ecology = MemoryEcology(
            resonance_radius=resonance_radius,
            decay_factor=decay_factor,
        )
        self.projector: Optional[InputProjector] = None
        self.pattern_learner = PatternLearner(similarity_threshold=0.65)
        self.trajectory = CognitiveTrajectory()
        self.climate = CognitiveClimate()
        self.self_layer = NLPSelfLayer()
        self.pathfinder: Optional[DecisionPathfinder] = None
        self.third_choice_gen = ThirdChoiceGenerator()
        self.llm_bridge: Optional[LLMBridge] = None
        self.persistence: Optional[PersistenceLayer] = None
        self._prev_state: Optional[CognitiveState] = None

        if storage_path:
            self.persistence = PersistenceLayer(storage_path)

    def init_project(
        self,
        domain: str = "default",
        dim_labels: Optional[List[str]] = None,
        llm_bridge: Optional[LLMBridge] = None,
        project_description: Optional[str] = None,
    ) -> DimensionSet:
        """Initialize a new project."""
        self.llm_bridge = llm_bridge
        adapter = DimensionAdapter()

        if dim_labels:
            dim_set = adapter.use_custom(dim_labels)
        elif project_description and llm_bridge:
            dim_set = adapter.adapt_with_llm(project_description, llm_bridge)
        else:
            dim_set = adapter.use_example(domain)

        adapter.lock(dim_set)
        self.dimension_set = dim_set

        self.space = CognitiveSpace(dim_set.labels)

        # Wire enhanced third choice generator with ecology and self layer
        self.third_choice_gen = ThirdChoiceGenerator(
            space=self.space,
            ecology=self.ecology,
            self_layer=self.self_layer,
        )

        self.projector = InputProjector(dim_set, self.growth_stage)
        self.pathfinder = DecisionPathfinder(self.space, self.ecology)

        return dim_set

    def set_self_level(
        self,
        name: str,
        description: str,
        state: CognitiveState,
        weight: float = 1.0,
        stability: float = 0.9,
    ) -> None:
        """Set a level in the NLP self layer."""
        self.self_layer.set_level(name, description, state, weight, stability)

    def process(
        self,
        input_text: str,
        target_state: Optional[CognitiveState] = None,
        conflict_state: Optional[CognitiveState] = None,
    ) -> AgentResponse:
        """Process an input through the full cognitive pipeline (v0.3)."""
        if self.projector is None:
            raise RuntimeError("Agent not initialized. Call init_project() first.")

        # 1-2. Pattern match or LLM projection
        projection, pattern_matched, pattern_confidence = self._resolve_projection(input_text)
        current_state = projection.state

        # 3. Recall memory
        memory_recall = self.ecology.recall(current_state)
        suggestions: List[str] = list(memory_recall.get("suggestions", []))

        # 4. Self alignment
        self_alignment = self._evaluate_self_alignment(current_state, suggestions)

        # 5. Decision path
        decision = self._find_decision_path(current_state, target_state)

        # 6. Third choice candidates
        third_candidates = self._generate_third_choices(current_state, conflict_state, suggestions)

        # 7. LLM advice
        llm_advice = self._get_llm_advice(input_text, memory_recall, pattern_matched)

        # 8. Learn pattern
        if not pattern_matched and projection.source == "llm":
            self.pattern_learner.learn(
                input_text, current_state,
                source="llm", confidence=projection.confidence,
            )

        # 9-11. Record cognition
        self._record_cognition(input_text, current_state, projection, pattern_matched)

        return AgentResponse(
            input_text=input_text,
            current_state=current_state,
            projection=projection,
            memory_recall=memory_recall,
            decision=decision,
            third_choice_candidates=third_candidates,
            suggestions=suggestions,
            llm_advice=llm_advice,
            growth_stage=self.growth_stage,
            self_alignment=self_alignment,
            trajectory_length=self.trajectory.length,
            pattern_matched=pattern_matched,
            pattern_confidence=pattern_confidence,
        )

    def _resolve_projection(
        self, input_text: str,
    ) -> tuple[ProjectionResult, bool, float]:
        """Try pattern match first, fall back to LLM projection."""
        pattern_matched = False
        pattern_confidence = 0.0
        projection: Optional[ProjectionResult] = None

        if self.growth_stage != "school" and self.dimension_set is not None:
            match = self.pattern_learner.match(input_text)
            if match:
                pattern, sim = match
                state = CognitiveState.from_values(pattern.state_values)
                projection = ProjectionResult(
                    state=state,
                    dimension_assessments={l: "pattern_match" for l in self.dimension_set.labels},
                    confidence=sim,
                    source="pattern",
                )
                pattern_matched = True
                pattern_confidence = sim

        if projection is None:
            assert self.projector is not None  # checked in process()
            llm_cb = self.llm_bridge if self.llm_bridge else None
            projection = self.projector.project(input_text, llm_cb)

        return projection, pattern_matched, pattern_confidence

    def _evaluate_self_alignment(
        self, current_state: CognitiveState, suggestions: List[str],
    ) -> float:
        """Evaluate alignment with self layer, append warning if low."""
        self_alignment = self.self_layer.alignment_score(current_state)
        if self_alignment < 0.3:
            suggestions.append(
                f"Low self-alignment ({self_alignment:.0%}). "
                f"This state is far from the agent's personality center."
            )
        return self_alignment

    def _find_decision_path(
        self, current_state: CognitiveState, target_state: Optional[CognitiveState],
    ) -> Optional[DecisionPath]:
        """Find decision path if a target state is specified."""
        if target_state and self.pathfinder:
            prefer_void = current_state.distance(target_state) >= 10
            return self.pathfinder.find_path(
                current_state, target_state, prefer_void=prefer_void,
            )
        return None

    def _generate_third_choices(
        self,
        current_state: CognitiveState,
        conflict_state: Optional[CognitiveState],
        suggestions: List[str],
    ) -> List[ThirdChoiceCandidate]:
        """Generate third-choice candidates if a conflict state is given."""
        if not conflict_state:
            return []
        candidates = self.third_choice_gen.generate_all(current_state, conflict_state)
        if candidates:
            best = candidates[0]
            suggestions.append(
                f"Third choice: [{best.strategy}] State #{best.state.index} "
                f"(score: {best.total_score:.2f}, "
                f"void: {best.void_ratio:.0%})"
            )
        return candidates

    def _get_llm_advice(
        self,
        input_text: str,
        memory_recall: Dict[str, Any],
        pattern_matched: bool,
    ) -> Optional[str]:
        """Get LLM advice based on growth stage and memory state."""
        if self.growth_stage == "school" and self.llm_bridge:
            memory_context = self._format_memory_context(memory_recall)
            return self.llm_bridge.advise(input_text, context=memory_context)
        if self.growth_stage == "graduate" and self.llm_bridge:
            state_mem = memory_recall.get("state")
            if state_mem and state_mem.is_empty and not pattern_matched:
                return self.llm_bridge.advise(input_text)
        return None

    def _record_cognition(
        self,
        input_text: str,
        current_state: CognitiveState,
        projection: ProjectionResult,
        pattern_matched: bool,
    ) -> None:
        """Record state in trajectory, memory ecology, and climate."""
        self.trajectory.record(
            state=current_state,
            context=input_text[:100],
            trigger="process",
            metadata={"source": projection.source, "pattern_matched": pattern_matched},
        )
        event = CognitiveEvent(
            state=current_state,
            prev_state=self._prev_state,
            context={"input": input_text, "source": projection.source},
            metadata={"projection_confidence": projection.confidence},
        )
        self.ecology.remember(event)
        self._prev_state = current_state
        self.climate.snapshot(current_state)

    def record_outcome(
        self,
        state: Optional[CognitiveState] = None,
        decision: Optional[str] = None,
        outcome: Optional[str] = None,
        outcome_positive: Optional[bool] = None,
    ) -> None:
        """Record outcome and reinforce self layer."""
        if state is None:
            state = self._prev_state
        if state is None:
            return

        # Update memory
        mem = self.ecology.state_store.get(state.index)
        if mem.visits:
            mem.visits[-1].decision = decision
            mem.visits[-1].outcome = outcome
            mem.visits[-1].outcome_positive = outcome_positive
            if outcome_positive is False and decision:
                if decision not in mem.suppressed_decisions:
                    mem.suppressed_decisions.append(decision)

        # Update transition memory
        if self._prev_state and self._prev_state != state:
            self.ecology.transition_store.record(
                from_idx=self._prev_state.index,
                to_idx=state.index,
                decision=decision,
                outcome=outcome,
                outcome_positive=outcome_positive,
            )

        # Reinforce self layer
        if outcome_positive is not None:
            self.self_layer.reinforce(state, positive=outcome_positive)
            self.pattern_learner.reinforce(state.index, outcome_positive)

    def advance_stage(self) -> str:
        """Advance growth stage: school -> internalize -> graduate."""
        if self.growth_stage == "school":
            self.growth_stage = "internalize"
        elif self.growth_stage == "internalize":
            self.growth_stage = "graduate"
        else:
            return self.growth_stage

        if self.projector:
            self.projector.set_growth_stage(self.growth_stage)
        return self.growth_stage

    def discover_seasons(self) -> List:
        """Discover cognitive seasons from ecology + trajectory + climate."""
        eco_seasons = self.ecology.sense_making()

        # Add trajectory-based seasons
        clusters = self.trajectory.detect_clusters()
        for c in clusters:
            eco_seasons.append(type(eco_seasons[0])(
                season_type="cluster",
                description=f"Cognitive cluster at #{c.center_index} "
                           f"({c.visit_count} visits, {len(c.member_indices)} members)",
                state_indices=c.member_indices,
                strength=c.visit_count / max(1, self.trajectory.length),
                evidence_count=c.visit_count,
            ))

        cycles = self.trajectory.detect_cycles()
        for cy in cycles:
            eco_seasons.append(type(eco_seasons[0])(
                season_type="cycle",
                description=f"Cognitive cycle: {cy.pattern} "
                           f"(repeated {cy.occurrences} times, period={cy.period})",
                state_indices=cy.pattern,
                strength=cy.occurrences / 10,
                evidence_count=cy.occurrences,
            ))

        return eco_seasons

    def climate_report(self) -> str:
        """Generate a cognitive climate report."""
        report = self.climate.report(
            ecology=self.ecology,
            trajectory=self.trajectory,
        )
        lines = [
            f"=== Cognitive Climate Report ===",
            f"Steps: {report.total_steps} | Unique states: {report.unique_states} "
            f"({report.exploration_rate:.0%} uniqueness)",
            f"Phase: {report.exploration_phase} "
            f"(recent new state rate: {report.recent_new_state_rate:.0%})",
            f"Polarity: avg={report.avg_polarity:+.1f} "
            f"trend={report.polarity_trend:+.3f} "
            f"volatility={report.polarity_volatility:.2f}",
            f"Climate zones: {len(report.zones)}",
        ]
        for z in report.zones[:3]:
            lines.append(f"  Zone #{z.center_index}: temp={z.temperature:.2f} "
                        f"visits={z.visit_count} polarity={z.avg_polarity:+.1f}")
        if report.dominant_period:
            lines.append(f"Rhythm: period~{report.dominant_period} "
                        f"regularity={report.rhythm_regularity:.0%}")
        if report.drift_magnitude > 0:
            lines.append(f"Drift: {report.drift_magnitude:.1f}"
                        + (f" toward #{report.drift_direction.index}" if report.drift_direction else ""))
        lines.append(f"Summary: {report.summary}")
        return "\n".join(lines)

    def save(self) -> Optional[str]:
        """Save complete cognitive state to disk."""
        if not self.persistence:
            return None
        return self.persistence.save(
            ecology=self.ecology,
            trajectory=self.trajectory,
            pattern_learner=self.pattern_learner,
            self_layer=self.self_layer,
            dim_labels=list(self.dimension_set.labels) if self.dimension_set else [],
            growth_stage=self.growth_stage,
            climate=self.climate,
        )

    def load(self) -> bool:
        """Load cognitive state from disk."""
        if not self.persistence or not self.persistence.exists:
            return False

        data = self.persistence.load()
        if not data:
            return False

        self.ecology = self.persistence.restore_ecology(data)
        self.trajectory = self.persistence.restore_trajectory(data)
        self.pattern_learner = self.persistence.restore_pattern_learner(data)
        self.self_layer = self.persistence.restore_self_layer(data)
        self.climate = self.persistence.restore_climate(data)
        self.growth_stage = data.get("growth_stage", "school")

        # Restore dimensions if available
        dim_labels = data.get("dimension_labels", [])
        if dim_labels and len(dim_labels) == 9:
            self.dimension_set = DimensionSet(labels=dim_labels, locked=True)
            self.space = CognitiveSpace(dim_labels)
            self.projector = InputProjector(self.dimension_set, self.growth_stage)
            self.pathfinder = DecisionPathfinder(self.space, self.ecology)
            self.third_choice_gen = ThirdChoiceGenerator(
                space=self.space,
                ecology=self.ecology,
                self_layer=self.self_layer,
            )

        return True

    def export_memory(self) -> Dict[str, Any]:
        """Export all memory."""
        return self.ecology.export_legacy()

    def import_memory(self, data: Dict[str, Any]) -> None:
        """Import memory."""
        self.ecology.import_legacy(data)

    def _format_memory_context(self, recall: Dict[str, Any]) -> str:
        parts = []
        state_mem = recall.get("state")
        if state_mem and not state_mem.is_empty:
            parts.append(f"Previous visits: {state_mem.visit_count}")
            if state_mem.success_count > 0:
                parts.append(f"Past successes: {state_mem.success_count}")
            if state_mem.failure_count > 0:
                parts.append(f"Past failures: {state_mem.failure_count}")

        suggestions = recall.get("suggestions", [])
        if suggestions:
            parts.append("Suggestions: " + " | ".join(suggestions[:3]))

        return "\n".join(parts) if parts else "No prior memory."

    def status(self) -> str:
        lines = [
            f"=== BTCU Agent Status (v0.3) ===",
            f"Stage: {self.growth_stage}",
            f"Dimensions: {self.dimension_set}",
            f"Memory: {self.ecology.state_store}",
            f"Transitions: {self.ecology.transition_store}",
            f"Trajectory: {self.trajectory}",
            f"Climate: {self.climate}",
            f"Patterns: {self.pattern_learner}",
            f"Self: {self.self_layer}",
            f"Self attractor: #{self.self_layer.attractor.index} [{self.self_layer.attractor}]",
        ]
        if self.projector:
            lines.append(f"Projector: {self.projector}")
        if self.llm_bridge:
            lines.append(f"LLM: {self.llm_bridge}")
        if self.persistence:
            lines.append(f"Storage: {self.persistence.info()}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"BTCUAgent(v0.3, stage={self.growth_stage}, "
            f"trajectory={self.trajectory.length}, "
            f"patterns={self.pattern_learner.pattern_count})"
        )
