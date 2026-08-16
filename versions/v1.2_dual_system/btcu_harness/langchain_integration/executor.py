"""
BTCU-enhanced LangChain agent factory.

Provides factory functions to create LangChain agents enhanced with
BTCU cognitive middleware.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from langchain.agents import create_agent

from .btcucognitive_agent import BTCUCognitiveMiddleware


def create_btcu_agent(
    model: Any,
    tools: List[Any],
    api_key: Optional[str] = None,
    provider: str = "openai",
    cognitive_model: str = "gpt-4o-mini",
    growth_stage: str = "school",
    verbose: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Create a LangChain agent enhanced with BTCU cognitive middleware.

    Args:
        model: LangChain chat model (e.g., ChatOpenAI, ChatAnthropic)
        tools: List of LangChain tools
        api_key: LLM API key for BTCU cognitive projection.
            If None, BTCU runs in rule-based mode (no LLM projection).
        provider: LLM provider for cognitive projection
        cognitive_model: Model for cognitive projection
        growth_stage: BTCU growth stage (school/internalize/graduate)
        verbose: Log cognitive state at each step
        **kwargs: Additional arguments passed to langchain.agents.create_agent

    Returns:
        A compiled LangGraph agent (CompiledStateGraph) with BTCU middleware.

    Example:
        from langchain_openai import ChatOpenAI
        from btcu_harness.langchain_integration import create_btcu_agent

        agent = create_btcu_agent(
            model=ChatOpenAI(model="gpt-4o"),
            tools=[...],
            api_key="sk-...",
        )
        result = agent.invoke({"messages": [HumanMessage("Hello!")]})
    """
    middleware = BTCUCognitiveMiddleware(
        api_key=api_key,
        provider=provider,
        model=cognitive_model,
        growth_stage=growth_stage,
        verbose=verbose,
    )

    return create_agent(
        model=model,
        tools=tools,
        middleware=[middleware],
        **kwargs,
    )


def create_btcu_agent_from_env(
    model: Any,
    tools: List[Any],
    verbose: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Create a BTCU-enhanced agent using environment variables for configuration.

    Reads:
        OPENAI_API_KEY or ANTHROPIC_API_KEY or GEMINI_API_KEY
        BTCU_GROWTH_STAGE (default: school)
        BTCU_COGNITIVE_MODEL (default: gpt-4o-mini)

    Args:
        model: LangChain chat model
        tools: List of LangChain tools
        verbose: Log cognitive state at each step
        **kwargs: Additional arguments for create_agent

    Returns:
        A compiled LangGraph agent with BTCU middleware.
    """
    # Determine provider and API key from environment
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if openai_key:
        provider, api_key = "openai", openai_key
    elif anthropic_key:
        provider, api_key = "anthropic", anthropic_key
    elif gemini_key:
        provider, api_key = "gemini", gemini_key
    else:
        provider, api_key = "openai", None

    cognitive_model = os.environ.get("BTCU_COGNITIVE_MODEL", "gpt-4o-mini")
    growth_stage = os.environ.get("BTCU_GROWTH_STAGE", "school")

    return create_btcu_agent(
        model=model,
        tools=tools,
        api_key=api_key,
        provider=provider,
        cognitive_model=cognitive_model,
        growth_stage=growth_stage,
        verbose=verbose,
        **kwargs,
    )
