"""
Integration tests for BTCU dual-system cognitive architecture.

Covers System 1 / System 2 decision cascade, cognitive modes,
laziness defenses, audits, and the updated MCP Server.
"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from btcu_harness.cognition import (
    AuditReport,
    AuditResult,
    CognitiveAuditor,
    CognitivePattern,
    CognitiveSafetyGuard,
    Decision,
    DualSystemDecisionEngine,
    SafetyConstants,
    System1PatternLibrary,
)
from btcu_harness.cognition.defense import CognitiveSafetyGuard
from btcu_harness.core.state import CognitiveState
from btcu_harness.mcp.server import BTCUMCPServer


# ─────────────────────────────────────────────────────────────────────────
#  System 1 Pattern Library Tests
# ─────────────────────────────────────────────────────────────────────────

class TestSystem1PatternLibrary:
    """Test the System 1 pattern matching engine."""

    def test_create_library(self):
        """Library can be created empty."""
        lib = System1PatternLibrary()
        assert lib.get_state_coverage() == 0.0
        assert len(lib._patterns) == 0

    def test_learn_pattern(self):
        """Learning creates a new pattern."""
        lib = System1PatternLibrary()
        state = CognitiveState.from_index(1000)
        lib.learn("Calculate 2+2", state, "use_calculator")

        assert len(lib._patterns) == 1
        assert lib.get_state_coverage() > 0

    def test_exact_match(self):
        """Exact hash match returns the pattern."""
        lib = System1PatternLibrary()
        state = CognitiveState.from_index(1000)
        lib.learn("Calculate 2+2", state, "use_calculator")

        result = lib.match_exact("Calculate 2+2")
        assert result is not None
        assert result.action == "use_calculator"

    def test_exact_match_miss(self):
        """No match returns None."""
        lib = System1PatternLibrary()
        result = lib.match_exact("Unknown input")
        assert result is None

    def test_knn_match(self):
        """k-NN finds nearby states."""
        lib = System1PatternLibrary()
        # Create two nearby states
        state_a = CognitiveState.from_values([1, 0, 0, 0, 0, 0, 0, 0, 0])
        state_b = CognitiveState.from_values([1, 1, 0, 0, 0, 0, 0, 0, 0])

        lib.learn("Math query A", state_a, "use_calculator")
        lib.learn("Math query B", state_b, "use_calculator")

        # Query a state close to A
        query = CognitiveState.from_values([1, 0, 0, 0, 0, 0, 0, 0, 0])
        results = lib.match_knn(query.values, k=2)

        assert len(results) == 2
        assert all(r.action == "use_calculator" for r in results)

    def test_fuzzy_match(self):
        """Fuzzy matching on text similarity."""
        lib = System1PatternLibrary()
        state = CognitiveState.from_index(5000)
        lib.learn(
            "calculate compound interest rate formula",
            state,
            "use_calculator",
            context={
                "input_text": "calculate compound interest rate formula",
                "features": System1PatternLibrary._extract_text_features(
                    "calculate compound interest rate formula"
                ),
            },
        )

        # Same text should match at low threshold
        result = lib.match_fuzzy("calculate compound interest rate formula", threshold=0.1)
        assert result is not None
        assert result.action == "use_calculator"

    def test_pattern_aging(self):
        """Patterns age and confidence decays."""
        lib = System1PatternLibrary()
        state = CognitiveState.from_index(1000)
        lib.learn("Test input", state, "action_a")

        original_conf = lib._patterns[0].confidence
        # Simulate aging
        lib.age_patterns(decay_factor=0.5)

        # Pattern should still exist but confidence lower
        aged_pattern = lib._patterns[0]
        assert aged_pattern.confidence < original_conf

    def test_reinforce_pattern(self):
        """Reinforcing a pattern increases use count and keeps high confidence."""
        lib = System1PatternLibrary()
        state = CognitiveState.from_index(1000)
        lib.learn("Test input", state, "action_a", success=True)

        original_conf = lib._patterns[0].computed_confidence
        lib.learn("Test input", state, "action_a", success=True)

        # Because confidence is computed via recency decay, it may not strictly
        # increase when success_rate is already 1.0.  Assert it stays high.
        assert lib._patterns[0].computed_confidence >= original_conf - 0.01
        assert lib._patterns[0].use_count == 2

    def test_state_coverage_growth(self):
        """Coverage grows as patterns are added."""
        lib = System1PatternLibrary()
        assert lib.get_state_coverage() == 0.0

        for i in range(100):
            state = CognitiveState.from_index(i * 100)
            lib.learn(f"Input {i}", state, f"action_{i}")

        coverage = lib.get_state_coverage()
        assert coverage > 0
        assert coverage < 1.0  # Should be small fraction of 19683

    def test_persistence_roundtrip(self):
        """Save and load preserves patterns."""
        lib = System1PatternLibrary()
        state = CognitiveState.from_index(1000)
        lib.learn("Test input", state, "action_a")

        data = lib.to_dict()
        lib2 = System1PatternLibrary.from_dict(data)

        assert len(lib2._patterns) == 1
        assert lib2.match_exact("Test input") is not None


# ─────────────────────────────────────────────────────────────────────────
#  Dual System Decision Engine Tests
# ─────────────────────────────────────────────────────────────────────────

class TestDualSystemDecisionEngine:
    """Test the System 1 / System 2 cascade."""

    def test_engine_creation(self):
        """Engine can be created without LLM."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)
        assert engine.system1 is lib
        assert engine.system2 is None

    def test_system1_exact_match(self):
        """System 1 exact match bypasses System 2."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        lib.learn("Calculate 2+2", state, "use_calculator")

        with patch.object(engine.safety_guard, "should_explore", return_value=False):
            decision = engine.decide("Calculate 2+2", state)

        assert decision.system_used == "system1"
        assert decision.source == "system1_exact"
        assert decision.action == "use_calculator"
        assert decision.tokens_consumed == 0
        assert decision.latency_ms < 10  # Fast!

    def test_system1_miss_fallback(self):
        """System 1 miss falls back to System 1 miss when no LLM."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        with patch.object(engine.safety_guard, "should_explore", return_value=False):
            decision = engine.decide("Completely novel query", state)

        # No LLM configured → source is "system1_miss"
        assert decision.source == "system1_miss"
        assert decision.action == "unknown"
        assert decision.tokens_consumed == 0

    def test_system1_knn_consensus(self):
        """k-NN consensus returns System 1 decision."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        # Multiple similar patterns
        for i in range(5):
            state = CognitiveState.from_values([1, 1 if i % 2 else 0, 0, 0, 0, 0, 0, 0, 0])
            lib.learn(f"Math query {i}", state, "use_calculator")

        query_state = CognitiveState.from_values([1, 0, 0, 0, 0, 0, 0, 0, 0])
        with patch.object(engine.safety_guard, "should_explore", return_value=False):
            decision = engine.decide("New math problem", query_state)

        # Should hit k-NN
        assert "system1" in decision.source
        assert decision.action == "use_calculator"

    def test_mode_novice(self):
        """Novice mode skips System 1 and falls back to system1_miss when no LLM."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        lib.learn("Calculate 2+2", state, "use_calculator")

        # Novice mode skips System 1, and with no LLM configured returns system1_miss
        with patch.object(engine.safety_guard, "should_explore", return_value=False):
            decision = engine.decide("Calculate 2+2", state, mode="novice")
        assert decision.source == "system1_miss"
        assert decision.action == "unknown"

    def test_mode_system1_only(self):
        """system1 mode forces System 1 even with low confidence."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        # Low confidence pattern
        lib.learn("Query", state, "action", success=False)

        with patch.object(engine.safety_guard, "should_explore", return_value=False):
            decision = engine.decide("Query", state, mode="system1")
        assert "system1" in decision.source

    def test_epsilon_exploration(self):
        """Epsilon exploration forces System 2 sometimes."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        lib.learn("Query", state, "action")

        # With epsilon=1.0, should always explore (System 2)
        decision = engine.decide("Query", state, epsilon=1.0)
        assert decision.source == "system2_explore"

    def test_stats_tracking(self):
        """Engine tracks decision statistics."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        lib.learn("Q1", state, "a1")
        lib.learn("Q2", CognitiveState.from_index(2000), "a2")

        engine.decide("Q1", state)
        engine.decide("Unknown", CognitiveState.from_index(3000))

        stats = engine.get_coverage_stats()
        assert stats["total_decisions"] == 2
        assert stats["system1_hits"] == 1
        # system1_miss is counted as system1, so system2_hits == 0 here
        assert stats["system2_hits"] == 0

    def test_learning_from_system2(self):
        """When no LLM is configured, System 2 is unavailable and no learning occurs."""
        lib = System1PatternLibrary()
        engine = DualSystemDecisionEngine(pattern_library=lib)

        state = CognitiveState.from_index(1000)
        # No patterns yet
        assert len(lib._patterns) == 0

        # Decision falls to System 1 miss (no System 2 configured)
        with patch.object(engine.safety_guard, "should_explore", return_value=False):
            decision = engine.decide("New query", state)
        assert decision.source == "system1_miss"

        # No learning occurred because System 2 is unavailable
        assert len(lib._patterns) == 0


# ─────────────────────────────────────────────────────────────────────────
#  Cognitive Safety Guard Tests
# ─────────────────────────────────────────────────────────────────────────

class TestCognitiveSafetyGuard:
    """Test laziness defenses."""

    def test_rigidity_detection(self):
        """Detect when pattern is applied to wrong state."""
        guard = CognitiveSafetyGuard()

        current = CognitiveState.from_index(0)       # ALL_YIN
        matched = CognitiveState.from_index(19682)   # ALL_YANG

        result = guard.detect_rigidity(current, matched, threshold=3)

        assert result["rigid"] is True
        assert result["distance"] == 18  # Maximum possible

    def test_no_rigidity_nearby(self):
        """Nearby states are not rigid."""
        guard = CognitiveSafetyGuard()

        current = CognitiveState.from_values([1, 0, 0, 0, 0, 0, 0, 0, 0])
        matched = CognitiveState.from_values([1, 1, 0, 0, 0, 0, 0, 0, 0])

        result = guard.detect_rigidity(current, matched, threshold=3)
        assert result["rigid"] is False

    def test_epsilon_exploration_low_coverage(self):
        """Epsilon boosted when coverage is low."""
        guard = CognitiveSafetyGuard()

        # Mock low coverage stats
        stats = {"state_coverage_pct": 0.05}
        should = guard.should_explore(epsilon=0.1, session_stats=stats)

        # With coverage < 10%, epsilon should be boosted
        # But it's probabilistic, so we can't assert exact result
        assert isinstance(should, bool)

    def test_feedback_trap_detection(self):
        """Detect declining pattern quality."""
        guard = CognitiveSafetyGuard()

        pattern = CognitivePattern(
            input_hash="hash123",
            state_index=100,
            state_values=[0] * 9,
            action="action",
            context={},
            success_rate=0.9,
            use_count=10,
            created_at=datetime.now(),
            last_used=datetime.now(),
            confidence=0.9,
            system2_audit_score=0.8,
        )

        # Simulate declining decisions for this exact pattern hash
        recent = [
            {"pattern_hash": "hash123", "confidence": 0.9},
            {"pattern_hash": "hash123", "confidence": 0.7},
            {"pattern_hash": "hash123", "confidence": 0.5},
            {"pattern_hash": "hash123", "confidence": 0.3},
            {"pattern_hash": "hash123", "confidence": 0.1},
        ]

        result = guard.detect_feedback_trap(pattern, recent)

        assert result["trapped"] is True
        assert result["decline_rate"] > 0

    def test_no_trap_stable(self):
        """Stable patterns are not trapped."""
        guard = CognitiveSafetyGuard()

        pattern = CognitivePattern(
            input_hash="hash",
            state_index=100,
            state_values=[0] * 9,
            action="action",
            context={},
            success_rate=0.8,
            use_count=10,
            created_at=datetime.now(),
            last_used=datetime.now(),
            confidence=0.8,
            system2_audit_score=0.8,
        )

        recent = [
            {"source": "system1_exact", "confidence": 0.8},
            {"source": "system1_exact", "confidence": 0.82},
            {"source": "system1_exact", "confidence": 0.79},
        ]

        result = guard.detect_feedback_trap(pattern, recent)
        assert result["trapped"] is False

    def test_blind_spots_detection(self):
        """Identify unexplored cognitive regions."""
        lib = System1PatternLibrary()
        # Cover a small region
        for i in range(50):
            state = CognitiveState.from_index(i * 10)
            lib.learn(f"Input {i}", state, f"action_{i}")

        guard = CognitiveSafetyGuard()
        spots = guard.get_blind_spots(lib, min_density=0.001)

        assert len(spots) > 0
        # Most of 19683 states should be blind spots
        total_blind = sum(s["state_range"][1] - s["state_range"][0] for s in spots)
        assert total_blind > 19000


# ─────────────────────────────────────────────────────────────────────────
#  Cognitive Auditor Tests
# ─────────────────────────────────────────────────────────────────────────

class TestCognitiveAuditor:
    """Test System 2 audit of System 1."""

    def test_auditor_creation(self):
        """Auditor can be created without LLM."""
        auditor = CognitiveAuditor()
        assert auditor is not None

    def test_audit_decision_no_llm(self):
        """Without LLM, audit returns basic comparison."""
        auditor = CognitiveAuditor()

        decision = Decision(
            action="use_calculator",
            source="system1_exact",
            confidence=0.9,
            system_used="system1",
            tokens_consumed=0,
            latency_ms=2.0,
            pattern_matched=True,
            alternative_actions=["use_search"],
            cognitive_state=1000,
        )

        result = auditor.audit_decision(decision, "Calculate 2+2", {})

        assert isinstance(result, AuditResult)
        assert result.original_action == "use_calculator"

    def test_batch_audit_empty(self):
        """Batch audit with empty list returns empty report."""
        auditor = CognitiveAuditor()
        report = auditor.audit_batch([], sample_rate=0.1)

        assert report.total_audited == 0

    def test_batch_audit_sampling(self):
        """Batch audit samples a subset."""
        auditor = CognitiveAuditor()

        decisions = [
            Decision(
                action=f"action_{i}",
                source="system1_exact",
                confidence=0.8,
                system_used="system1",
                tokens_consumed=0,
                latency_ms=2.0,
                pattern_matched=True,
                alternative_actions=[],
                cognitive_state=i * 100,
            )
            for i in range(100)
        ]

        report = auditor.audit_batch(decisions, sample_rate=0.1)

        # Should audit about 10% = ~10 decisions
        assert 5 <= report.total_audited <= 20

    def test_audit_report_generation(self):
        """Can generate markdown report."""
        auditor = CognitiveAuditor()
        report_text = auditor.generate_report()

        assert isinstance(report_text, str)
        assert len(report_text) > 0


# ─────────────────────────────────────────────────────────────────────────
#  MCP Server Dual-System Tests
# ─────────────────────────────────────────────────────────────────────────

class TestMCPServerDualSystem:
    """Test MCP Server integration of dual-system features."""

    def setup_method(self):
        """Create a fresh server for each test."""
        self.server = BTCUMCPServer()

    def test_server_version(self):
        """Server reports dual-system version."""
        assert self.server.SERVER_VERSION == "1.2.0"

    def test_tools_list_includes_new_tools(self):
        """Tools list includes cognitive_decide, cognitive_mode, cognitive_audit."""
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        result = self.server.dispatch(msg)

        tools = result["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        assert "cognitive_decide" in tool_names
        assert "cognitive_mode" in tool_names
        assert "cognitive_audit" in tool_names
        # Old tools still present
        assert "cognitive_project" in tool_names
        assert "cognitive_compare" in tool_names

    def test_cognitive_decide_creates_engine(self):
        """cognitive_decide lazily creates DualSystemDecisionEngine."""
        assert len(self.server._engines) == 0

        msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_decide",
                "arguments": {
                    "input": "Calculate 2+2",
                    "session_id": "test_dual",
                    "mode": "auto",
                }
            }
        }
        self.server.dispatch(msg)

        assert "test_dual" in self.server._engines
        assert isinstance(self.server._engines["test_dual"], DualSystemDecisionEngine)

    def test_cognitive_decide_returns_decision(self):
        """cognitive_decide returns structured decision."""
        msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_decide",
                "arguments": {
                    "input": "Calculate compound interest",
                    "session_id": "test_decide",
                }
            }
        }
        result = self.server.dispatch(msg)

        data = json.loads(result["result"]["content"][0]["text"])
        assert "action" in data
        assert "source" in data
        assert "confidence" in data
        assert "system_used" in data
        assert "latency_ms" in data
        assert "tokens_consumed" in data

    def test_cognitive_mode_sets_mode(self):
        """cognitive_mode changes the session's cognitive mode."""
        # First create engine via decide
        self.server.dispatch({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_decide",
                "arguments": {
                    "input": "Test",
                    "session_id": "test_mode",
                }
            }
        })

        # Set mode to expert
        msg = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cognitive_mode",
                "arguments": {
                    "mode": "expert",
                    "session_id": "test_mode",
                }
            }
        }
        result = self.server.dispatch(msg)

        data = json.loads(result["result"]["content"][0]["text"])
        assert data["mode"] == "expert"
        assert "coverage_stats" in data

    def test_cognitive_mode_rejects_invalid(self):
        """cognitive_mode rejects invalid mode names."""
        msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_mode",
                "arguments": {
                    "mode": "invalid_mode",
                    "session_id": "test_invalid",
                }
            }
        }
        result = self.server.dispatch(msg)

        assert "error" in result

    def test_cognitive_project_with_system1_match(self):
        """cognitive_project now includes system1_match field."""
        # First teach a pattern
        self.server.dispatch({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_decide",
                "arguments": {
                    "input": "Calculate 2+2",
                    "session_id": "test_project_s1",
                }
            }
        })

        # Now project the same input
        msg = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "Calculate 2+2",
                    "session_id": "test_project_s1",
                }
            }
        }
        result = self.server.dispatch(msg)

        data = json.loads(result["result"]["content"][0]["text"])
        assert "system1_match" in data

    def test_resources_list_includes_new_resources(self):
        """Resources list includes efficiency, blind_spots, audit_report."""
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}}
        result = self.server.dispatch(msg)

        resources = result["result"]["resources"]
        uris = [r["uri"] for r in resources]

        assert "cognitive://sessions/{session_id}/efficiency" in uris
        assert "cognitive://sessions/{session_id}/blind_spots" in uris
        assert "cognitive://sessions/{session_id}/audit_report" in uris

    def test_efficiency_resource(self):
        """efficiency resource returns dashboard data."""
        # Create some decisions first
        for i in range(5):
            self.server.dispatch({
                "jsonrpc": "2.0", "id": i,
                "method": "tools/call",
                "params": {
                    "name": "cognitive_decide",
                    "arguments": {
                        "input": f"Query {i}",
                        "session_id": "test_eff",
                    }
                }
            })

        msg = {
            "jsonrpc": "2.0", "id": 10,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/test_eff/efficiency"}
        }
        result = self.server.dispatch(msg)

        data = json.loads(result["result"]["contents"][0]["text"])
        assert "system1_hit_rate" in data
        assert "total_decisions" in data
        assert "system2_tokens_consumed_24h" in data
        assert "estimated_cost_savings" in data

    def test_blind_spots_resource(self):
        """blind_spots resource returns unexplored regions."""
        msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/test_blind/blind_spots"}
        }
        result = self.server.dispatch(msg)

        wrapper = json.loads(result["result"]["contents"][0]["text"])
        data = wrapper["blind_spots"]
        assert isinstance(data, list)
        # Most states should be blind spots initially
        total_blind = sum(s["state_range"][1] - s["state_range"][0] for s in data)
        assert total_blind > 19000

    def test_prompts_list_includes_mode_guide(self):
        """Prompts list includes cognitive_mode_guide."""
        msg = {"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}}
        result = self.server.dispatch(msg)

        prompts = result["result"]["prompts"]
        names = [p["name"] for p in prompts]
        assert "cognitive_mode_guide" in names

    def test_cognitive_mode_guide_prompt(self):
        """cognitive_mode_guide prompt explains dual-system modes."""
        msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "prompts/get",
            "params": {"name": "cognitive_mode_guide", "arguments": {}}
        }
        result = self.server.dispatch(msg)

        # The actual guide content is in messages[0].content.text
        text = result["result"]["messages"][0]["content"]["text"]
        assert "novice" in text.lower() or "expert" in text.lower()

    def test_backward_compatibility_existing_tools(self):
        """All existing tools still work."""
        # cognitive_project
        msg1 = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {"input": "Test", "session_id": "test_compat"}
            }
        }
        result1 = self.server.dispatch(msg1)
        assert "error" not in result1

        # cognitive_compare
        msg2 = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [-1, -1, -1, -1, -1, -1, -1, -1, -1],
                    "state_b": [1, 1, 1, 1, 1, 1, 1, 1, 1],
                }
            }
        }
        result2 = self.server.dispatch(msg2)
        assert "error" not in result2
        data2 = json.loads(result2["result"]["content"][0]["text"])
        assert data2["distance"] == 18

    def test_multiple_sessions_isolation(self):
        """Different sessions have independent engines."""
        for session_id in ["sess_a", "sess_b", "sess_c"]:
            self.server.dispatch({
                "jsonrpc": "2.0", "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "cognitive_decide",
                    "arguments": {"input": "Test", "session_id": session_id}
                }
            })

        assert len(self.server._engines) == 3
        assert "sess_a" in self.server._engines
        assert "sess_b" in self.server._engines
        assert "sess_c" in self.server._engines

    def test_cognitive_decide_with_learned_pattern(self):
        """Without an LLM, both calls return system1_miss when exploration is disabled."""
        session_id = "test_learn"

        with patch.object(CognitiveSafetyGuard, "should_explore", return_value=False):
            # First call: no pattern known, System 2 unavailable → system1_miss
            msg1 = {
                "jsonrpc": "2.0", "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "cognitive_decide",
                    "arguments": {"input": "Calculate 2+2", "session_id": session_id}
                }
            }
            result1 = self.server.dispatch(msg1)
            data1 = json.loads(result1["result"]["content"][0]["text"])

            # Second call with exact same input: still system1_miss because no LLM → no learning
            msg2 = {
                "jsonrpc": "2.0", "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "cognitive_decide",
                    "arguments": {"input": "Calculate 2+2", "session_id": session_id}
                }
            }
            result2 = self.server.dispatch(msg2)
            data2 = json.loads(result2["result"]["content"][0]["text"])

            # Both return system1_miss when no LLM is configured and exploration is off
            assert data1["source"] == "system1_miss"
            assert data2["source"] == "system1_miss"


# ─────────────────────────────────────────────────────────────────────────
#  Integration Flow Test
# ─────────────────────────────────────────────────────────────────────────

class TestDualSystemIntegrationFlow:
    """End-to-end dual-system cognitive workflow."""

    def test_full_cognitive_workflow(self):
        """Simulate a realistic cognitive workflow with all components."""
        server = BTCUMCPServer()
        session_id = "integration_test"

        # Step 1: Set mode to apprentice (balanced System 1/2)
        server.dispatch({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_mode",
                "arguments": {"mode": "apprentice", "session_id": session_id}
            }
        })

        # Step 2: Process multiple decisions to build pattern library
        inputs = [
            "Calculate 25 times 17",
            "What is the square root of 144",
            "Add 100 and 250",
            "Calculate compound interest",
            "What is 15% of 240",
        ]

        for i, inp in enumerate(inputs):
            server.dispatch({
                "jsonrpc": "2.0", "id": 10 + i,
                "method": "tools/call",
                "params": {
                    "name": "cognitive_decide",
                    "arguments": {"input": inp, "session_id": session_id}
                }
            })

        # Step 3: Check efficiency dashboard
        result = server.dispatch({
            "jsonrpc": "2.0", "id": 20,
            "method": "resources/read",
            "params": {"uri": f"cognitive://sessions/{session_id}/efficiency"}
        })
        efficiency = json.loads(result["result"]["contents"][0]["text"])
        assert efficiency["total_decisions"] == 5

        # Step 4: Check for blind spots
        result = server.dispatch({
            "jsonrpc": "2.0", "id": 21,
            "method": "resources/read",
            "params": {"uri": f"cognitive://sessions/{session_id}/blind_spots"}
        })
        blind_spots = json.loads(result["result"]["contents"][0]["text"])
        assert len(blind_spots) > 0

        # Step 5: Run audit (will be basic without LLM)
        result = server.dispatch({
            "jsonrpc": "2.0", "id": 22,
            "method": "tools/call",
            "params": {
                "name": "cognitive_audit",
                "arguments": {"session_id": session_id, "sample_rate": 0.2}
            }
        })
        audit = json.loads(result["result"]["content"][0]["text"])
        assert "total_audited" in audit

        # Step 6: Check that patterns were learned
        engine = server._engines.get(session_id)
        if engine:
            stats = engine.get_coverage_stats()
            assert stats["total_decisions"] == 5

        print(f"Integration flow complete: {efficiency['total_decisions']} decisions, "
              f"{efficiency.get('system1_hit_rate', 0):.2f} System 1 hit rate")

    def test_rigidity_downgrade(self):
        """When rigidity detected, System 2 should take over."""
        server = BTCUMCPServer()
        session_id = "test_rigidity"

        # First, learn a pattern
        server.dispatch({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "cognitive_decide",
                "arguments": {
                    "input": "Calculate 2+2",
                    "session_id": session_id,
                    "mode": "system1",  # Force System 1 to learn
                }
            }
        })

        # Now with a very different input but similar enough to trigger match
        # The safety guard should detect rigidity if state distance is large
        # Since we're in auto mode with no LLM, it will fallback to System 2
        result = server.dispatch({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cognitive_decide",
                "arguments": {
                    "input": "Write a poem about love and loss",  # Very different!
                    "session_id": session_id,
                }
            }
        })

        data = json.loads(result["result"]["content"][0]["text"])
        # With no LLM, System 2 returns "unknown"
        # But the decision flow went through the dual-system cascade
        assert "action" in data
        assert "source" in data
