"""Benchmark suite for BTCU Harness.

Evaluates BTCU against baseline approaches across multiple dimensions:
- Decision consistency (structured vs unstructured)
- Third-choice quality (creativity from binary conflicts)
- Token economy (LLM call reduction over time)
- Path quality (navigation through cognitive space)
"""

from .runner import BenchmarkRunner
from .report import BenchmarkReport

__all__ = ["BenchmarkRunner", "BenchmarkReport"]
