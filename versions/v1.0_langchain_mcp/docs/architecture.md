# Architecture Overview

BTCU Harness is organized into six layers, each with a distinct cognitive responsibility.

## System Architecture

```
┌─────────────────────────────────────────────────┐
│  BTCUAgent (orchestrator)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ Projector│ │  Self    │ │ ThirdChoiceGen   ││
│  │ (mapping)│ │  Layer   │ │ (decision)       ││
│  └──────────┘ └──────────┘ └──────────────────┘│
│  ┌──────────────────────────────────────────────┤
│  │         MemoryEcology                         ││
│  │  ┌────────┐ ┌──────────┐ ┌────────────────┐││
│  │  │ State  │ │Transition│ │  Trajectory    │││
│  │  │Memory  │ │ Memory   │ │  (biography)   │││
│  │  └────────┘ └──────────┘ └────────────────┘││
│  │  ┌────────────────────────────────────────┐││
│  │  │          CognitiveClimate              │││
│  │  └────────────────────────────────────────┘││
│  └──────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ Pattern  │ │   LLM    │ │  Persistence     ││
│  │ Learner  │ │  Bridge  │ │  Layer           ││
│  └──────────┘ └──────────┘ └──────────────────┘│
└─────────────────────────────────────────────────┘
         │                        │
         v                        v
   CognitiveSpace            LLM (OpenAI/Claude/Gemini)
   (19,683 states)
```

## Layer-by-Layer

### Core Layer

**Files**: `core/trit.py`, `core/state.py`, `core/space.py`

The foundation of BTCU. Three classes with no dependencies on anything above them:

| Class | Purpose |
|---|---|
| `Trit` | {-1, 0, +1} with arithmetic, negation, and encoding |
| `CognitiveState` | 9-dimensional ternary vector, index 0-19682 |
| `CognitiveSpace` | Topology: distance, neighbors, paths, opposition |

Key property: `CognitiveState` is immutable and hashable — it can be used as a dictionary key and stored in sets.

### Mapping Layer

**Files**: `mapping/dimension_adapter.py`, `mapping/projector.py`, `mapping/pattern_learner.py`

Maps between the human world and the 19,683-state space:

| Class | Purpose |
|---|---|
| `DimensionAdapter` | Adapts 9 dimension labels per project, then locks them |
| `InputProjector` | Projects natural language inputs onto cognitive states |
| `PatternLearner` | Accumulates input→state mappings to reduce LLM calls |

The projector has three modes based on growth stage:
- **school**: always calls LLM
- **internalize**: pattern match first, LLM fallback
- **graduate**: pattern primary, LLM only for genuinely unknown inputs

### Memory Layer

**Files**: `memory/ecology.py`, `memory/state_memory.py`, `memory/transition_memory.py`, `memory/trajectory.py`, `memory/climate.py`

Five memory subsystems forming a four-layer ecology:

| Memory | Implementation | Capacity | Biological Analog |
|---|---|---|---|
| Episodic | `StateMemory` + `VisitRecord` | 19,683 rooms × 1,000 visits | Episodic memory |
| Procedural | `TransitionMemory` + `TransitionRecord` | Unbounded × 500 | Procedural memory |
| Capability | `PatternLearner` + `Pattern` | Unbounded | Semantic memory |
| Biographical | `CognitiveTrajectory` | 10,000 points (configurable) | Autobiographical memory |

All memories support:
- **Decay**: Activation decreases over time (multiplicative decay factor)
- **Resonance**: Nearby states get activation boosts when one is visited
- **Sense-making**: Emergent pattern detection (attractors, virtues, traps, blind spots)

### Decision Layer

**Files**: `decision/pathfinder.py`, `decision/third_choice.py`

Two decision-making systems:

| Class | Purpose |
|---|---|
| `DecisionPathfinder` | Finds navigation paths between states (direct or via void) |
| `ThirdChoiceGenerator` | Generates creative alternatives from binary conflicts |

Third Choice Generator implements five strategies:
1. **void** — preserve agreements, void conflicts
2. **fusion** — choose committed positions over uncertainty
3. **dominance_a/b** — lean toward one side
4. **emergent** — find novel equidistant states

Candidates are scored on: equidistance (25%), memory (25%), self-alignment (20%), void ratio (30%).

### Self Layer

**File**: `self_layer/__init__.py`

Implements the Dilts Logical Levels model adapted for BTCU:

| Level | Weight | Stability |
|---|---|---|
| Environment | 0.5 | Fast |
| Behavior | 1.0 | Medium |
| Capability | 1.5 | Medium |
| Values | 2.0 | Medium |
| Identity | 2.5 | Slow |
| Vision | 3.0 | Slow |
| Mission | 4.0 | Very slow |

The weighted center of all levels forms the **attractor** — the agent's personality center. Over time, positive experiences pull levels toward the experience state; negative experiences push away.

### LLM Layer

**File**: `llm/bridge.py`

Multi-provider LLM bridge with unified interface:

```python
bridge = LLMBridge(provider="openai", api_key="sk-...", model="gpt-4o-mini")
bridge = LLMBridge(provider="anthropic", api_key="sk-...", model="claude-3-5-sonnet")
bridge = LLMBridge(provider="gemini", api_key="AIza...", model="gemini-1.5-flash")
bridge = LLMBridge(callback=my_custom_function)  # testing / custom
```

Tracks call statistics for cost analysis:
- total_calls
- dimension_adaptation_calls
- projection_calls
- advisor_calls

### Storage Layer

**Files**: `storage/persistence.py`, `storage/mongo_persistence.py`

Two backends:

| Backend | Use Case |
|---|---|
| `PersistenceLayer` (JSON) | Single-agent, local development |
| `MongoPersistence` | Multi-agent, production, concurrent access |

## Cognitive Pipeline

The `BTCUAgent.process()` method implements the full cognitive pipeline in 6 sub-methods:

1. **`_resolve_projection`** — Pattern match first, LLM fallback
2. **`_evaluate_self_alignment`** — Check attractor distance
3. **`_find_decision_path`** — If target state specified
4. **`_generate_third_choices`** — If conflict state specified
5. **`_get_llm_advice`** — Based on growth stage and memory state
6. **`_record_cognition`** — Update trajectory, memory, climate

## Growth Model

| Stage | Projection | Memory | LLM Usage |
|---|---|---|---|
| school | Always LLM | Basic recording | Every input |
| internalize | Pattern + fallback | Accumulation | Only on miss |
| graduate | Pattern primary | Full ecology | Only unknown |

The `PatternLearner` tracks `reuse_rate` (total_reuses / total_lookups). As this approaches 1.0, the agent approaches full cognitive autonomy.

## Configuration

All configuration via environment variables with `BTCU_` prefix:

```bash
BTCU_LLM_PROVIDER=openai          # openai / anthropic / gemini
BTCU_LLM_API_KEY=sk-...
BTCU_LLM_MODEL=gpt-4o-mini
BTCU_MONGO_URI=mongodb://localhost:27017
BTCU_MONGO_DB=btcu_harness
BTCU_GROWTH_STAGE=school
```

Or use a `.env` file:

```
BTCU_LLM_PROVIDER=openai
BTCU_LLM_API_KEY=sk-...
BTCU_LLM_MODEL=gpt-4o-mini
```
