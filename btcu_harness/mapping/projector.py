"""
InputProjector: Maps natural language input to a 9-dimensional ternary vector.

This is the agent's internal cognitive mapping - it takes an input
(question, situation, problem) and projects it onto the fixed 9-dimension
space to produce a CognitiveState.

Two modes:
1. School stage: LLM-assisted projection (LLM evaluates each dimension)
2. Internalize/Graduate stage: Pattern-based projection using accumulated
   memory (the agent maps inputs based on past experience, only calling
   LLM for genuinely novel inputs)

The projector is the "eye" of the agent - how it sees the world in
ternary terms.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..core.state import CognitiveState, NUM_DIMENSIONS
from .dimension_adapter import DimensionSet


@dataclass
class ProjectionResult:
    """Result of projecting an input onto the cognitive space."""

    state: CognitiveState
    dimension_assessments: Dict[str, str]  # label -> assessment text
    confidence: float = 1.0
    source: str = "llm"  # "llm" or "pattern" or "hybrid"


PROJECTION_PROMPT_TEMPLATE = """You are a ternary cognitive projector. Evaluate the following input across 9 cognitive dimensions.

Input: {input_text}

Dimensions (each must be -1, 0, or +1):
{dimension_list}

For each dimension, assign a value:
- -1: The input is negative/suppressing/regarding this dimension
-  0: The input is neutral/transitioning/unclear regarding this dimension
- +1: The input is positive/active/supporting regarding this dimension

Return ONLY a JSON object:
{{
    "assessments": [
        {{"dimension": "{dim1}", "value": -1|0|1, "reason": "brief reason"}},
        ...for all 9 dimensions...
    ]
}}

Be precise and analytical. Each dimension assessment should reflect a genuine evaluation of the input from that perspective."""


class InputProjector:
    """
    Projects inputs onto the 19683-state cognitive space.

    Requires a locked DimensionSet. The projection method depends on
    the agent's growth stage:

    - School: Always uses LLM for projection
    - Internalize: Uses pattern matching from memory, falls back to LLM
    - Graduate: Primarily pattern-based, LLM only for novel inputs
    """

    def __init__(self, dim_set: DimensionSet, growth_stage: str = "school") -> None:
        if not dim_set.locked:
            raise ValueError("DimensionSet must be locked before projection.")
        self.dim_set = dim_set
        self.growth_stage = growth_stage

        # Pattern store for internalize/graduate stages
        # Maps input features -> dimension values
        self._patterns: Dict[str, List[int]] = {}

    def project(
        self,
        input_text: str,
        llm_callback: Optional[Callable[[str], str]] = None,
    ) -> ProjectionResult:
        """
        Project an input onto the cognitive state space.

        Args:
            input_text: Natural language input to evaluate.
            llm_callback: Function that takes a prompt and returns LLM response.
                         Required for school stage, optional for later stages.

        Returns:
            ProjectionResult with the cognitive state and assessments.
        """
        if self.growth_stage == "school":
            return self._project_with_llm(input_text, llm_callback)
        elif self.growth_stage == "internalize":
            # Try pattern match first, fall back to LLM
            pattern_result = self._project_with_patterns(input_text)
            if pattern_result is not None:
                return pattern_result
            return self._project_with_llm(input_text, llm_callback)
        else:  # graduate
            pattern_result = self._project_with_patterns(input_text)
            if pattern_result is not None:
                return pattern_result
            # Only call LLM for truly novel inputs
            if llm_callback:
                return self._project_with_llm(input_text, llm_callback)
            # No LLM available - return void state
            return ProjectionResult(
                state=CognitiveState.all_void(),
                dimension_assessments={l: "unknown" for l in self.dim_set.labels},
                confidence=0.0,
                source="void_fallback",
            )

    def _project_with_llm(
        self,
        input_text: str,
        llm_callback: Optional[Callable[[str], str]],
    ) -> ProjectionResult:
        """Use LLM to evaluate each dimension."""
        if llm_callback is None:
            raise ValueError(
                "LLM callback required for school-stage projection."
            )

        dim_list = "\n".join(
            f"  {i+1}. {label}"
            for i, label in enumerate(self.dim_set.labels)
        )

        prompt = PROJECTION_PROMPT_TEMPLATE.format(
            input_text=input_text,
            dimension_list=dim_list,
            dim1=self.dim_set.labels[0],
        )

        response = llm_callback(prompt)

        # Parse response
        try:
            parsed = json.loads(response)
            assessments = parsed.get("assessments", [])
            values = []
            dim_assessments = {}

            for i, label in enumerate(self.dim_set.labels):
                if i < len(assessments):
                    val = int(assessments[i].get("value", 0))
                    reason = assessments[i].get("reason", "")
                    values.append(max(-1, min(1, val)))
                    dim_assessments[label] = reason
                else:
                    values.append(0)
                    dim_assessments[label] = "no assessment"

            state = CognitiveState.from_values(values)
            return ProjectionResult(
                state=state,
                dimension_assessments=dim_assessments,
                confidence=0.8,
                source="llm",
            )

        except (json.JSONDecodeError, ValueError, KeyError):
            # Fallback: void state
            return ProjectionResult(
                state=CognitiveState.all_void(),
                dimension_assessments={
                    l: "parse_error" for l in self.dim_set.labels
                },
                confidence=0.0,
                source="llm_parse_error",
            )

    def _project_with_patterns(
        self,
        input_text: str,
    ) -> Optional[ProjectionResult]:
        """
        Use accumulated patterns to project without LLM.

        This is a simple keyword/feature matching system.
        In production, this would be replaced with a trained classifier.
        """
        if not self._patterns:
            return None

        input_lower = input_text.lower()

        # Simple keyword matching against stored patterns
        best_match = None
        best_score = 0

        for pattern_key, values in self._patterns.items():
            keywords = pattern_key.split()
            score = sum(1 for kw in keywords if kw in input_lower)
            if score > best_score:
                best_score = score
                best_match = values

        if best_match is None or best_score == 0:
            return None

        state = CognitiveState.from_values(best_match)
        return ProjectionResult(
            state=state,
            dimension_assessments={
                l: "pattern_match" for l in self.dim_set.labels
            },
            confidence=min(1.0, best_score / 5),
            source="pattern",
        )

    def learn_pattern(
        self,
        input_text: str,
        state: CognitiveState,
    ) -> None:
        """
        Learn a projection pattern from experience.

        In the internalize stage, the agent stores LLM-generated projections
        as patterns so future similar inputs can be projected without LLM.
        """
        # Extract keywords (simple approach - production would use embeddings)
        keywords = sorted(set(
            word.lower().strip(".,!?;:")
            for word in input_text.split()
            if len(word) > 2
        ))[:5]  # Top 5 keywords

        pattern_key = " ".join(keywords)
        self._patterns[pattern_key] = list(state.values)

    def set_growth_stage(self, stage: str) -> None:
        """Update the growth stage (school/internalize/graduate)."""
        if stage not in ("school", "internalize", "graduate"):
            raise ValueError(f"Invalid growth stage: {stage}")
        self.growth_stage = stage

    @property
    def pattern_count(self) -> int:
        """Number of learned patterns."""
        return len(self._patterns)

    def __repr__(self) -> str:
        return (
            f"InputProjector(stage={self.growth_stage}, "
            f"patterns={self.pattern_count}, "
            f"dims={self.dim_set.labels})"
        )
