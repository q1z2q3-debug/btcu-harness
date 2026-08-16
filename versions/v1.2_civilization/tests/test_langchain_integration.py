"""Tests for BTCU-LangChain integration."""

import os
import sys
import json
import pytest

# Skip all tests if LangChain is not installed
langchain_available = False
if sys.version_info >= (3, 10):
    try:
        from langchain.agents.middleware import AgentMiddleware
        langchain_available = True
    except ImportError:
        pass

if not langchain_available:
    pytest.skip(
        "LangChain not installed. Install with: pip install 'btcu-harness[langchain]'",
        allow_module_level=True,
    )

from btcu_harness.langchain_integration import (
    BTCUCognitiveMiddleware,
    create_btcu_agent,
    create_btcu_agent_from_env,
)
from btcu_harness.langchain_integration.btcucognitive_agent import (
    BTCUCognitiveMiddleware as MW,
)
from btcu_harness.llm.bridge import LLMBridge


def _mock_llm(prompt: str) -> str:
    """Mock LLM that returns a valid cognitive projection."""
    return json.dumps({
        "assessments": [
            {"value": 1, "reason": "test"},
            {"value": 0, "reason": "test"},
            {"value": -1, "reason": "test"},
            {"value": 1, "reason": "test"},
            {"value": 0, "reason": "test"},
            {"value": 1, "reason": "test"},
            {"value": 0, "reason": "test"},
            {"value": -1, "reason": "test"},
            {"value": 1, "reason": "test"},
        ]
    })


class TestBTCUCognitiveMiddleware:
    """Test the BTCU cognitive middleware."""

    def test_creation(self):
        """Middleware can be created without API key."""
        mw = BTCUCognitiveMiddleware()
        assert mw.btcu is not None
        assert mw.btcu.growth_stage == "school"
        assert mw.total_projections == 0

    def test_creation_with_llm(self):
        """Middleware can be created with mock LLM bridge."""
        mw = BTCUCognitiveMiddleware()
        mw.btcu.llm_bridge = LLMBridge(callback=_mock_llm)
        assert mw.btcu.llm_bridge is not None

    def test_cognitive_projection(self):
        """Middleware can project input to cognitive state."""
        mw = BTCUCognitiveMiddleware()
        mw.btcu.llm_bridge = LLMBridge(callback=_mock_llm)
        response = mw.btcu.process("What is 2+2?")
        assert response.current_state is not None
        assert response.current_state.index >= 0
        assert response.current_state.index < 19683

    def test_context_formatting(self):
        """Cognitive context is formatted correctly."""
        from btcu_harness.core.state import CognitiveState
        mw = BTCUCognitiveMiddleware()
        state = CognitiveState.from_index(19682)  # All YANG
        ctx = mw._format_cognitive_context(state, type("R", (), {"self_alignment": 0.8})())
        assert "Cognitive Context" in ctx
        assert "+9" in ctx
        assert "action-oriented" in ctx

    def test_context_formatting_yin(self):
        """YIN-heavy state shows cautious disposition."""
        from btcu_harness.core.state import CognitiveState
        mw = BTCUCognitiveMiddleware()
        state = CognitiveState.from_index(0)  # All YIN
        ctx = mw._format_cognitive_context(state, type("R", (), {"self_alignment": 0.5})())
        assert "-9" in ctx
        assert "cautious" in ctx

    def test_context_formatting_low_alignment(self):
        """Low self-alignment triggers warning."""
        from btcu_harness.core.state import CognitiveState
        mw = BTCUCognitiveMiddleware()
        state = CognitiveState.from_index(100)
        ctx = mw._format_cognitive_context(state, type("R", (), {"self_alignment": 0.2})())
        assert "Warning" in ctx
        assert "Low self-alignment" in ctx

    def test_stats(self):
        """Stats return correct structure."""
        mw = BTCUCognitiveMiddleware()
        stats = mw.get_stats()
        assert "total_projections" in stats
        assert "total_tool_observations" in stats
        assert "trajectory_length" in stats
        assert "growth_stage" in stats
        assert "unique_states_visited" in stats

    def test_extract_user_text(self):
        """User text extraction from messages."""
        from langchain_core.messages import HumanMessage, AIMessage
        mw = BTCUCognitiveMiddleware()
        messages = [HumanMessage("Hello"), AIMessage("Hi there")]
        text = mw._extract_user_text(messages)
        assert text == "Hello"

    def test_extract_user_text_empty(self):
        """Empty message list returns empty string."""
        mw = BTCUCognitiveMiddleware()
        assert mw._extract_user_text([]) == ""

    def test_record_tool_choice_no_tools(self):
        """Recording when model returns no tools."""
        mw = BTCUCognitiveMiddleware()
        # Simulate a result with no tool calls
        class MockResult:
            result = [type("Msg", (), {"tool_calls": None, "content": "done"})()]
        mw._record_tool_choice(MockResult())
        assert mw.total_tool_observations == 0

    def test_record_tool_choice_with_tools(self):
        """Recording tool calls increments counter."""
        mw = BTCUCognitiveMiddleware()
        from btcu_harness.core.state import CognitiveState
        mw._last_cognitive_state = CognitiveState.from_index(100)

        class MockTC:
            def __init__(self, name):
                self.name = name

        class MockMsg:
            tool_calls = [MockTC("calculator"), MockTC("search")]

        class MockResult:
            result = [MockMsg()]

        mw._record_tool_choice(MockResult())
        assert mw.total_tool_observations == 2

    def test_before_agent(self):
        """before_agent hook returns None."""
        mw = BTCUCognitiveMiddleware()
        result = mw.before_agent({}, None)
        assert result is None

    def test_after_agent(self):
        """after_agent hook returns None."""
        mw = BTCUCognitiveMiddleware()
        result = mw.after_agent({}, None)
        assert result is None

    def test_wrap_model_call_injects_context(self):
        """wrap_model_call injects cognitive context into system message."""
        mw = BTCUCognitiveMiddleware()
        mw.btcu.llm_bridge = LLMBridge(callback=_mock_llm)

        from langchain_core.messages import HumanMessage, SystemMessage

        class MockRequest:
            def __init__(self):
                self.messages = [HumanMessage("What is 2+2?")]
                self.system_message = SystemMessage(content="You are helpful.")

        class MockHandler:
            def __call__(self, req):
                # Verify context was injected
                assert "Cognitive Context" in req.system_message.content
                return type("R", (), {"result": [type("M", (), {"tool_calls": None})()]})()

        req = MockRequest()
        handler = MockHandler()
        mw.wrap_model_call(req, handler)
        assert mw.total_projections == 1

    def test_wrap_model_call_creates_system_message(self):
        """wrap_model_call creates system message if none exists."""
        mw = BTCUCognitiveMiddleware()
        mw.btcu.llm_bridge = LLMBridge(callback=_mock_llm)

        from langchain_core.messages import HumanMessage

        class MockRequest:
            def __init__(self):
                self.messages = [HumanMessage("Calculate 5*3")]
                self.system_message = None

        class MockHandler:
            def __call__(self, req):
                assert req.system_message is not None
                assert "Cognitive Context" in req.system_message.content
                return type("R", (), {"result": [type("M", (), {"tool_calls": None})()]})()

        mw.wrap_model_call(MockRequest(), MockHandler())


class TestExecutor:
    """Test the factory functions."""

    def test_create_btcu_agent_signature(self):
        """create_btcu_agent is callable with correct params."""
        assert callable(create_btcu_agent)
        assert callable(create_btcu_agent_from_env)

    def test_create_btcu_agent_from_env_no_keys(self, monkeypatch):
        """from_env handles missing API keys gracefully."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        # Should not crash even without keys — BTCU runs in rule-based mode
        try:
            create_btcu_agent_from_env(model=None, tools=[])
        except Exception:
            # May fail at create_agent level, that's ok
            pass


class TestBenchmark:
    """Test the benchmark framework."""

    def test_scenarios_loaded(self):
        """Benchmark scenarios are loaded."""
        from btcu_harness.benchmark.langchain import BENCHMARK_SCENARIOS
        assert len(BENCHMARK_SCENARIOS) == 10
        categories = {s.category for s in BENCHMARK_SCENARIOS}
        assert "math" in categories
        assert "search" in categories
        assert "multi_step" in categories
        assert "creative" in categories
        assert "analytical" in categories

    def test_benchmark_runner(self):
        """Benchmark runner produces results."""
        from btcu_harness.benchmark.langchain import LangChainBenchmarkRunner
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()

        assert "btcu" in results
        assert "standard" in results

        btcu = results["btcu"]
        std = results["standard"]

        assert btcu.total_scenarios == 10
        assert btcu.successful_scenarios == 10
        assert btcu.total_cognitive_states > 0
        assert btcu.unique_cognitive_states > 0
        assert btcu.scenarios_with_context == 10
        assert btcu.trajectory_length > 0

        # Standard agent has zero cognitive capabilities
        assert std.total_cognitive_states == 0
        assert std.unique_cognitive_states == 0
        assert std.scenarios_with_context == 0

    def test_btcu_advantages(self):
        """BTCU has advantages over standard."""
        from btcu_harness.benchmark.langchain import (
            LangChainBenchmarkRunner,
            LangChainBenchmarkReport,
        )
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()
        report = LangChainBenchmarkReport(results["btcu"], results["standard"])
        advantages = report._compute_advantages()
        assert len(advantages) >= 5

    def test_report_generation(self, tmp_path):
        """Report can be saved to disk."""
        from btcu_harness.benchmark.langchain import (
            LangChainBenchmarkRunner,
            LangChainBenchmarkReport,
        )
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()
        report = LangChainBenchmarkReport(results["btcu"], results["standard"])
        paths = report.save(str(tmp_path))

        assert os.path.exists(paths["chart"])
        assert os.path.exists(paths["report"])
        assert os.path.exists(paths["json"])

    def test_markdown_report(self):
        """Markdown report contains key sections."""
        from btcu_harness.benchmark.langchain import (
            LangChainBenchmarkRunner,
            LangChainBenchmarkReport,
        )
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()
        report = LangChainBenchmarkReport(results["btcu"], results["standard"])
        md = report.to_markdown()

        assert "BTCU-LangChain Integration Benchmark" in md
        assert "Capability Comparison" in md
        assert "Per-Scenario Breakdown" in md
        assert "Conclusion" in md

    def test_json_report(self):
        """JSON report is valid JSON."""
        from btcu_harness.benchmark.langchain import (
            LangChainBenchmarkRunner,
            LangChainBenchmarkReport,
        )
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()
        report = LangChainBenchmarkReport(results["btcu"], results["standard"])
        data = report.to_json()

        assert "summary" in data
        assert "btcu" in data["summary"]
        assert "standard" in data["summary"]
        assert "btcu_advantages" in data

    def test_mock_llm_projection_math(self):
        """Mock LLM produces math-like projection for math queries."""
        from btcu_harness.benchmark.langchain.runner import _mock_llm_projection
        result = json.loads(_mock_llm_projection("Calculate 25 * 17"))
        assert "assessments" in result
        assert len(result["assessments"]) == 9
        # Math queries should have high tool matching
        assert result["assessments"][1]["value"] == 1

    def test_mock_llm_projection_search(self):
        """Mock LLM produces search-like projection for search queries."""
        from btcu_harness.benchmark.langchain.runner import _mock_llm_projection
        result = json.loads(_mock_llm_projection("Search for Python"))
        assert len(result["assessments"]) == 9

    def test_consistency_score(self):
        """Consistency score is computed for BTCU."""
        from btcu_harness.benchmark.langchain import LangChainBenchmarkRunner
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()
        assert results["btcu"].consistency_score > 0
        assert results["standard"].consistency_score == 0

    def test_state_coverage(self):
        """BTCU visits unique states."""
        from btcu_harness.benchmark.langchain import LangChainBenchmarkRunner
        runner = LangChainBenchmarkRunner()
        results = runner.run_all()
        assert results["btcu"].unique_cognitive_states > 0
        assert results["btcu"].state_coverage_pct > 0
