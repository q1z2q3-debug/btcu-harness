"""Benchmark suite for BTCU Harness.

Evaluates BTCU against baseline approaches across multiple dimensions:
- Decision consistency (structured vs unstructured)
- Third-choice quality (creativity from binary conflicts)
- Token economy (LLM call reduction over time)
- Path quality (navigation through cognitive space)
"""

from .report import BenchmarkReport
from .runner import BenchmarkRunner
from .token_economy import SimulationResult, TokenEconomySimulator

__all__ = ["BenchmarkRunner", "BenchmarkReport", "SimulationResult", "TokenEconomySimulator"]
