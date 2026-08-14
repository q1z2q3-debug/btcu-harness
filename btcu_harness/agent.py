"""
BTCU Agent: The main cognitive agent loop.

Integrates all layers into a single agent that can:
1. Adapt dimensions for a new project (with LLM)
2. Project inputs onto the 19683 space
3. Recall relevant memories
4. Make decisions by generating state transition paths
5. Generate third choices when facing binary conflicts
6. Remember outcomes and grow over time

The agent evolves through three stages:
- School: LLM does most cognitive work, BTCU records
- Internalize: BTCU matches patterns, LLM for novel inputs
- Graduate: BTCU primarily self-sufficient, LLM as advisor only
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
from .memory.ecology import MemoryEcology, CognitiveEvent
from .decision.pathfinder import DecisionPathfinder, DecisionPath
from .decision.third_choice import ThirdChoiceGenerator, ThirdChoice
from .llm.bridge import LLMBridge


@dataclass
class AgentResponse:
    """The agent's response to a cognitive query."""

    input_text: str
    current_state: CognitiveState
    projection: ProjectionResult
    memory_recall: Dict[str, Any]
    decision: Optional[DecisionPath] = None
    third_choice: Optional[ThirdChoice] = None
    suggestions: List[str] = field(default_factory=list)
    llm_advice: Optional[str] = None
    growth_stage: str = "school"

    def summary(self) -> str:
        """Human-readable summary of the agent's cognitive process."""
        lines = [
            f"=== BTCU Agent Response ===",
            f"Input: {self.input_text[:100]}...",
            f"Growth Stage: {self.growth_stage}",
            f"Current State: #{self.current_state.index} [{self.current_state}]",
            f"  Polarity: {self.current_state.polarity:+d} | "
            f"YIN:{self.current_state.yin_count} "
            f"VOID:{self.current_state.void_count} "
            f"YANG:{self.current_state.yang_count}",
            f"Projection Source: {self.projection.source} "
            f"(confidence: {self.projection.confidence:.0%})",
            f"Memory: {self.memory_recall.get('state', 'N/A')}",
        ]

        if self.suggestions:
            lines.append(f"Suggestions:")
            for s in self.suggestions:
                lines.append(f"  - {s}")

        if self.decision:
            lines.append(f"Decision: {self.decision.summary()}")

        if self.third_choice:
            lines.append(f"Third Choice: {self.third_choice.summary()}")

        if self.llm_advice:
            lines.append(f"LLM Advice: {self.llm_advice[:200]}...")

        return "\n".join(lines)


class BTCUAgent:
    """
    The main BTCU Harness cognitive agent.

    Lifecycle:
        1. Create agent
        2. Initialize project (adapt + lock dimensions)
        3. Process inputs (project → recall → decide → remember)
        4. Grow through stages (school → internalize → graduate)

    Example:
        agent = BTCUAgent()

        # Initialize project
        agent.init_project(
            domain="investment",
            llm_bridge=some_bridge,
        )

        # Process inputs
        response = agent.process("Should I invest in AI chips?")

        # Record outcome
        agent.record_outcome(
            state=response.current_state,
            decision="invest",
            outcome="profit",
            positive=True,
        )
    """

    def __init__(
        self,
        growth_stage: str = "school",
        resonance_radius: int = 3,
        decay_factor: float = 0.95,
    ) -> None:
        self.growth_stage = growth_stage
        self.dimension_set: Optional[DimensionSet] = None
        self.space: Optional[CognitiveSpace] = None
        self.ecology = MemoryEcology(
            resonance_radius=resonance_radius,
            decay_factor=decay_factor,
        )
        self.projector: Optional[InputProjector] = None
        self.pathfinder: Optional[DecisionPathfinder] = None
        self.third_choice_gen = ThirdChoiceGenerator()
        self.llm_bridge: Optional[LLMBridge] = None

        # Track previous state for transition memory
        self._prev_state: Optional[CognitiveState] = None

    def init_project(
        self,
        domain: str = "default",
        dim_labels: Optional[List[str]] = None,
        llm_bridge: Optional[LLMBridge] = None,
        project_description: Optional[str] = None,
    ) -> DimensionSet:
        """
        Initialize a new project by adapting and locking dimensions.

        Args:
            domain: Predefined domain name ("default", "investment", etc.)
            dim_labels: Custom dimension labels (overrides domain)
            llm_bridge: LLM bridge for adaptation (if using LLM)
            project_description: Description for LLM-based adaptation

        Returns:
            The locked DimensionSet.
        """
        self.llm_bridge = llm_bridge

        adapter = DimensionAdapter()

        if dim_labels:
            dim_set = adapter.use_custom(dim_labels)
        elif project_description and llm_bridge:
            dim_set = adapter.adapt_with_llm(
                project_description, llm_bridge
            )
        else:
            dim_set = adapter.use_example(domain)

        adapter.lock(dim_set)
        self.dimension_set = dim_set

        # Create cognitive space with dimension labels
        self.space = CognitiveSpace(dim_set.labels)
        self.third_choice_gen.space = self.space

        # Create projector
        self.projector = InputProjector(dim_set, self.growth_stage)

        # Create pathfinder with ecology
        self.pathfinder = DecisionPathfinder(self.space, self.ecology)

        return dim_set

    def process(
        self,
        input_text: str,
        target_state: Optional[CognitiveState] = None,
        conflict_state: Optional[CognitiveState] = None,
    ) -> AgentResponse:
        """
        Process an input through the full cognitive pipeline.

        1. Project input onto 19683 space
        2. Recall relevant memories
        3. If target_state given: find decision path
        4. If conflict_state given: generate third choice
        5. If school stage or novel input: get LLM advice
        6. Return response

        Args:
            input_text: Natural language input to process.
            target_state: If provided, find a path to this state.
            conflict_state: If provided, resolve conflict between
                           current state and this state.

        Returns:
            AgentResponse with full cognitive process details.
        """
        if self.projector is None:
            raise RuntimeError("Agent not initialized. Call init_project() first.")

        # 1. Project input
        llm_cb = self.llm_bridge if self.llm_bridge else None
        projection = self.projector.project(input_text, llm_cb)
        current_state = projection.state

        # 2. Recall memory
        memory_recall = self.ecology.recall(current_state)

        # 3. Collect suggestions
        suggestions = memory_recall.get("suggestions", [])

        # 4. Decision path (if target specified)
        decision = None
        if target_state and self.pathfinder:
            prefer_void = current_state.distance(target_state) >= 10
            decision = self.pathfinder.find_path(
                current_state, target_state, prefer_void=prefer_void
            )

        # 5. Third choice (if conflict specified)
        third_choice = None
        if conflict_state:
            third_choice = self.third_choice_gen.generate(
                current_state, conflict_state
            )
            suggestions.append(
                f"Third choice generated: State #{third_choice.state.index} "
                f"(voided {len(third_choice.voided_dims)} conflicting dimensions)"
            )

        # 6. LLM advice (if in school stage or novel input)
        llm_advice = None
        if self.growth_stage == "school" and self.llm_bridge:
            # In school stage, LLM provides reasoning alongside BTCU structure
            memory_context = self._format_memory_context(memory_recall)
            llm_advice = self.llm_bridge.advise(
                input_text, context=memory_context
            )
        elif self.growth_stage == "graduate" and self.llm_bridge:
            # In graduate stage, only consult LLM for novel (unvisited) states
            state_mem = memory_recall.get("state")
            if state_mem and state_mem.is_empty:
                llm_advice = self.llm_bridge.advise(input_text)

        # 7. Learn pattern (for internalize/graduate stages)
        if self.growth_stage != "school":
            self.projector.learn_pattern(input_text, current_state)

        # 8. Record in memory ecology
        event = CognitiveEvent(
            state=current_state,
            prev_state=self._prev_state,
            context={"input": input_text, "source": projection.source},
            metadata={"projection_confidence": projection.confidence},
        )
        self.ecology.remember(event)
        self._prev_state = current_state

        return AgentResponse(
            input_text=input_text,
            current_state=current_state,
            projection=projection,
            memory_recall=memory_recall,
            decision=decision,
            third_choice=third_choice,
            suggestions=suggestions,
            llm_advice=llm_advice,
            growth_stage=self.growth_stage,
        )

    def record_outcome(
        self,
        state: Optional[CognitiveState] = None,
        decision: Optional[str] = None,
        outcome: Optional[str] = None,
        outcome_positive: Optional[bool] = None,
    ) -> None:
        """Record the outcome of a decision for memory reinforcement."""
        if state is None:
            state = self._prev_state
        if state is None:
            return

        # Update the most recent visit with outcome
        mem = self.ecology.state_store.get(state.index)
        if mem.visits:
            mem.visits[-1].decision = decision
            mem.visits[-1].outcome = outcome
            mem.visits[-1].outcome_positive = outcome_positive

            # Suppress failed decisions
            if outcome_positive is False and decision:
                if decision not in mem.suppressed_decisions:
                    mem.suppressed_decisions.append(decision)

        # Also update transition memory if applicable
        if self._prev_state and self._prev_state != state:
            self.ecology.transition_store.record(
                from_idx=self._prev_state.index,
                to_idx=state.index,
                decision=decision,
                outcome=outcome,
                outcome_positive=outcome_positive,
            )

    def advance_stage(self) -> str:
        """
        Advance to the next growth stage.

        school -> internalize -> graduate

        Returns the new stage name.
        """
        if self.growth_stage == "school":
            self.growth_stage = "internalize"
        elif self.growth_stage == "internalize":
            self.growth_stage = "graduate"
        else:
            return self.growth_stage  # already at graduate

        if self.projector:
            self.projector.set_growth_stage(self.growth_stage)

        return self.growth_stage

    def discover_seasons(self) -> List:
        """Run sense-making to discover cognitive seasons."""
        return self.ecology.sense_making()

    def export_memory(self) -> Dict[str, Any]:
        """Export all memory for persistence or transfer."""
        return self.ecology.export_legacy()

    def import_memory(self, data: Dict[str, Any]) -> None:
        """Import memory from a previous export."""
        self.ecology.import_legacy(data)

    def _format_memory_context(self, recall: Dict[str, Any]) -> str:
        """Format memory recall as context string for LLM."""
        parts = []
        state_mem = recall.get("state")
        if state_mem and not state_mem.is_empty:
            parts.append(
                f"Previous visits to this state: {state_mem.visit_count}"
            )
            if state_mem.success_count > 0:
                parts.append(f"Past successes: {state_mem.success_count}")
            if state_mem.failure_count > 0:
                parts.append(f"Past failures: {state_mem.failure_count}")
            if state_mem.insights:
                parts.append(f"Insights: {'; '.join(state_mem.insights[:3])}")

        suggestions = recall.get("suggestions", [])
        if suggestions:
            parts.append("Suggestions: " + " | ".join(suggestions[:3]))

        return "\n".join(parts) if parts else "No prior memory for this state."

    def status(self) -> str:
        """Return agent status summary."""
        lines = [
            f"=== BTCU Agent Status ===",
            f"Stage: {self.growth_stage}",
            f"Dimensions: {self.dimension_set}",
            f"Memory: {self.ecology.state_store}",
            f"Transitions: {self.ecology.transition_store}",
        ]
        if self.projector:
            lines.append(f"Projector: {self.projector}")
        if self.llm_bridge:
            lines.append(f"LLM: {self.llm_bridge}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"BTCUAgent(stage={self.growth_stage}, "
            f"dims={'set' if self.dimension_set else 'none'})"
        )
