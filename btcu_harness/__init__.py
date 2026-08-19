"""
BTCU Harness - Balanced Ternary Cognitive Unit Harness

A cognitive architecture framework for LLM agents based on the
balanced ternary unit {-1, 0, +1} and the 19683-state space.
"""

__version__ = "0.1.0"
__author__ = "BTCU Harness Team"

from btcu_harness.core.btcu import BTCU, T, Z, O
from btcu_harness.core.encoding import encode, decode

__all__ = ["BTCU", "T", "Z", "O", "encode", "decode"]
