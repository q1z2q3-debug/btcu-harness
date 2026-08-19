"""
Balanced ternary encoding for the 19683-state space.

A nine-dimensional trit vector maps to a unique integer index in
[0, 19682]. The mapping is a linear shift from balanced ternary
{-1, 0, +1} to ordinary ternary {0, 1, 2}.

Special states:
    all YIN   = [-1]*9 -> index 0
    all EMPTY = [ 0]*9 -> index 9841
    all YANG  = [+1]*9 -> index 19682

The all-EMPTY state sits exactly at the center of the space.
"""

from __future__ import annotations

from typing import Sequence

from btcu_harness.core.btcu import T, Z, O, VALID_TRITS, is_valid_trit

# Default reference dimension
DEFAULT_DIM = 9

# Space size = 3^9 = 19683
SPACE_SIZE = 3**DEFAULT_DIM

# Index boundaries
MIN_INDEX = 0
MAX_INDEX = SPACE_SIZE - 1

# Center index: the all-EMPTY state
CENTER_INDEX = (SPACE_SIZE - 1) // 2

# Balanced ternary value range for nine trits
MIN_VALUE = -((SPACE_SIZE - 1) // 2)
MAX_VALUE = (SPACE_SIZE - 1) // 2


def _assert_valid_index(index: int) -> None:
    """Raise ValueError if index is outside the 19683 space."""
    if not isinstance(index, int):
        raise TypeError(f"Index must be int, got {type(index).__name__}")
    if index < MIN_INDEX or index > MAX_INDEX:
        raise ValueError(
            f"Index {index} out of range [{MIN_INDEX}, {MAX_INDEX}]"
        )


def _assert_valid_vector(vector: Sequence[int], dim: int = DEFAULT_DIM) -> None:
    """Raise ValueError if vector has wrong length or invalid trits."""
    if len(vector) != dim:
        raise ValueError(f"Vector length {len(vector)} != expected {dim}")
    for i, v in enumerate(vector):
        if not is_valid_trit(v):
            raise ValueError(f"Invalid trit at position {i}: {v}")


def encode(vector: Sequence[int]) -> int:
    """
    Encode a nine-dimensional balanced ternary vector to an integer index.

    The vector is expected least-significant-trit first.
    Mapping: d_i -> t_i = d_i + 1, then index = sum(t_i * 3^i).
    """
    _assert_valid_vector(vector)
    index = 0
    multiplier = 1
    for d in vector:
        t = d + 1  # -1->0, 0->1, +1->2
        index += t * multiplier
        multiplier *= 3
    return index


def decode(index: int) -> list[int]:
    """
    Decode an integer index back to a nine-dimensional trit vector.

    The returned vector is least-significant-trit first.
    """
    _assert_valid_index(index)
    vector: list[int] = []
    remaining = index
    for _ in range(DEFAULT_DIM):
        t = remaining % 3
        remaining //= 3
        d = t - 1  # 0->-1, 1->0, 2->+1
        vector.append(d)
    return vector


def balanced_value(vector: Sequence[int]) -> int:
    """
    Compute the signed balanced ternary value of a vector.

    value = sum(d_i * 3^i), ranging from -9841 to +9841.
    """
    _assert_valid_vector(vector)
    value = 0
    multiplier = 1
    for d in vector:
        value += d * multiplier
        multiplier *= 3
    return value


def index_to_balanced_value(index: int) -> int:
    """Convert an index to its balanced ternary value, centered on 0."""
    _assert_valid_index(index)
    return index - CENTER_INDEX


def balanced_value_to_index(value: int) -> int:
    """Convert a balanced ternary value back to an index."""
    if value < MIN_VALUE or value > MAX_VALUE:
        raise ValueError(f"Value {value} out of range [{MIN_VALUE}, {MAX_VALUE}]")
    return value + CENTER_INDEX


def mirror(index: int) -> int:
    """
    Return the mirrored index: negate every trit.

    For the balanced ternary encoding, mirroring maps index -> MAX_INDEX - index.
    """
    _assert_valid_index(index)
    return MAX_INDEX - index


def polarity(vector: Sequence[int]) -> int:
    """Net polarity: sum of all trits. Range -9 to +9."""
    _assert_valid_vector(vector)
    return sum(vector)


def empty_count(vector: Sequence[int]) -> int:
    """Number of EMPTY (0) trits in the vector."""
    _assert_valid_vector(vector)
    return sum(1 for v in vector if v == Z)


def is_center(vector: Sequence[int]) -> bool:
    """Return True if the vector is the all-EMPTY center state."""
    return all(v == Z for v in vector)


def is_extreme(vector: Sequence[int]) -> bool:
    """Return True if the vector is all-YIN or all-YANG."""
    return all(v == T for v in vector) or all(v == O for v in vector)


def to_symbol_string(vector: Sequence[int]) -> str:
    """Render the vector as a readable symbol string, most significant first."""
    _assert_valid_vector(vector)
    symbols = {T: "T", Z: "0", O: "1"}
    return "".join(symbols[v] for v in reversed(vector))
