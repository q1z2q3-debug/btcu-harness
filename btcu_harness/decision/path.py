"""
BTCU Harness - State Transition Path

Decision is the generation of a legal path from a current state
to a target state in the 19683 space.

A single legal step moves one trit by one level:
    -1 -> 0 -> +1
    +1 -> 0 -> -1
No direct jump from -1 to +1 without passing through 0.
"""

from __future__ import annotations

from typing import Sequence

from btcu_harness.core.btcu import T, Z, O, is_valid_trit
from btcu_harness.core.encoding import DEFAULT_DIM, encode, decode


def is_legal_step(a: Sequence[int], b: Sequence[int]) -> bool:
    """
    Return True when moving from vector a to vector b is a legal
    single step: exactly one trit changed, and the change is by one.
    """
    if len(a) != len(b):
        return False

    changed = 0
    for av, bv in zip(a, b):
        if av == bv:
            continue
        changed += 1
        if changed > 1:
            return False
        if abs(av - bv) != 1:
            return False
    return changed == 1


def generate_path(
    from_state: int,
    to_state: int,
    max_steps: int = 18,
) -> list[int]:
    """
    Generate a legal path of state indices from from_state to to_state.

    Uses a per-position trit-by-trit walk that always passes through 0
    when moving between -1 and +1. Returns the sequence of indices
    including the source and target.
    """
    src = decode(from_state)
    dst = decode(to_state)

    path = [from_state]
    current = src.copy()

    for i in range(len(current)):
        while current[i] != dst[i]:
            if current[i] < dst[i]:
                current[i] += 1
            else:
                current[i] -= 1
            path.append(encode(current))
            if len(path) > max_steps:
                return path

    if path[-1] != to_state:
        path.append(to_state)

    return path
