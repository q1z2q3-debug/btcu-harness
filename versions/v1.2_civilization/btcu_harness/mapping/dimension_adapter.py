"""
DimensionAdapter: LLM-assisted dimension adaptation for new projects.

When a new project starts, the LLM analyzes the project's domain and
suggests the most appropriate 9 dimensions. Once adapted, the dimensions
are fixed for the project's lifetime.

This is the ONLY place where the LLM is used for dimension selection.
After adaptation, all cognitive mapping is done by the agent internally
using the InputProjector.

The adapter provides:
1. A default dimension set (time/space/causality) for immediate use
2. LLM-based adaptation for custom project domains
3. Dimension validation and locking
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..core.state import NUM_DIMENSIONS


# Default dimension set: time / space / causality
DEFAULT_DIMENSIONS = [
    "past",       # 时间-过去
    "present",    # 时间-现在
    "future",     # 时间-未来
    "inner",      # 空间-内部
    "middle",     # 空间-中间
    "outer",      # 空间-外部
    "cause",      # 因果-因
    "condition",  # 因果-缘
    "effect",     # 因果-果
]

DEFAULT_DIM_DESCRIPTIONS = [
    {-1: "past evidence", 0: "transitioning", +1: "future-oriented"},
    {-1: "past-leaning", 0: "present-focused", +1: "future-leaning"},
    {-1: "regressive", 0: "open", +1: "progressive"},
    {-1: "internal deficit", 0: "neutral", +1: "internal strength"},
    {-1: "boundary weak", 0: "boundary fluid", +1: "boundary strong"},
    {-1: "external adverse", 0: "external neutral", +1: "external favorable"},
    {-1: "root cause negative", 0: "cause unclear", +1: "root cause positive"},
    {-1: "conditions unfavorable", 0: "conditions forming", +1: "conditions favorable"},
    {-1: "outcome negative", 0: "outcome pending", +1: "outcome positive"},
]

# Example dimension sets for common domains
EXAMPLE_DIMENSION_SETS = {
    "default": DEFAULT_DIMENSIONS,
    "investment": [
        "fundamentals", "technicals", "sentiment",
        "macro", "industry", "company",
        "risk", "timing", "return",
    ],
    "decision": [
        "motivation", "capability", "resource",
        "risk", "timing", "reward",
        "short_term", "mid_term", "long_term",
    ],
    "diagnosis": [
        "symptom", "structure", "essence",
        "history", "current", "trend",
        "internal_cause", "external_factor", "consequence",
    ],
    "ethics": [
        "intent", "action", "consequence",
        "individual", "group", "society",
        "short_term", "mid_term", "long_term",
    ],
}


@dataclass
class DimensionSet:
    """
    A locked set of 9 dimensions for a project.

    Once locked, the dimensions cannot be changed. This ensures
    all cognitive states in the project map to the same 19683 space.
    """

    labels: List[str]
    descriptions: Optional[List[Dict[int, str]]] = None
    domain: str = "custom"
    locked: bool = False

    def __post_init__(self) -> None:
        if len(self.labels) != NUM_DIMENSIONS:
            raise ValueError(
                f"Expected {NUM_DIMENSIONS} dimensions, got {len(self.labels)}"
            )

    def lock(self) -> None:
        """Lock this dimension set. Cannot be unlocked."""
        self.locked = True

    def __repr__(self) -> str:
        status = "LOCKED" if self.locked else "UNLOCKED"
        return f"DimensionSet({status}, domain={self.domain}, dims={self.labels})"


class DimensionAdapter:
    """
    Adapts and locks dimensions for a new project.

    Usage:
        adapter = DimensionAdapter()

        # Use default dimensions
        dim_set = adapter.use_default()

        # Or use an example set
        dim_set = adapter.use_example("investment")

        # Or adapt with LLM (requires LLM bridge)
        dim_set = adapter.adapt_with_llm(
            project_description="AI chip investment analysis",
            llm_callback=some_llm_function,
        )

        # Lock it
        adapter.lock(dim_set)
    """

    def __init__(self) -> None:
        self.current_set: Optional[DimensionSet] = None

    def use_default(self) -> DimensionSet:
        """Use the default time/space/causality dimension set."""
        ds = DimensionSet(
            labels=list(DEFAULT_DIMENSIONS),
            descriptions=[dict(d) for d in DEFAULT_DIM_DESCRIPTIONS],
            domain="default",
        )
        self.current_set = ds
        return ds

    def use_example(self, domain: str) -> DimensionSet:
        """Use a pre-defined example dimension set."""
        if domain not in EXAMPLE_DIMENSION_SETS:
            raise ValueError(
                f"Unknown domain '{domain}'. Available: {list(EXAMPLE_DIMENSION_SETS)}"
            )
        ds = DimensionSet(
            labels=list(EXAMPLE_DIMENSION_SETS[domain]),
            domain=domain,
        )
        self.current_set = ds
        return ds

    def use_custom(self, labels: Sequence[str], domain: str = "custom") -> DimensionSet:
        """Use a custom dimension set (must be exactly 9 labels)."""
        ds = DimensionSet(
            labels=list(labels),
            domain=domain,
        )
        self.current_set = ds
        return ds

    def adapt_with_llm(
        self,
        project_description: str,
        llm_callback: Any,
    ) -> DimensionSet:
        """
        Use LLM to suggest 9 dimensions for a project.

        The LLM is called ONCE here. After this, the dimensions are fixed
        and the agent maps inputs internally without LLM.

        Args:
            project_description: Natural language description of the project.
            llm_callback: A callable that takes a prompt string and returns
                          a response string. Typically the LLM bridge.

        Returns:
            A DimensionSet with 9 suggested dimensions.
        """
        prompt = DIMENSION_ADAPTATION_PROMPT.format(
            project_description=project_description
        )

        response = llm_callback(prompt)

        # Parse LLM response - expect JSON with dimension labels
        try:
            parsed = json.loads(response)
            labels = parsed.get("dimensions", [])
            if len(labels) != NUM_DIMENSIONS:
                raise ValueError(
                    f"LLM returned {len(labels)} dimensions, expected {NUM_DIMENSIONS}"
                )
        except (json.JSONDecodeError, ValueError):
            # Fallback: try to extract 9 lines
            lines = [
                line.strip().strip('"').strip("'").strip(",")
                for line in response.strip().split("\n")
                if line.strip()
            ]
            labels = lines[:NUM_DIMENSIONS]
            if len(labels) != NUM_DIMENSIONS:
                # Ultimate fallback: use default
                labels = list(DEFAULT_DIMENSIONS)

        ds = DimensionSet(
            labels=labels,
            domain="llm_adapted",
        )
        self.current_set = ds
        return ds

    def lock(self, dim_set: Optional[DimensionSet] = None) -> DimensionSet:
        """Lock the current (or specified) dimension set."""
        if dim_set is None:
            dim_set = self.current_set
        if dim_set is None:
            raise ValueError("No dimension set to lock. Call use_default/use_example/adapt_with_llm first.")
        dim_set.lock()
        return dim_set

    @property
    def is_ready(self) -> bool:
        """True if a dimension set is locked and ready for use."""
        return self.current_set is not None and self.current_set.locked


DIMENSION_ADAPTATION_PROMPT = """You are a cognitive architecture designer. A new project needs 9 cognitive dimensions for analysis.

Project description: {project_description}

Design exactly 9 dimensions that are most relevant to this project. Each dimension will be evaluated on a ternary scale: -1 (negative/suppressing), 0 (neutral/transitioning), +1 (positive/active).

Return ONLY a JSON object with this exact format:
{{
    "dimensions": ["dim1", "dim2", "dim3", "dim4", "dim5", "dim6", "dim7", "dim8", "dim9"],
    "rationale": "Brief explanation of why these 9 dimensions"
}}

Guidelines:
- Dimensions should cover different aspects (temporal, spatial, causal, evaluative, etc.)
- Each dimension should be independent (not redundant)
- Names should be concise (1-2 words)
- Think about what perspectives matter most for this specific project
"""
