"""Tests for multi-provider LLM bridge."""
import pytest

from btcu_harness.llm.bridge import (
    LLMBridge,
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    _PROVIDERS,
)


class TestProviders:
    def test_provider_registry(self):
        assert "openai" in _PROVIDERS
        assert "anthropic" in _PROVIDERS
        assert "gemini" in _PROVIDERS

    def test_provider_names(self):
        assert OpenAIProvider.name == "openai"
        assert AnthropicProvider.name == "anthropic"
        assert GeminiProvider.name == "gemini"

    def test_provider_init(self):
        p = OpenAIProvider(api_key="sk-test", model="gpt-4o")
        assert p.api_key == "sk-test"
        assert p.model == "gpt-4o"

    def test_base_provider_raises(self):
        p = LLMProvider(api_key="k", model="m")
        with pytest.raises(NotImplementedError):
            p.complete("sys", "user")


class TestLLMBridgeCallback:
    def test_callback_mode(self):
        bridge = LLMBridge(callback=lambda p: "result")
        assert bridge.query("test") == "result"
        assert bridge.total_calls == 1

    def test_callable(self):
        bridge = LLMBridge(callback=lambda p: "called")
        assert bridge("prompt") == "called"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMBridge(provider="invalid_provider", api_key="k")

    def test_repr_callback(self):
        bridge = LLMBridge(callback=lambda p: "")
        r = repr(bridge)
        assert "callback" in r

    def test_cost_stats(self):
        bridge = LLMBridge(callback=lambda p: "")
        bridge.query("a")
        bridge.query("b")
        assert bridge.cost_stats["total_calls"] == 2

    def test_advise(self):
        bridge = LLMBridge(callback=lambda p: f"advice for: {p}")
        result = bridge.advise("what to do?", context="some context")
        assert "what to do" in result
        assert bridge.cost_stats["advisor"] == 1

    def test_project_input(self):
        bridge = LLMBridge(callback=lambda p: f"projection: {p[:20]}")
        result = bridge.project_input("test input", ["d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8"])
        assert "projection" in result
        assert bridge.cost_stats["projection"] == 1

    def test_adapt_dimensions(self):
        bridge = LLMBridge(callback=lambda p: "dims")
        bridge.adapt_dimensions("my project")
        assert bridge.cost_stats["dimension_adaptation"] == 1


class TestLLMBridgeProviderMode:
    def test_openai_provider_init(self):
        bridge = LLMBridge(provider="openai", api_key="sk-test", model="gpt-4o-mini")
        assert bridge.provider_name == "openai"
        assert bridge._provider is not None
        assert isinstance(bridge._provider, OpenAIProvider)

    def test_anthropic_provider_init(self):
        bridge = LLMBridge(provider="anthropic", api_key="sk-test", model="claude-3-5-sonnet-20241022")
        assert bridge.provider_name == "anthropic"
        assert isinstance(bridge._provider, AnthropicProvider)

    def test_gemini_provider_init(self):
        bridge = LLMBridge(provider="gemini", api_key="AIza-test", model="gemini-1.5-flash")
        assert bridge.provider_name == "gemini"
        assert isinstance(bridge._provider, GeminiProvider)

    def test_repr_with_provider(self):
        bridge = LLMBridge(provider="openai", api_key="sk-test", model="gpt-4o")
        r = repr(bridge)
        assert "openai" in r
        assert "gpt-4o" in r
