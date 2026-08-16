"""
Trit: The fundamental cognitive unit of BTCU Harness.

Three states:
    YIN  (-1)  - deny, contract, suppress, retreat
    VOID ( 0)  - transform, create, suspend, wait
    YANG (+1)  - affirm, expand, activate, advance

Axiom: -1 + 1 = 0
    The interaction of opposing cognitive states enters the void state.
    The void is the gateway to creation and third choice.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Union


class TritEnum(IntEnum):
    """Named constants for trit values."""

    YIN = -1
    VOID = 0
    YANG = 1


# Type alias
TritValue = Union[int, TritEnum, "Trit"]

# Canonical values
VALID_VALUES = frozenset({-1, 0, 1})


class Trit:
    """
    Balanced ternary cognitive unit.

    The only closed primitive in the system. All higher-order structures
    (states, spaces, memory, decisions) are built from Trit operations.

    Examples:
        >>> Trit(1) + Trit(-1)
        Trit(0)  # YANG + YIN = VOID (the axiom)

        >>> Trit(1).negate()
        Trit(-1)  # YANG -> YIN (symmetric flip, zero cost)

        >>> Trit(0).negate()
        Trit(0)   # VOID is invariant under negation
    """

    __slots__ = ("_value",)

    # Type annotation for slot (helps type checkers)
    _value: int

    def __init__(self, value: TritValue) -> None:
        """
        Create a Trit from int, TritEnum, or another Trit.

        Args:
            value: -1, 0, or 1 (or TritEnum / Trit).

        Raises:
            ValueError: If value is not in {-1, 0, 1}.
        """
        if isinstance(value, Trit):
            value = value._value
        elif isinstance(value, TritEnum):
            value = int(value)
        else:
            value = int(value)

        if value not in VALID_VALUES:
            raise ValueError(
                f"Trit value must be in {{-1, 0, 1}}, got {value}"
            )
        self._value = value

    @property
    def value(self) -> int:
        """Raw integer value."""
        return self._value

    @property
    def name(self) -> str:
        """Human-readable name."""
        if self._value == -1:
            return "YIN"
        elif self._value == 0:
            return "VOID"
        else:
            return "YANG"

    @property
    def chinese_name(self) -> str:
        """Chinese name."""
        if self._value == -1:
            return "\u9634"  # 阴
        elif self._value == 0:
            return "\u7a7a"  # 空
        else:
            return "\u9633"  # 阳

    # --- Core operations ---

    def negate(self) -> "Trit":
        """
        Symmetric flip: YIN <-> YANG, VOID stays VOID.

        This is the fundamental operation that makes balanced ternary
        symmetric: negation is a zero-cost identity transform.

        YANG -> YIN
        YIN  -> YANG
        VOID -> VOID (invariant)
        """
        return Trit(-self._value)

    def __neg__(self) -> "Trit":
        """Unary negation operator."""
        return self.negate()

    def __pos__(self) -> "Trit":
        """Unary positive (identity)."""
        return Trit(self._value)

    def add(self, other: TritValue) -> "Trit":
        """
        Trit addition with balanced ternary wrapping.

        The core axiom: -1 + 1 = 0 (opposing forces resolve to void).

        Full truth table:
            -1 + -1 = -1  (YIN saturation)
            -1 +  0 = -1
            -1 +  1 =  0  (THE AXIOM)
             0 + -1 = -1
             0 +  0 =  0  (VOID is absorbing)
             0 +  1 =  1
             1 + -1 =  0  (THE AXIOM)
             1 +  0 =  1
             1 +  1 =  1  (YANG saturation)

        VOID is an absorbing element: once you reach void,
        addition cannot push you out. Void is a stable attractor
        unless an external force (dimension change) acts.
        """
        other_val: int = Trit(other)._value
        return Trit(self._value + other_val)

    def __add__(self, other: TritValue) -> "Trit":
        return self.add(other)

    def multiply(self, other: TritValue) -> "Trit":
        """
        Trit multiplication (standard sign multiplication).

            -1 * -1 =  1
            -1 *  0 =  0
            -1 *  1 = -1
             0 *  x =  0  (VOID annihilates)
             1 * -1 = -1
             1 *  0 =  0
             1 *  1 =  1

        VOID is the annihilator: any state multiplied by void becomes void.
        """
        return Trit(self._value * Trit(other).value)

    def __mul__(self, other: TritValue) -> "Trit":
        return self.multiply(other)

    # --- Logical operations ---

    def is_yin(self) -> bool:
        return self._value == -1

    def is_void(self) -> bool:
        return self._value == 0

    def is_yang(self) -> bool:
        return self._value == 1

    def is_polarized(self) -> bool:
        """True if not void (has definite polarity)."""
        return self._value != 0

    # --- Encoding ---

    def encode(self) -> int:
        """
        Encode to non-negative integer for indexing.

        -1 (YIN)  -> 0
         0 (VOID) -> 1
        +1 (YANG) -> 2

        This mapping enables 0-19682 indexing for the 19683 state space.
        """
        return self._value + 1

    @classmethod
    def decode(cls, code: int) -> "Trit":
        """Decode from non-negative integer (inverse of encode)."""
        if code not in (0, 1, 2):
            raise ValueError(f"Trit code must be in {{0, 1, 2}}, got {code}")
        return cls(code - 1)

    # --- Comparison ---

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Trit):
            return self._value == other._value
        if isinstance(other, int):
            return self._value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __lt__(self, other: TritValue) -> bool:
        return self._value < Trit(other).value

    def __le__(self, other: TritValue) -> bool:
        return self._value <= Trit(other).value

    def __gt__(self, other: TritValue) -> bool:
        return self._value > Trit(other).value

    def __ge__(self, other: TritValue) -> bool:
        return self._value >= Trit(other).value

    # --- Representation ---

    def __repr__(self) -> str:
        return f"Trit({self._value})"

    def __str__(self) -> str:
        symbols = {-1: "T", 0: "0", 1: "1"}
        return symbols[self._value]

    def __int__(self) -> int:
        return self._value

    def __bool__(self) -> bool:
        """VOID is falsy, polarized states are truthy."""
        return self._value != 0


# Convenience constants
YIN = Trit(-1)
VOID = Trit(0)
YANG = Trit(1)
