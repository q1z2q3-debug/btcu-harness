"""
CognitiveState: A 9-dimensional ternary vector representing one cognitive state.

Each dimension is a Trit {-1, 0, +1}, producing 3^9 = 19683 total states.
States are encoded as integers in [0, 19682] for efficient indexing.

The dimension labels are flexible - they are adapted per project and then
fixed. The structure (9 trits) is invariant; the semantics are emergent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Sequence, Tuple

from .trit import Trit, TritValue, YIN, VOID, YANG


# Total number of dimensions (invariant structural constant)
NUM_DIMENSIONS = 9

# Total state space size
SPACE_SIZE = 3 ** NUM_DIMENSIONS  # 19683

# Weight for each dimension position (low to high)
WEIGHTS = tuple(3 ** i for i in range(NUM_DIMENSIONS))
# (1, 3, 9, 27, 81, 243, 729, 2187, 6561)

# Special state indices
ALL_YIN_INDEX = 0         # [-1,-1,-1,-1,-1,-1,-1,-1,-1]
ALL_VOID_INDEX = 9841     # [0,0,0,0,0,0,0,0,0]
ALL_YANG_INDEX = 19682    # [+1,+1,+1,+1,+1,+1,+1,+1,+1]


@dataclass(frozen=True)
class CognitiveState:
    """
    A point in the 19683-dimensional cognitive state space.

    Defined by exactly 9 Trit values. Immutable and hashable.

    The dimension labels (what each position means) are NOT stored in
    the state itself - they belong to the project/space configuration.
    The state is pure structure; semantics are emergent.

    Examples:
        >>> s = CognitiveState([1, 0, -1, 1, 0, 0, -1, 1, -1])
        >>> s.index
        14598

        >>> s.opposite().index
        5084

        >>> CognitiveState.from_index(9841)
        CognitiveState([0, 0, 0, 0, 0, 0, 0, 0, 0])  # ALL_VOID
    """

    dims: Tuple[Trit, ...]

    def __post_init__(self) -> None:
        if len(self.dims) != NUM_DIMENSIONS:
            raise ValueError(
                f"CognitiveState requires exactly {NUM_DIMENSIONS} dimensions, "
                f"got {len(self.dims)}"
            )

    # --- Construction ---

    @classmethod
    def from_values(cls, values: Sequence[int]) -> "CognitiveState":
        """Create from a sequence of integers in {-1, 0, 1}."""
        return cls(tuple(Trit(v) for v in values))

    @classmethod
    def from_index(cls, index: int) -> "CognitiveState":
        """
        Decode a state index [0, 19682] into a CognitiveState.

        Mapping: -1 -> 0, 0 -> 1, +1 -> 2 (standard ternary decoding)
        """
        if not 0 <= index < SPACE_SIZE:
            raise ValueError(
                f"State index must be in [0, {SPACE_SIZE - 1}], got {index}"
            )
        digits: List[Trit] = []
        n = index
        for _ in range(NUM_DIMENSIONS):
            digit = n % 3
            n //= 3
            digits.append(Trit.decode(digit))
        return cls(tuple(digits))

    @classmethod
    def all_yin(cls) -> "CognitiveState":
        """The extreme negative state: all dimensions YIN."""
        return cls(tuple(YIN for _ in range(NUM_DIMENSIONS)))

    @classmethod
    def all_void(cls) -> "CognitiveState":
        """The void state: all dimensions VOID (index 9841)."""
        return cls(tuple(VOID for _ in range(NUM_DIMENSIONS)))

    @classmethod
    def all_yang(cls) -> "CognitiveState":
        """The extreme positive state: all dimensions YANG."""
        return cls(tuple(YANG for _ in range(NUM_DIMENSIONS)))

    @classmethod
    def random(cls) -> "CognitiveState":
        """Generate a random state (uniform over 19683)."""
        import random
        return cls.from_index(random.randint(0, SPACE_SIZE - 1))

    # --- Properties ---

    @property
    def index(self) -> int:
        """
        Encode this state to an integer in [0, 19682].

        Mapping: -1 -> 0, 0 -> 1, +1 -> 2 (standard ternary encoding)
        """
        result = 0
        for i, dim in enumerate(self.dims):
            result += dim.encode() * WEIGHTS[i]
        return result

    @property
    def values(self) -> Tuple[int, ...]:
        """Raw integer values of each dimension."""
        return tuple(d.value for d in self.dims)

    @property
    def yin_count(self) -> int:
        """Number of YIN (-1) dimensions."""
        return sum(1 for d in self.dims if d.is_yin())

    @property
    def void_count(self) -> int:
        """Number of VOID (0) dimensions."""
        return sum(1 for d in self.dims if d.is_void())

    @property
    def yang_count(self) -> int:
        """Number of YANG (+1) dimensions."""
        return sum(1 for d in self.dims if d.is_yang())

    @property
    def polarity(self) -> int:
        """
        Net polarity: sum of all dimension values.

        Range: [-9, +9]
        -9 = extreme YIN, 0 = balanced/void-dominant, +9 = extreme YANG
        """
        return sum(d.value for d in self.dims)

    @property
    def intensity(self) -> int:
        """
        Cognitive intensity: absolute polarity.

        0 = fully void/open, 9 = fully polarized (either direction).
        Higher intensity means more decisive cognition.
        """
        return abs(self.polarity)

    @property
    def is_void_dominant(self) -> bool:
        """True if VOID is the most common state across dimensions."""
        return self.void_count >= max(self.yin_count, self.yang_count)

    # --- Core operations ---

    def opposite(self) -> "CognitiveState":
        """
        Mirror state: every dimension flipped.

        YIN <-> YANG, VOID -> VOID.

        This is the "cuo gua" (opposite hexagram) operation.
        In balanced ternary, it's simply negating each dimension.
        The index of the opposite state is: 19682 - self.index
        """
        return CognitiveState(tuple(d.negate() for d in self.dims))

    def distance(self, other: "CognitiveState") -> int:
        """
        Cognitive distance: sum of per-dimension differences.

        Each dimension: 0 if same, 1 if adjacent (-1/0 or 0/+1), 2 if opposite.

        Range: [0, 18]
        0 = identical states
        18 = exact opposites (every dimension flipped)
        """
        return sum(
            abs(a.value - b.value) for a, b in zip(self.dims, other.dims)
        )

    def neighbors(self) -> List["CognitiveState"]:
        """
        All states reachable by changing exactly one dimension by one step.

        A dimension can change: -1<->0 or 0<->+1 (not -1<->+1 directly).

        Returns up to 18 neighbors (2 possible changes x 9 dimensions).
        """
        result = []
        for i, dim in enumerate(self.dims):
            val = dim.value
            # Can we move toward YIN?
            if val > -1:
                new_dims = list(self.dims)
                new_dims[i] = Trit(val - 1)
                result.append(CognitiveState(tuple(new_dims)))
            # Can we move toward YANG?
            if val < 1:
                new_dims = list(self.dims)
                new_dims[i] = Trit(val + 1)
                result.append(CognitiveState(tuple(new_dims)))
        return result

    def diff_dimensions(self, other: "CognitiveState") -> List[int]:
        """Indices of dimensions that differ from other."""
        return [
            i for i, (a, b) in enumerate(zip(self.dims, other.dims))
            if a != b
        ]

    def with_dimension(self, index: int, value: TritValue) -> "CognitiveState":
        """Return a copy with one dimension changed."""
        new_dims = list(self.dims)
        new_dims[index] = Trit(value)
        return CognitiveState(tuple(new_dims))

    # --- Representation ---

    def __repr__(self) -> str:
        vals = ", ".join(str(d) for d in self.dims)
        return f"CognitiveState([{vals}])"

    def __str__(self) -> str:
        """Compact string: T0-1001-0 (T=YIN, 0=VOID, 1=YANG)."""
        return "".join(str(d) for d in self.dims)

    def __getitem__(self, index: int) -> Trit:
        return self.dims[index]

    def __iter__(self) -> Iterator[Trit]:
        return iter(self.dims)

    def __len__(self) -> int:
        return NUM_DIMENSIONS

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CognitiveState):
            return self.dims == other.dims
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.dims)
