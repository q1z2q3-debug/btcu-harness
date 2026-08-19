"""
Balanced ternary operations for BTCU Harness.

All operations work on trit vectors of arbitrary length.
Each trit belongs to {-1, 0, +1}.

Core principle:
    -1 + 1 = 0

Opposite states entering the EMPTY state is the foundation of
creativity and third-choice generation.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from btcu_harness.core.btcu import T, Z, O, VALID_TRITS, is_valid_trit


def _assert_trit_vector(vector: Sequence[int], name: str = "vector") -> None:
    """Raise ValueError if any element is not a valid trit."""
    for i, v in enumerate(vector):
        if not is_valid_trit(v):
            raise ValueError(f"Invalid trit at {name}[{i}]: {v}")


def neg(vector: Sequence[int]) -> list[int]:
    """Negate every trit: YIN <-> YANG, EMPTY stays EMPTY."""
    _assert_trit_vector(vector)
    return [-v for v in vector]


def add(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """
    Add two balanced ternary vectors trit-wise with carry.

    Rules:
        1 + 1 = 2  -> write T, carry 1
        T + T = -2 -> write 1, carry T
        1 + T = 0  -> write 0, no carry

    The result may be one trit longer than the longest input.
    """
    _assert_trit_vector(a, "a")
    _assert_trit_vector(b, "b")

    max_len = max(len(a), len(b))
    result: list[int] = []
    carry: int = Z

    for i in range(max_len):
        av = a[i] if i < len(a) else Z
        bv = b[i] if i < len(b) else Z
        total = av + bv + carry

        if total >= 2:
            result.append(total - 3)
            carry = O
        elif total <= -2:
            result.append(total + 3)
            carry = T
        else:
            result.append(total)
            carry = Z

    if carry != Z:
        result.append(carry)

    return result


def sub(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """Subtract b from a: a - b = a + (-b)."""
    return add(a, neg(b))


def mul(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """
    Balanced ternary multiplication of two vectors.

    This is a simple digit-by-digit multiplication without carries,
    suitable for polarity coupling of cognitive states.

    For full numeric multiplication, use mul_full().
    """
    _assert_trit_vector(a, "a")
    _assert_trit_vector(b, "b")
    return [av * bv for av, bv in zip(a, b)]


def mul_full(a: Sequence[int], b: Sequence[int]) -> list[int]:
    """
    Full balanced ternary multiplication with carries.

    Treats both vectors as balanced ternary numbers (least significant
    trit first) and returns their product.
    """
    _assert_trit_vector(a, "a")
    _assert_trit_vector(b, "b")

    if len(a) == 0 or len(b) == 0:
        return [Z]

    result = [Z] * (len(a) + len(b))

    for i, av in enumerate(a):
        for j, bv in enumerate(b):
            result[i + j] += av * bv

    # Normalize carries
    normalized: list[int] = []
    carry = Z
    for value in result:
        total = value + carry
        # Convert arbitrary integers into balanced ternary with carry
        rem = ((total + 1) % 3) - 1
        carry = (total - rem) // 3
        normalized.append(rem)

    while carry != Z:
        rem = ((carry + 1) % 3) - 1
        carry = (carry - rem) // 3
        normalized.append(rem)

    # Trim trailing zeros (most significant trits)
    while len(normalized) > 1 and normalized[-1] == Z:
        normalized.pop()

    return normalized


def polarity_sum(vector: Sequence[int]) -> int:
    """Return the net polarity: sum of all trits in the vector."""
    _assert_trit_vector(vector)
    return sum(vector)


def similarity(a: Sequence[int], b: Sequence[int]) -> int:
    """
    Polarity similarity between two vectors.

    Each position contributes:
        same polarity  -> +1
        opposite       -> -1
        either is 0    ->  0

    Range: -n to +n for vectors of length n.
    """
    _assert_trit_vector(a, "a")
    _assert_trit_vector(b, "b")
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def hamming_distance(a: Sequence[int], b: Sequence[int]) -> int:
    """Number of positions where a and b differ."""
    _assert_trit_vector(a, "a")
    _assert_trit_vector(b, "b")
    n = min(len(a), len(b))
    return sum(1 for i in range(n) if a[i] != b[i])


def to_string(vector: Sequence[int]) -> str:
    """Render a trit vector as a compact string, most significant first."""
    _assert_trit_vector(vector)
    symbols = {T: "T", Z: "0", O: "1"}
    return "".join(symbols[v] for v in reversed(vector))


def from_string(text: str) -> list[int]:
    """Parse a compact trit string into a vector, least significant first."""
    symbols = {"T": T, "t": T, "-1": T, "0": Z, "1": O, "+": O}
    vector: list[int] = []
    for ch in reversed(text.strip()):
        if ch not in symbols:
            raise ValueError(f"Invalid trit character: {ch!r}")
        vector.append(symbols[ch])
    return vector
