# BTCU Harness

**Balanced Ternary Cognitive Unit Harness**

> A cognitive harness for LLM agents built on the balanced ternary unit `{-1, 0, +1}` and the 19683-state cognitive space.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Status: Experimental](https://img.shields.io/badge/status-experimental-orange.svg)]()

---

## Overview

BTCU Harness gives large language model agents a structured, explainable, and evolvable cognitive layer. It does not replace the LLM—it harnesses it.

The system maps any cognitive state into a nine-dimensional balanced ternary vector and encodes it as a unique index in the **19683-state space**:

```text
3^9 = 19683
```

Where each dimension takes one of three values:

| Value | Symbol | Name  | Meaning                              |
|-------|--------|-------|--------------------------------------|
| `-1`  | `T`    | YIN   | negation, retreat, contraction       |
| `0`   | `0`    | EMPTY | transformation, creativity, waiting |
| `+1`  | `1`    | YANG  | affirmation, advance, expansion      |

The core identity is:

```text
-1 + 1 = 0
```

Opposite states entering EMPTINESS is not cancellation. It is the gateway to third-choice generation.

---

## Philosophy

BTCU Harness is not a traditional ternary computer project. It focuses on software-level cognitive architecture for LLM agents.

- **Structure** — the ternary primitive and the 19683 space are the skeleton.
- **Soul** — the EMPTY state, mission, values, and identity are the breath.
- **Creativity** — moving toward unmapped regions is the growth.

The LLM is the school. BTCU Harness is the graduation.

---

## Architecture

```text
BTCU Harness
├── core/          # balanced ternary primitives and 19683 encoding
├── npl/           # NLP self-layer (mission, values, identity, ...)
├── storage/       # MongoDB adapter with in-memory fallback
├── mapping/       # cognitive projectors
├── memory/        # memory ecosystem
├── decision/      # trigram transition paths and third choice
└── llm/           # LLM advisor layer
```

### Implementation Status

| Module        | Status      |
|---------------|-------------|
| `core/`       | ✅ implemented |
| `storage/`    | ✅ implemented |
| `npl/`        | 🔨 in progress |
| `mapping/`    | ⏳ planned   |
| `memory/`     | ⏳ planned   |
| `decision/`   | ⏳ planned   |
| `llm/`        | ⏳ planned   |

---

## Quick Start

### Install

```bash
git clone https://github.com/q1z2q3-debug/btcu-harness.git
cd btcu-harness
pip install -e .
```

### Encode a Cognitive State

```python
from btcu_harness.core.encoding import encode, decode
from btcu_harness.core.space import Space19683

# Nine-trit vector: [time, space, causality, value, relation, action, subject, intent, cognition]
vector = [1, 0, -1, 1, -1, 0, 1, 0, -1]

state_id = encode(vector)
print(state_id)  # unique index in 0..19682

space = Space19683()
print(space.interpret(state_id))
```

### Interpret a State

```python
space = Space19683()
info = space.interpret(9841)  # all-EMPTY center
print(info["symbol"])   # "000000000"
print(info["region"])   # "all-empty"
```

---

## Storage

MongoDB is the primary store. If MongoDB is unavailable, an in-memory fallback keeps the harness fully operational.

```python
from btcu_harness.storage import MongoStore

store = MongoStore()
print(store.is_mongo_available)
```

Collections:

- `state_space` — 19683 cognitive state slots
- `memory_traces` — agent cognitive trajectories
- `dimension_sets` — flexible dimension definitions
- `experiment_logs` — daily project memory
- `life_course` — agent growth records
- `capabilities` — skill and workflow index

---

## Core Principles

1. **Only the ternary core is closed.** Everything else is open and self-adaptive.
2. **Emptiness is creative.** `0` is a first-class cognitive state, not a gap.
3. **Memory is ecology.** It evolves; it is not a static archive.
4. **Decision is transition.** It moves through valid state paths, not option picks.
5. **Cost decreases with maturity.** The agent graduates from the LLM.

---

## Documentation

- [Life Course](docs/life_course.md) — the project's first life imprint

---

## License

MIT
