"""
LLMBridge: Multi-provider LLM bridge for BTCU Harness.

Supports three LLM providers through a unified interface:
    1. OpenAI (GPT-4o, GPT-4o-mini, etc.)
    2. Anthropic Claude (Claude 3.5 Sonnet, Claude 3 Opus, etc.)
    3. Google Gemini (Gemini 1.5 Pro/Flash, etc.)

Plus a callback mode for testing and custom integrations.

Usage:
    # Auto-detect from config
    bridge = LLMBridge()  # reads BTCU_LLM_PROVIDER env

    # Explicit provider
    bridge = LLMBridge(provider="anthropic", api_key="sk-...", model="claude-3-5-sonnet-20241022")

    # Callback mode (no API needed)
    bridge = LLMBridge(callback=lambda prompt: '{"assessments": [...]}')

The bridge is directly callable -- LLMBridge(prompt) returns the response string.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from ..config import settings

logger = logging.getLogger("btcu_harness.llm")


class LLMProvider:
    """Base class for LLM providers."""

    name: str = "base"

    def __init__(self, api_key: str, model: str, api_base: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model
        self.api_base = api_base

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""

    name = "openai"

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        try:
            import openai  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install 'btcu-harness[openai]'"
            )

        client = openai.OpenAI(base_url=self.api_base, api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    name = "anthropic"

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Install with: pip install 'btcu-harness[anthropic]'"
            )

        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text if message.content else ""


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    name = "gemini"

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        try:
            from google import genai  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "google-genai package not installed. Install with: pip install 'btcu-harness[gemini]'"
            )

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=self.model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={"temperature": temperature},
        )
        return response.text or ""


_PROVIDERS: Dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


_SYSTEM_PROMPT = (
    "You are a cognitive projection engine for the BTCU Harness. "
    "Always respond with valid JSON when asked to evaluate dimensions."
)


class LLMBridge:
    """
    Multi-provider LLM bridge.

    Supports OpenAI, Anthropic Claude, Google Gemini, and callback mode.
    Provider is selected via:
        1. Explicit `provider` argument
        2. BTCU_LLM_PROVIDER env var (default: "openai")
        3. Callback mode if `callback` is provided

    Examples:
        >>> bridge = LLMBridge(provider="anthropic", api_key="sk-...")
        >>> bridge = LLMBridge()  # auto-detect from env
        >>> bridge = LLMBridge(callback=lambda p: '{"value": 0}')
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        callback: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.callback = callback
        self.provider_name = provider or settings.llm_provider
        self.api_base = api_base or settings.llm_api_base
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model

        self._provider: Optional[LLMProvider] = None
        if callback is None:
            self._init_provider()

        # Call statistics
        self.total_calls = 0
        self.dimension_adaptation_calls = 0
        self.projection_calls = 0
        self.advisor_calls = 0

    def _init_provider(self) -> None:
        cls = _PROVIDERS.get(self.provider_name)
        if cls is None:
            raise ValueError(
                f"Unknown LLM provider: {self.provider_name}. "
                f"Supported: {list(_PROVIDERS.keys())}"
            )
        self._provider = cls(
            api_key=self.api_key,
            model=self.model,
            api_base=self.api_base,
        )

    def __call__(self, prompt: str) -> str:
        return self.query(prompt)

    def query(self, prompt: str) -> str:
        """Send a query to the LLM and return the response text."""
        self.total_calls += 1

        if self.callback:
            return self.callback(prompt)

        assert self._provider is not None
        return self._provider.complete(_SYSTEM_PROMPT, prompt)

    def adapt_dimensions(self, project_description: str) -> str:
        """LLM call for dimension adaptation."""
        self.dimension_adaptation_calls += 1
        from ..mapping.dimension_adapter import DIMENSION_ADAPTATION_PROMPT

        prompt = DIMENSION_ADAPTATION_PROMPT.format(project_description=project_description)
        return self.query(prompt)

    def project_input(self, input_text: str, dimension_labels: list) -> str:
        """LLM call for input projection."""
        self.projection_calls += 1
        from ..mapping.projector import PROJECTION_PROMPT_TEMPLATE

        dim_list = "\n".join(f"  {i+1}. {label}" for i, label in enumerate(dimension_labels))
        prompt = PROJECTION_PROMPT_TEMPLATE.format(
            input_text=input_text, dimension_list=dim_list, dim1=dimension_labels[0],
        )
        return self.query(prompt)

    def advise(self, question: str, context: Optional[str] = None) -> str:
        """Use LLM as an advisor for novel situations (graduate stage)."""
        self.advisor_calls += 1
        full_prompt = question
        if context:
            full_prompt = f"Context: {context}\n\nQuestion: {question}"
        return self.query(full_prompt)

    @property
    def cost_stats(self) -> Dict[str, int]:
        return {
            "total_calls": self.total_calls,
            "dimension_adaptation": self.dimension_adaptation_calls,
            "projection": self.projection_calls,
            "advisor": self.advisor_calls,
        }

    def __repr__(self) -> str:
        mode = "callback" if self.callback else self.provider_name
        return f"LLMBridge(provider={mode}, model={self.model}, calls={self.total_calls})"
