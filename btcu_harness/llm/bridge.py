"""
LLMBridge: Connects BTCU Harness to large language models.

The LLM serves three roles in BTCU:
1. Dimension adapter: suggests 9 dimensions for a new project (once)
2. Input projector: evaluates inputs across 9 dimensions (school stage)
3. Advisor: consulted for genuinely novel inputs (graduate stage)

The bridge provides a unified interface regardless of the underlying
LLM provider (OpenAI, local model, etc).

Cost model:
- School stage: C proportional to N_call (every input needs LLM)
- Internalize: C proportional to N_pattern_miss (only novel inputs)
- Graduate: C proportional to N_unknown (only truly unknown territory)
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from ..config import settings


class LLMBridge:
    """
    Bridge to a large language model.

    Supports two modes:
    1. API mode: Uses OpenAI-compatible API
    2. Callback mode: Uses a provided callback function
       (for testing, local models, or custom integrations)
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        callback: Optional[Callable[[str], str]] = None,
    ) -> None:
        """
        Initialize the LLM bridge.

        Args:
            api_base: API base URL (e.g. "https://api.openai.com/v1")
            api_key: API key
            model: Model name
            callback: Custom callback function. If provided, takes
                     precedence over API settings.
        """
        self.callback = callback
        self.api_base = api_base or settings.llm_api_base
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

        # Call statistics for cost tracking
        self.total_calls = 0
        self.dimension_adaptation_calls = 0
        self.projection_calls = 0
        self.advisor_calls = 0

    def __call__(self, prompt: str) -> str:
        """
        Call the LLM with a prompt. This makes the bridge directly
        usable as the llm_callback parameter expected by DimensionAdapter
        and InputProjector.
        """
        return self.query(prompt)

    def query(self, prompt: str) -> str:
        """
        Send a query to the LLM and return the response text.

        Uses callback if available, otherwise falls back to API call.
        """
        self.total_calls += 1

        if self.callback:
            return self.callback(prompt)

        return self._api_call(prompt)

    def _api_call(self, prompt: str) -> str:
        """Make an actual API call to the LLM."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

        client = openai.OpenAI(
            base_url=self.api_base,
            api_key=self.api_key,
        )

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cognitive projection engine for the BTCU Harness. "
                        "Always respond with valid JSON when asked to evaluate dimensions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content or ""

    def adapt_dimensions(self, project_description: str) -> str:
        """LLM call for dimension adaptation."""
        self.dimension_adaptation_calls += 1
        from ..mapping.dimension_adapter import DIMENSION_ADAPTATION_PROMPT

        prompt = DIMENSION_ADAPTATION_PROMPT.format(
            project_description=project_description
        )
        return self.query(prompt)

    def project_input(
        self,
        input_text: str,
        dimension_labels: list,
    ) -> str:
        """LLM call for input projection."""
        self.projection_calls += 1
        from ..mapping.projector import PROJECTION_PROMPT_TEMPLATE

        dim_list = "\n".join(
            f"  {i+1}. {label}"
            for i, label in enumerate(dimension_labels)
        )

        prompt = PROJECTION_PROMPT_TEMPLATE.format(
            input_text=input_text,
            dimension_list=dim_list,
            dim1=dimension_labels[0],
        )
        return self.query(prompt)

    def advise(self, question: str, context: Optional[str] = None) -> str:
        """
        Use LLM as an advisor for novel situations.

        In the graduate stage, this is called only when the agent
        encounters truly unknown territory in the 19683 space.
        """
        self.advisor_calls += 1

        full_prompt = question
        if context:
            full_prompt = f"Context: {context}\n\nQuestion: {question}"

        return self.query(full_prompt)

    @property
    def cost_stats(self) -> Dict[str, int]:
        """Return call statistics for cost analysis."""
        return {
            "total_calls": self.total_calls,
            "dimension_adaptation": self.dimension_adaptation_calls,
            "projection": self.projection_calls,
            "advisor": self.advisor_calls,
        }

    def __repr__(self) -> str:
        return (
            f"LLMBridge(model={self.model}, "
            f"mode={'callback' if self.callback else 'api'}, "
            f"calls={self.total_calls})"
        )
