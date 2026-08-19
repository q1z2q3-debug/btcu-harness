"""
BTCU Harness - Core Module

Balanced ternary primitive, operations, encoding, and 19683 state space.
"""

from btcu_harness.core.btcu import BTCU, T, Z, O
from btcu_harness.core.ternary import neg, add, sub, mul, similarity, hamming_distance
from btcu_harness.core.encoding import encode, decode
from btcu_harness.core.space import Space19683

__all__ = [
    "BTCU", "T", "Z", "O",
    "neg", "add", "sub", "mul", "similarity", "hamming_distance",
    "encode", "decode",
    "Space19683",
]
