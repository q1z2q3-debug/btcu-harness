# API Reference — Memory

The `memory` module implements a four-layer memory ecology.

## `MemoryEcology`

Central memory manager coordinating all memory subsystems.

```python
from btcu_harness.memory.ecology import MemoryEcology

ecology = MemoryEcology()
```

### Key Methods

| Method | Description |
|---|---|
| `remember(event: CognitiveEvent)` | Record a cognitive event |
| `recall(state: CognitiveState)` | Retrieve memory for a state |
| `decay_all()` | Apply time-based decay to all memories |
| `sense_making()` | Discover emergent cognitive patterns |

### Recall Returns

```python
memory = ecology.recall(state)
# Returns dict with:
#   - state_memory (StateMemory)
#   - resonance (list of related states)
#   - transitions (list of corridors)
#   - suggestions (list of text recommendations)
```

## `StateMemory`

Episodic memory — one "room" per cognitive state.

```python
from btcu_harness.memory.state_memory import StateMemory

mem = StateMemory()
mem.record_visit(visit_record)
mem.add_insight("This state indicates high risk tolerance")
mem.boost_activation()
```

### Properties

| Property | Description |
|---|---|
| `visit_count` | Number of times this state has been visited |
| `insights` | List of deduplicated textual insights |
| `activation` | Current activation level (float, 0.0-1.0) |
| `resonance_links` | Dict of {state_index: strength} |
| `suppressed_decisions` | List of failed decisions to avoid |

## `TransitionMemory`

Procedural memory — corridors between states.

```python
from btcu_harness.memory.transition_memory import TransitionMemory, TransitionRecord

trans = TransitionMemory()
trans.record_transition(TransitionRecord(...))
```

### Emergent Properties

| Property | Condition | Meaning |
|---|---|---|
| `is_pathway` | traverse_count ≥ 5 | A formed cognitive habit |
| `is_virtue` | pathway AND success_rate ≥ 0.7 | Reliable cognitive path |
| `is_trap` | pathway AND success_rate ≤ 0.3 | Repeatedly failing path |

## `CognitiveTrajectory`

Biographical memory — the agent's cognitive journey.

```python
from btcu_harness.memory.trajectory import CognitiveTrajectory

traj = CognitiveTrajectory(max_points=10000)
traj.record(state=my_state, context="Analyzed investment risk", trigger="process")
```

### Analysis Methods

| Method | Returns | Description |
|---|---|---|
| `velocity()` | `float` | Average distance per step |
| `cognitive_center()` | `CognitiveState` | Weighted average state |
| `drift(window=50)` | `int` | Distance between first/second half centers |
| `detect_clusters()` | `list[CognitiveCluster]` | Frequently visited regions |
| `detect_cycles()` | `list[CognitiveCycle]` | Repeating state sequences |
| `state_sequence()` | `list[int]` | Ordered list of visited state indices |

### Properties

| Property | Description |
|---|---|
| `length` | Number of trajectory points |
| `unique_states` | Count of distinct states visited |
| `coverage` | unique_states / 19683 |
| `explore_ratio()` | unique / total (1.0 = all unique) |

## `CognitiveClimate`

Long-term trend analysis of the trajectory.

```python
from btcu_harness.memory.climate import CognitiveClimate

climate = CognitiveClimate(window=20)
climate.snapshot(state)
report = climate.report()
```

### Metrics

| Metric | Description |
|---|---|
| `polarity_trend` | Positive = becoming more YANG |
| `exploration_phase` | "expanding", "consolidating", or "stagnant" |
| `drift_magnitude` | Whether cognitive center is moving |
| `dominant_period` | Most frequent cycle length |
| `rhythm_regularity` | Fraction of steps matching dominant period |

### Climate Zones

Hot regions of cognitive activity — clusters of recently active states.
