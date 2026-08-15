"""Benchmark scenarios for BTCU-LangChain comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BenchmarkScenario:
    """A single benchmark scenario."""
    id: str
    name: str
    category: str  # math / search / multi_step / creative / analytical
    query: str
    expected_tools: List[str] = field(default_factory=list)
    description: str = ""


BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    # Math scenarios
    BenchmarkScenario(
        id="math_01",
        name="Simple Arithmetic",
        category="math",
        query="What is 25 * 17 + 33?",
        expected_tools=["calculator"],
        description="Basic arithmetic that requires a calculator tool.",
    ),
    BenchmarkScenario(
        id="math_02",
        name="Complex Expression",
        category="math",
        query="Calculate the factorial of 8 and divide by 4.",
        expected_tools=["calculator"],
        description="Multi-step mathematical calculation.",
    ),
    BenchmarkScenario(
        id="math_03",
        name="Percentage",
        category="math",
        query="What is 15% of 240?",
        expected_tools=["calculator"],
        description="Percentage calculation.",
    ),
    # Search scenarios
    BenchmarkScenario(
        id="search_01",
        name="Fact Lookup",
        category="search",
        query="Search for information about Python programming language.",
        expected_tools=["search"],
        description="Simple fact retrieval.",
    ),
    BenchmarkScenario(
        id="search_02",
        name="Technical Query",
        category="search",
        query="Find information about BTCU Harness.",
        expected_tools=["search"],
        description="Technical domain query.",
    ),
    # Multi-step scenarios
    BenchmarkScenario(
        id="multi_01",
        name="Search Then Calculate",
        category="multi_step",
        query="Search for the value of pi, then calculate pi squared.",
        expected_tools=["search", "calculator"],
        description="Requires search followed by calculation.",
    ),
    BenchmarkScenario(
        id="multi_02",
        name="Multi-Calculation",
        category="multi_step",
        query="Calculate 100 / 7 and also 200 * 3, then tell me which is larger.",
        expected_tools=["calculator"],
        description="Multiple calculations in sequence.",
    ),
    # Creative scenarios
    BenchmarkScenario(
        id="creative_01",
        name="Creative Problem",
        category="creative",
        query="If I have 3 boxes with 12 items each and give away 15, how many remain?",
        expected_tools=["calculator"],
        description="Word problem requiring translation to math.",
    ),
    # Analytical scenarios
    BenchmarkScenario(
        id="analytical_01",
        name="Comparative Analysis",
        category="analytical",
        query="Compare 2^10 with 10^2 using the calculator.",
        expected_tools=["calculator"],
        description="Comparative analysis requiring calculation.",
    ),
    BenchmarkScenario(
        id="analytical_02",
        name="Data Reasoning",
        category="analytical",
        query="If a train travels at 60 mph for 2.5 hours, how far does it go?",
        expected_tools=["calculator"],
        description="Physics word problem.",
    ),
]
