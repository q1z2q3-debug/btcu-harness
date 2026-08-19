# BTCU Harness

**Balanced Ternary Cognitive Unit Harness** — A cognitive architecture for LLM-based agents built on balanced ternary logic {-1, 0, +1}.

[![CI](https://github.com/q1z2q3-debug/btcu-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/q1z2q3-debug/btcu-harness/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/btcu-harness.svg)](https://pypi.org/project/btcu-harness/)
[![Tests](https://img.shields.io/badge/tests-218%20passed-brightgreen.svg)](#)

---

## What is BTCU?

BTCU Harness introduces a **structured, interpretable, and evolvable cognitive layer** between large language models (LLMs) and autonomous agents.

Instead of treating the agent's "mind" as an unstructured text buffer, BTCU provides:

- **19,683 discrete cognitive states** — completely enumerable, navigable, and comparable
- **Intrinsic transformation** — the VOID state encodes change itself (-1+1=0)
- **Emergent semantics** — state meanings arise from experience, never preset
- **Four-layer memory ecology** — episodic, procedural, capability, and biographical
- **Third-choice synthesis** — generates creative alternatives beyond binary conflicts
- **Growth model** — school → internalize → graduate, progressively reducing LLM dependency

## Installation

```bash
pip install btcu-harness

# With LLM providers
pip install "btcu-harness[openai]"      # OpenAI GPT
pip install "btcu-harness[anthropic]"   # Anthropic Claude
pip install "btcu-harness[gemini]"      # Google Gemini

# With REST API
pip install "btcu-harness[api]"

# With MongoDB
pip install "btcu-harness[mongo]"

# Everything
pip install "btcu-harness[all]"
```

## Quick Example

```python
from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState
from btcu_harness.llm.bridge import LLMBridge

# Create agent with callback (no API key needed for testing)
agent = BTCUAgent(growth_stage="school")
agent.init_project(
    domain="custom",
    dim_labels=["Speed", "Quality", "Cost", "Risk", "Innovation",
                "Team", "Deadline", "Scope", "Impact"],
)

# Process input
response = agent.process("Should we prioritize speed?")
print(f"State #{response.current_state.index}")
print(f"Polarity: {response.current_state.polarity}")
print(f"Self alignment: {response.self_alignment:.1%}")
```

Or run the quickstart script (no API key needed):

```bash
python examples/quickstart.py
```

## REST API

```bash
pip install "btcu-harness[api]"
uvicorn btcu_harness.api:app --port 8000
```

Endpoints: `POST /api/init`, `POST /api/project`, `GET /api/status`, `GET /api/explore`, and more. Interactive OpenAPI docs at `http://localhost:8000/docs`.

Or with Docker:

```bash
docker compose up
```

## Architecture

```
btcu_harness/
├── core/              # Trit, CognitiveState (19,683 states), CognitiveSpace
├── mapping/           # DimensionAdapter, InputProjector, PatternLearner
├── memory/            # StateMemory, TransitionMemory, Ecology, Trajectory, Climate
├── decision/          # Pathfinder, ThirdChoiceGenerator
├── self_layer/        # NLPSelfLayer (Dilts 8-level identity model)
├── llm/               # Multi-provider bridge (OpenAI/Claude/Gemini)
├── storage/           # PersistenceLayer (JSON), MongoPersistence (MongoDB)
├── api.py             # FastAPI REST interface
├── cli.py             # Command-line interface
└── agent.py           # BTCUAgent orchestrator
```

## Documentation

- [Quickstart](docs/quickstart.md) — 5-minute tutorial
- [Architecture](docs/architecture.md) — System design
- [Philosophy](docs/philosophy.md) — Dao, emptiness, and information theory
- [REST API](docs/rest_api.md) — Complete API reference
- [Paper](docs/BTCU_Harness_Paper_v1.0.md) — Full academic paper

## Configuration

All via environment variables with `BTCU_` prefix:

```bash
BTCU_LLM_PROVIDER=openai          # openai / anthropic / gemini
BTCU_LLM_API_KEY=sk-...
BTCU_LLM_MODEL=gpt-4o-mini
BTCU_MONGO_URI=mongodb://localhost:27017
```

Or use a `.env` file.

## Testing

```bash
pip install "btcu-harness[dev]"
pytest tests/ -v
```

## License

MIT License
