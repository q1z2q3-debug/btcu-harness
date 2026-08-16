# API Reference — Decision

The `decision` module provides pathfinding and third-choice synthesis.

## `DecisionPathfinder`

Navigates between cognitive states.

```python
from btcu_harness.decision.pathfinder import DecisionPathfinder
from btcu_harness.core.state import CognitiveState

pf = DecisionPathfinder()

start = CognitiveState.from_index(0)      # ALL_YIN
end = CognitiveState.from_index(19682)    # ALL_YANG

path = pf.find_path(start, end)
# path.states → list of intermediate states
# path.steps → number of steps
# path.description → human-readable summary
```

### Path Types

| Method | Description |
|---|---|
| `find_path(a, b, prefer_void=False)` | Direct greedy path |
| `find_path(a, b, prefer_void=True)` | Route through all-VOID center |

### DecisionPath Properties

| Property | Type | Description |
|---|---|---|
| `states` | `list[CognitiveState]` | Intermediate states |
| `steps` | `int` | Number of transitions |
| `description` | `str` | Human-readable path summary |

## `ThirdChoiceGenerator`

Generates creative alternatives from binary conflicts.

```python
from btcu_harness.decision.third_choice import ThirdChoiceGenerator

gen = ThirdChoiceGenerator()

state_a = CognitiveState.from_values([1, 1, 1, 1, 1, 1, 1, 1, 1])
state_b = CognitiveState.from_values([-1, -1, -1, -1, -1, -1, -1, -1, -1])

candidates = gen.generate_all(state_a, state_b)
```

### Synthesis Strategies

| Strategy | Description | When Used |
|---|---|---|
| `void` | Preserve agreements, void conflicts | Default, maximum creativity |
| `fusion` | Choose committed over uncertain | 0 vs ±1 conflicts |
| `dominance_a` | Take A's values on half, void rest | Strong A preference |
| `dominance_b` | Take B's values on half, void rest | Strong B preference |
| `emergent` | Find novel equidistant neighbors | When void result is insufficient |

### ThirdChoiceCandidate Properties

| Property | Type | Description |
|---|---|---|
| `state` | `CognitiveState` | The synthesized state |
| `strategy` | `str` | Which strategy generated it |
| `equidistance` | `float` | Fairness score (0-1) |
| `memory_score` | `float` | Historical success rate |
| `self_alignment` | `float` | Personality fit |
| `void_ratio` | `float` | Creative potential (0-1) |
| `total_score` | `float` | Weighted composite (0-1) |

### Scoring Weights

| Dimension | Weight | Rationale |
|---|---|---|
| Equidistance | 0.25 | Fairness between A and B |
| Memory | 0.25 | Historical evidence |
| Self-alignment | 0.20 | Personality consistency |
| VOID ratio | 0.30 | Creative potential |

Candidates are sorted by `total_score` and deduplicated by state index.

## Usage Example

```python
from btcu_harness.decision.third_choice import ThirdChoiceGenerator
from btcu_harness.core.state import CognitiveState

gen = ThirdChoiceGenerator()

# Two opposing strategies
speed = CognitiveState.from_values([1, -1, -1, 1, -1, -1, 1, -1, -1])
quality = CognitiveState.from_values([-1, 1, -1, -1, -1, -1, -1, -1, 1])

candidates = gen.generate_all(speed, quality)

for c in candidates[:3]:
    print(f"{c.strategy:20s}  State #{c.state.index:5d}  "
          f"Score: {c.total_score:.2f}  VOID: {c.void_ratio:.0%}")
```
