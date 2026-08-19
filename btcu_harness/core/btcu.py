"""
BTCU - Balanced Ternary Cognitive Unit

The irreducible cognitive primitive of the harness:
    -1 = YIN  = negation, contraction, inhibition, retreat
     0 = EMPTY = transformation, creation, suspension, waiting
    +1 = YANG = affirmation, expansion, activation, advance

Core identity:
    -1 + 1 = 0

This equation means that opposite cognitive states, when they meet,
enter the EMPTY state. Emptiness is not absence but a creative field
where third choices can emerge.
"""

from enum import IntEnum
from typing import Final


class BTCU(IntEnum):
    """Balanced Ternary Cognitive Unit."""

    YIN = -1
    EMPTY = 0
    YANG = 1


# Canonical short aliases
T: Final[int] = BTCU.YIN.value
Z: Final[int] = BTCU.EMPTY.value
O: Final[int] = BTCU.YANG.value

# Valid trit set
VALID_TRITS: Final[tuple[int, ...]] = (T, Z, O)


def is_valid_trit(value: int) -> bool:
    """Return True when value is a legal trit."""
    return value in VALID_TRITS


def opposite(value: int) -> int:
    """Return the opposite trit: YIN <-> YANG, EMPTY stays EMPTY."""
    if not is_valid_trit(value):
        raise ValueError(f"Invalid trit: {value}")
    return -value


def to_symbol(value: int) -> str:
    """Render a trit as a human-readable symbol."""
    return {-1: "T", 0: "0", 1: "1"}[value]


def to_name(value: int) -> str:
    """Render a trit as a semantic name."""
    return {-1: "YIN", 0: "EMPTY", 1: "YANG"}[value]


def polarity_name(value: int) -> str:
    """Return a compact polarity label."""
    return {-1: "negative", 0: "neutral", 1: "positive"}[value]
