# Quickstart

Get BTCU Harness running in 5 minutes.

## Prerequisites

- Python 3.10+
- pip

## Installation

```bash
pip install btcu-harness
```

For this tutorial, we use **callback mode** — no API key required. In production, swap the callback for a real LLM bridge.

## Step 1: Create an Agent

```python
from btcu_harness.agent import BTCUAgent
from btcu_harness.llm.bridge import LLMBridge

agent = BTCUAgent(growth_stage="school")
```

## Step 2: Initialize a Project

```python
agent.init_project(
    domain="custom",
    dim_labels=[
        "Speed", "Quality", "Cost", "Risk", "Innovation",
        "Team", "Deadline", "Scope", "Impact",
    ],
)
```

The agent now has a 19,683-state cognitive space structured by your 9 dimensions. Each dimension is a `Trit` with three states: YIN(-1), VOID(0), YANG(+1).

## Step 3: Attach a Demo LLM Bridge

```python
import json

def demo_llm(prompt: str) -> str:
    """Simulate an LLM that evaluates 9 dimensions."""
    assessments = []
    for i in range(9):
        value = [1, -1, 0, 1, 0, -1, 1, 0, 1][i]
        assessments.append({
            "dimension": f"d{i}",
            "value": value,
            "reason": f"demo reason {i}",
        })
    return json.dumps({"assessments": assessments})

agent.llm_bridge = LLMBridge(callback=demo_llm)
```

In production, replace with:

```python
agent.llm_bridge = LLMBridge(
    provider="openai",
    api_key="sk-...",
    model="gpt-4o-mini",
)
```

## Step 4: Process Your First Input

```python
response = agent.process("Should we prioritize speed?")

print(f"State:       #{response.current_state.index}")
print(f"Values:      {response.current_state.values}")
print(f"Polarity:    {response.current_state.polarity}")
print(f"YIN:         {response.current_state.yin_count}")
print(f"VOID:        {response.current_state.void_count}")
print(f"YANG:        {response.current_state.yang_count}")
print(f"Alignment:   {response.self_alignment:.1%}")
```

## Step 5: Generate Third Choices

When you have two conflicting states, BTCU generates creative alternatives:

```python
from btcu_harness.core.state import CognitiveState

# Two opposing states
speed = CognitiveState.from_values([1, -1, -1, 1, -1, -1, 1, -1, -1])
quality = CognitiveState.from_values([-1, 1, -1, -1, -1, -1, -1, -1, 1])

candidates = agent.third_choice_gen.generate_all(speed, quality)

for c in candidates[:3]:
    print(f"  Strategy: {c.strategy:20s}  "
          f"State #{c.state.index:5d}  "
          f"Score: {c.total_score:.2f}  "
          f"VOID: {c.void_ratio:.0%}")
```

## Step 6: Save and Restore

```python
# Save everything
agent.save()

# Restore in a new session
new_agent = BTCUAgent()
new_agent.load()
print(f"Restored trajectory: {new_agent.trajectory.length} points")
```

## Step 7: Explore the Space

```python
from btcu_harness.core.state import CognitiveState

# Center of the universe
void = CognitiveState.from_index(9841)
print(f"VOID state: #{void.index}, polarity={void.polarity}")

# Navigate neighbors
for neighbor in void.neighbors()[:5]:
    dist = void.distance(neighbor)
    print(f"  Neighbor #{neighbor.index} — distance={dist}")

# Opposite of any state
yang = CognitiveState.from_index(19682)
yin = yang.opposite()
print(f"Opposite of #{yang.index} is #{yin.index}")
```

## Next Steps

- [Architecture Overview](architecture.md) — Understand the full system
- [Philosophy](philosophy.md) — Dao, emptiness, and information theory
- [REST API](rest_api.md) — Serve BTCU over HTTP
- [Paper](BTCU_Harness_Paper_v1.0.md) — Full academic reference

## Full Script

```bash
python examples/quickstart.py
```

Runs all of the above — no API key needed.
