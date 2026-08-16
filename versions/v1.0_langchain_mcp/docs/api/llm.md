# API Reference — LLM

The `llm` module provides a unified interface to multiple LLM providers.

## `LLMBridge`

Multi-provider LLM bridge with automatic provider selection.

```python
from btcu_harness.llm.bridge import LLMBridge

# Auto-detect from environment
bridge = LLMBridge()

# Explicit provider
bridge = LLMBridge(
    provider="openai",
    api_key="sk-...",
    model="gpt-4o-mini",
)

bridge = LLMBridge(
    provider="anthropic",
    api_key="sk-ant-...",
    model="claude-3-5-sonnet-20241022",
)

bridge = LLMBridge(
    provider="gemini",
    api_key="AIza...",
    model="gemini-1.5-flash",
)

# Callback mode (testing, custom integrations)
bridge = LLMBridge(callback=lambda prompt: '{"value": 0}')
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BTCU_LLM_PROVIDER` | `openai` | Provider name |
| `BTCU_LLM_API_KEY` | `""` | API key |
| `BTCU_LLM_MODEL` | `gpt-4o-mini` | Model name |
| `BTCU_LLM_API_BASE` | `https://api.openai.com/v1` | API base URL |

### Methods

| Method | Description |
|---|---|
| `query(prompt: str) -> str` | Send prompt to LLM, return response text |
| `adapt_dimensions(desc: str) -> str` | Get 9 dimension suggestions for a project |
| `project_input(text: str, labels: list) -> str` | Evaluate input across 9 dimensions |
| `advise(question: str, context=None) -> str` | Get advice for novel situations |

### Cost Tracking

```python
bridge = LLMBridge(provider="openai", api_key="sk-...")

# ... make some calls ...

stats = bridge.cost_stats
# {
#   "total_calls": 10,
#   "dimension_adaptation": 1,
#   "projection": 5,
#   "advisor": 4,
# }
```

## `LLMProvider` (Base Class)

All providers implement:

```python
class LLMProvider:
    name: str
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str
```

## Provider Classes

| Class | Name | Requirements |
|---|---|---|
| `OpenAIProvider` | `openai` | `pip install "btcu-harness[openai]"` |
| `AnthropicProvider` | `anthropic` | `pip install "btcu-harness[anthropic]"` |
| `GeminiProvider` | `gemini` | `pip install "btcu-harness[gemini]"` |

### Provider-Specific Notes

**OpenAI**: Standard chat.completions API. Supports any OpenAI-compatible endpoint (e.g., local servers).

**Anthropic**: Messages API with `max_tokens=4096`. System prompt passed via `system` parameter.

**Gemini**: Uses `google.genai` package. Temperature controlled via `config` parameter.

## Callback Mode

For testing or custom LLM integrations:

```python
def my_llm(prompt: str) -> str:
    # Your custom LLM logic here
    return '{"assessments": [...]}'

bridge = LLMBridge(callback=my_llm)
result = bridge.query("some prompt")  # Calls my_llm
```

Callback mode bypasses all provider logic and directly calls your function.
