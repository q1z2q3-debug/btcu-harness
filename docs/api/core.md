# API Reference — Core

The `core` module defines the fundamental cognitive primitives of BTCU.

## `Trit`

The balanced ternary cognitive unit.

```python
from btcu_harness.core.trit import Trit

t = Trit(1)       # YANG
t = Trit(-1)      # YIN
t = Trit(0)       # VOID
t = Trit(Trit(1)) # from another Trit
```

### Properties

| Property | Type | Description |
|---|---|---|
| `value` | `int` | -1, 0, or +1 |
| `name` | `str` | "YIN", "VOID", or "YANG" |
| `chinese_name` | `str` | "阴", "空", "阳" |
| `is_yin` | `bool` | `value == -1` |
| `is_void` | `bool` | `value == 0` |
| `is_yang` | `bool` | `value == 1` |
| `is_polarized` | `bool` | `abs(value) == 1` |

### Operations

| Operation | Example | Result |
|---|---|---|
| Negation | `Trit(1).negate()` | `Trit(-1)` |
| Addition | `Trit(1) + Trit(-1)` | `Trit(0)` (the axiom) |
| Multiplication | `Trit(-1) * Trit(1)` | `Trit(-1)` |
| Boolean | `bool(Trit(0))` | `False` |
| String | `str(Trit(1))` | "+" |

## `CognitiveState`

A 9-dimensional ternary vector.

```python
from btcu_harness.core.state import CognitiveState, NUM_DIMENSIONS, SPACE_SIZE

# From 9 trit values
state = CognitiveState.from_values([1, -1, 0, 1, 0, -1, 1, 0, 1])

# From index (0-19682)
state = CognitiveState.from_index(9841)  # all-VOID
```

### Properties

| Property | Type | Range | Description |
|---|---|---|---|
| `index` | `int` | [0, 19682] | Unique integer identifier |
| `values` | `tuple` | 9 ints | [-1,0,1] × 9 |
| `polarity` | `int` | [-9, 9] | Sum of dimension values |
| `intensity` | `int` | [0, 9] | Absolute polarity |
| `yin_count` | `int` | [0, 9] | Number of -1 dimensions |
| `void_count` | `int` | [0, 9] | Number of 0 dimensions |
| `yang_count` | `int` | [0, 9] | Number of +1 dimensions |
| `is_empty` | `bool` | — | `void_count == 9` |
| `is_polarized` | `bool` | — | `intensity > 0` |

### Methods

| Method | Signature | Description |
|---|---|---|
| `opposite()` | `→ CognitiveState` | Mirror (YIN ↔ YANG, VOID invariant) |
| `distance(other)` | `→ int` | Sum of per-dimension differences, [0, 18] |
| `neighbors()` | `→ list[CognitiveState]` | Up to 18 adjacent states |

### Special States

| State | Index | Values | Property |
|---|---|---|---|
| ALL_YIN | 0 | [-1, -1, ..., -1] | Opposite: ALL_YANG |
| ALL_VOID | 9841 | [0, 0, ..., 0] | Opposite: itself |
| ALL_YANG | 19682 | [+1, +1, ..., +1] | Opposite: ALL_YIN |

## `CognitiveSpace`

Topology of the 19,683-state space.

```python
from btcu_harness.core.space import CognitiveSpace

space = CognitiveSpace()
state = space.get_state(100)          # state at index 100
neighbors = space.get_neighbors(100)   # adjacent states
```

### Methods

| Method | Signature | Description |
|---|---|---|
| `get_state(index)` | `→ CognitiveState` | State by index |
| `get_neighbors(index)` | `→ list[CognitiveState]` | Adjacent states |
| `shortest_path(a, b)` | `→ list[CognitiveState]` | Greedy BFS path |
| `distance(a, b)` | `→ int` | Cognitive distance |
| `opposite(index)` | `→ int` | Opposite state index (19682 - index) |
| `all_states()` | `→ Generator[CognitiveState]` | All 19,683 states |
