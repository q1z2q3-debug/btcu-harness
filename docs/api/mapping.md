# API Reference — Mapping

The `mapping` module bridges between human concepts and the 19,683-state cognitive space.

## `DimensionAdapter`

Adapts dimension labels per project.

```python
from btcu_harness.mapping.dimension_adapter import DimensionAdapter

adapter = DimensionAdapter()

# Use a predefined domain
dim_set = adapter.use_example("default")
# Dimensions: ["past", "present", "future", "inner", "middle", "outer", "cause", "condition", "effect"]

# Custom dimensions
dim_set = adapter.create(["Speed", "Quality", "Cost", "Risk", "Innovation",
                           "Team", "Deadline", "Scope", "Impact"])

# Lock — prevents further modification
adapter.lock(dim_set)
```

### Predefined Domains

| Domain | Dimensions |
|---|---|
| `default` | Time + Space + Cause (philosophical) |
| `agent` | Task, Tool, Risk, Intent, Cost, Innovation, Explainability, Timeliness, Value |
| `decision` | Urgency, Importance, Resources, Risk, Team, Feasibility, Strategy, Time, Impact |
| `education` | Mastery, Motivation, Load, Practice, Innovation, Collaboration, Reflection, Strategy, Mindset |

### DimensionSet Properties

| Property | Type | Description |
|---|---|---|
| `labels` | `list[str]` | 9 dimension labels |
| `locked` | `bool` | Whether the set is immutable |

## `InputProjector`

Projects natural language inputs onto cognitive states.

```python
from btcu_harness.mapping.projector import InputProjector
from btcu_harness.llm.bridge import LLMBridge

projector = InputProjector(dim_set, growth_stage="school")

# With real LLM
bridge = LLMBridge(provider="openai", api_key="sk-...")
result = projector.project("Should we prioritize speed?", llm_callback=bridge)

# With callback
def mock_llm(prompt: str) -> str:
    return '{"assessments": [...]}'

result = projector.project("text", llm_callback=mock_llm)
```

### ProjectionResult

| Property | Type | Description |
|---|---|---|
| `state` | `CognitiveState` | Projected state |
| `dimension_assessments` | `dict[str, str]` | Per-dimension reasoning |
| `confidence` | `float` | Confidence score (0-1) |
| `source` | `str` | "llm", "pattern", "hybrid", or "llm_parse_error" |

### Growth Stage Behavior

| Stage | Projection Method |
|---|---|
| school | Always calls LLM |
| internalize | Pattern match first, LLM fallback |
| graduate | Pattern primary, LLM only for novel inputs |

## `PatternLearner`

Accumulates input→state mappings to reduce LLM dependency.

```python
from btcu_harness.mapping.pattern_learner import PatternLearner

learner = PatternLearner()

# Learn a mapping
learner.learn("speed over quality", state, source="llm", confidence=0.8)

# Match future inputs
match = learner.match("prioritize speed")  # (pattern, similarity) or None
```

### Properties

| Property | Description |
|---|---|
| `total_lookups` | Total pattern lookup attempts |
| `total_reuses` | Successful pattern matches |
| `reuse_rate` | reuses / lookups (0-1) |

### Matching

Pattern matching uses keyword overlap with configurable threshold (default 0.7). When `reuse_rate` approaches 1.0, the agent approaches full cognitive autonomy.
