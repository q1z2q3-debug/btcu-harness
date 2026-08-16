# BTCU Harness

**Balanced Ternary Cognitive Unit Harness** — A cognitive architecture for LLM-based agents built on balanced ternary logic {-1, 0, +1}.

---

## What is BTCU?

BTCU Harness introduces a **structured, interpretable, and evolvable cognitive layer** between LLMs and autonomous agents. Instead of treating the agent's "mind" as an unstructured text buffer, BTCU provides:

- **19,683 discrete cognitive states** — completely enumerable, navigable, and comparable
- **Intrinsic transformation** — the VOID state {-1+1=0} encodes change itself
- **Emergent semantics** — state meanings arise from experience, never preset
- **Four-layer memory ecology** — episodic, procedural, capability, and biographical
- **Third-choice synthesis** — generates creative alternatives beyond binary conflicts
- **Growth model** — school → internalize → graduate, progressively reducing LLM dependency

## Installation

```bash
pip install btcu-harness

# With LLM providers
pip install "btcu-harness[openai]"     # OpenAI GPT
pip install "btcu-harness[anthropic]"  # Anthropic Claude
pip install "btcu-harness[gemini]"     # Google Gemini

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

## Architecture

BTCU consists of six layers:

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Core | `core/` | Trit, CognitiveState (19,683 states), CognitiveSpace |
| Mapping | `mapping/` | DimensionAdapter, InputProjector, PatternLearner |
| Memory | `memory/` | StateMemory, TransitionMemory, Ecology, Trajectory, Climate |
| Decision | `decision/` | Pathfinder, ThirdChoiceGenerator |
| Self | `self_layer/` | NLPSelfLayer (Dilts 8-level identity model) |
| LLM | `llm/` | Multi-provider bridge (OpenAI/Claude/Gemini) |

## REST API

```bash
pip install "btcu-harness[api]"
uvicorn btcu_harness.api:app --port 8000
```

Endpoints: `POST /api/init`, `POST /api/project`, `GET /api/status`, `GET /api/explore`, and more. Full OpenAPI docs at `http://localhost:8000/docs`.

## Resources

- [Quickstart](quickstart.md) — 5-minute hands-on tutorial
- [Architecture](architecture.md) — System design overview
- [Philosophy](philosophy.md) — Dao, emptiness, and information theory
- [REST API](rest_api.md) — Complete API reference
- [Paper](BTCU_Harness_Paper_v1.0.md) — Full academic paper

## License

MIT License
