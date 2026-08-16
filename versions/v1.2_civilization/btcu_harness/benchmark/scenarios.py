"""Benchmark scenarios and test cases for BTCU evaluation.

Four benchmark categories:
1. Decision Consistency - structured vs unstructured state
2. Third Choice Quality - creativity from binary conflicts
3. Token Economy - LLM call reduction over time
4. Path Quality - navigation through cognitive space
"""

from __future__ import annotations

import json
import random
from typing import Callable, Dict, List, Optional, Tuple

from ..core.state import CognitiveState, SPACE_SIZE
from ..agent import BTCUAgent


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

class BenchmarkScenario:
    """A single benchmark scenario with inputs and expected behavior."""

    def __init__(
        self,
        name: str,
        description: str,
        inputs: List[str],
        conflict_pairs: Optional[List[Tuple[str, str]]] = None,
        expected_range: Optional[Tuple[int, int]] = None,
    ):
        self.name = name
        self.description = description
        self.inputs = inputs
        self.conflict_pairs = conflict_pairs or []
        self.expected_range = expected_range


# Predefined scenarios
SCENARIOS = {
    "investment": BenchmarkScenario(
        name="Investment Decision",
        description="Evaluate investment opportunities across risk/reward dimensions",
        inputs=[
            "Should I invest in this high-growth tech stock?",
            "Is it safe to put money in bonds now?",
            "Should I diversify into emerging markets?",
            "Real estate or crypto, which is better?",
            "Should I hold cash during a recession?",
            "Is this the right time to buy gold?",
            "Should I invest in AI startups?",
            "What about renewable energy stocks?",
            "Should I take profits from my current holdings?",
            "Is dollar-cost averaging still a good strategy?",
        ],
        conflict_pairs=[
            ("High risk high reward", "Safe stable returns"),
            ("Short term gains", "Long term compound growth"),
        ],
        expected_range=(8000, 12000),  # States around investment domain
    ),
    "technology": BenchmarkScenario(
        name="Technology Adoption",
        description="Evaluate technology adoption decisions",
        inputs=[
            "Should we migrate to microservices?",
            "Is serverless architecture right for us?",
            "Should we adopt GraphQL or stick with REST?",
            "Is it time to upgrade to Python 3.12?",
            "Should we containerize our entire stack?",
            "Move to cloud or keep on-premise?",
            "Should we adopt a new frontend framework?",
            "Is AI integration worth the complexity?",
            "Should we build or buy this solution?",
            "Is it time to refactor the legacy codebase?",
        ],
        conflict_pairs=[
            ("Cutting edge technology", "Proven stable stack"),
            ("Speed of development", "Code maintainability"),
        ],
        expected_range=(12000, 16000),
    ),
    "career": BenchmarkScenario(
        name="Career Decision",
        description="Evaluate career path choices",
        inputs=[
            "Should I switch to management or stay technical?",
            "Is it worth going back to school for a PhD?",
            "Should I join a startup or stay at a big company?",
            "Is remote work sustainable for my career?",
            "Should I specialize deeply or stay generalist?",
            "Is it time to negotiate a raise or look elsewhere?",
            "Should I take this overseas opportunity?",
            "Is entrepreneurship the right path for me?",
            "Should I focus on technical skills or soft skills?",
            "Is work-life balance more important than salary?",
        ],
        conflict_pairs=[
            ("High salary demanding job", "Lower pay balanced life"),
            ("Job security", "Career growth potential"),
        ],
        expected_range=(4000, 8000),
    ),
}


def get_scenario(name: str) -> BenchmarkScenario:
    """Get a predefined scenario by name."""
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {name}. Available: {list(SCENARIOS.keys())}")
    return SCENARIOS[name]


def list_scenarios() -> List[str]:
    """List all available scenario names."""
    return list(SCENARIOS.keys())
