"""
DualSystemDecisionEngine: Kahneman-style System 1 + System 2 cognitive engine.

Inspired by "Thinking Fast and Slow" (Kahneman 2011):
    - System 1: fast, intuitive, pattern-based. Uses the System1PatternLibrary.
    - System 2: slow, analytical, LLM-based. Activated when System 1 lacks
      confidence or when the mode demands deliberate reasoning.

The engine routes every decision through a cascade:
    1. Exact hash match    (System 1, ~0 ms)
    2. k-NN state match    (System 1, ~1 ms)
    3. Fuzzy text match    (System 1, ~5 ms)
    4. LLM fallback        (System 2, ~500-2000 ms)

When System 2 produces a decision, it is fed back into System 1 via `learn()`,
so the library grows over time and System 1 gradually takes over more decisions.

Modes:
    - "auto":    automatic escalation based on confidence thresholds
    - "system1": force System 1 only (fast, no LLM cost)
    - "system2": force System 2 always (full deliberation)
    - "expert":  hybrid -- System 1 + lightweight System 2 audit
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

logger = logging.getLogger("btcu_harness.cognition.dual_system")

from ..core.state import CognitiveState, SPACE_SIZE
from ..llm.bridge import LLMBridge

from .system1 import CognitivePattern, System1PatternLibrary
from .audit import CognitiveAuditor
from .defense import CognitiveSafetyGuard


@dataclass
class Decision:
    """
    A complete decision record from the dual-system engine.

    Captures which system produced the action, confidence, cost, latency,
    and audit recommendations for downstream analysis.
    """

    action: str
    source: str  # "system1_exact", "system1_knn", "system1_fuzzy", "system2"
    confidence: float
    system_used: str  # "system1" or "system2"
    tokens_consumed: int
    latency_ms: float
    pattern_matched: bool
    alternative_actions: List[str] = field(default_factory=list)
    cognitive_state: int = 0
    audit_recommendation: Optional[str] = None

    # --- extended metadata ---
    input_text: str = ""
    pattern: Optional[CognitivePattern] = None
    knn_matches: List[CognitivePattern] = field(default_factory=list)
    llm_response: Optional[str] = None

    def summary(self) -> str:
        return (
            f"Decision(source={self.source}, action={self.action[:50]}, "
            f"confidence={self.confidence:.2f}, latency={self.latency_ms:.1f}ms, "
            f"tokens={self.tokens_consumed})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "source": self.source,
            "confidence": self.confidence,
            "system_used": self.system_used,
            "tokens_consumed": self.tokens_consumed,
            "latency_ms": self.latency_ms,
            "pattern_matched": self.pattern_matched,
            "alternative_actions": self.alternative_actions,
            "cognitive_state": self.cognitive_state,
            "audit_recommendation": self.audit_recommendation,
        }


class DualSystemDecisionEngine:
    """
    Kahneman-style System 1 (fast/intuitive) + System 2 (slow/analytical)
    cognitive engine for the BTCU Harness.

    The engine manages the decision cascade, tracks statistics, and
    feeds System 2 outputs back into System 1 for incremental learning.
    """

    # Confidence thresholds for automatic escalation
    SYSTEM1_MIN_CONFIDENCE = 0.5
    SYSTEM2_AUDIT_THRESHOLD = 0.3

    def __init__(
        self,
        pattern_library: System1PatternLibrary,
        llm_bridge: Optional[LLMBridge] = None,
    ) -> None:
        """
        Args:
            pattern_library: the System 1 pattern library (fast pathway)
            llm_bridge: optional LLM bridge for System 2 (slow pathway)
        """
        self.system1 = pattern_library
        self.system2 = llm_bridge
        self.mode: str = "auto"  # auto / system1 / system2 / expert

        # Cognitive laziness defense system
        self.safety_guard = CognitiveSafetyGuard()
        self.auditor = CognitiveAuditor(llm_bridge)

        # Decision history for audit and replay
        self.decision_history: List[Decision] = []

        # Statistics
        self.stats: Dict[str, Any] = {
            "total_decisions": 0,
            "system1_exact": 0,
            "system1_knn": 0,
            "system1_fuzzy": 0,
            "system2_fallback": 0,
            "system2_forced": 0,
            "total_latency_ms": 0.0,
            "total_tokens": 0,
            "avg_confidence": 0.0,
        }

        # Coverage tracking
        self._states_seen: set = set()

    # ------------------------------------------------------------------
    # Core decision method
    # ------------------------------------------------------------------

    def decide(
        self,
        input_text: str,
        state: CognitiveState,
        session_id: str = "default",
        mode: Optional[str] = None,
        epsilon: float = 0.1,
    ) -> Decision:
        """
        Execute the full System 1 / System 2 decision cascade.

        Args:
            input_text: the raw user/agent input
            state: the current cognitive state (9D ternary)
            session_id: trace identifier for logging
            mode: override engine mode for this decision
            epsilon: exploration rate for random System 2 sampling

        Returns:
            Decision with full provenance metadata.
        """
        start_time = time.perf_counter()
        active_mode = mode or self.mode

        self._states_seen.add(state.index)

        # Epsilon exploration check before System 1
        session_stats = {
            "coverage": self.system1.get_state_coverage(),
            "total_decisions": self.stats["total_decisions"],
        }
        if self.safety_guard.should_explore(epsilon, session_stats):
            return self._run_system2(
                input_text, state, session_id, start_time,
                source_label="system2_explore", reason="epsilon-exploration"
            )

        # ------------------------------------------------------------------
        # 1. System 1: exact hash match
        # ------------------------------------------------------------------
        if active_mode in ("auto", "system1", "expert"):
            exact_match = self.system1.match_exact(input_text)
            if exact_match:
                # Cognitive safety guard: check for pattern rigidity
                matched_state = CognitiveState.from_values(exact_match.state_values)
                rigidity = self.safety_guard.detect_rigidity(
                    current_state=state,
                    matched_pattern_state=matched_state,
                )
                if rigidity["rigid"]:
                    # Pattern is being applied to a dissimilar state -- downgrade to System 2
                    return self._run_system2(
                        input_text, state, session_id, start_time,
                        source_label="system2_rigidity", reason=rigidity["recommendation"],
                        original_pattern=exact_match,
                    )

                latency = (time.perf_counter() - start_time) * 1000
                decision = Decision(
                    action=exact_match.action,
                    source="system1_exact",
                    confidence=exact_match.computed_confidence,
                    system_used="system1",
                    tokens_consumed=0,
                    latency_ms=latency,
                    pattern_matched=True,
                    alternative_actions=[],
                    cognitive_state=state.index,
                    audit_recommendation=None,
                    input_text=input_text,
                    pattern=exact_match,
                )
                self._record_decision(decision)
                return decision

        # ------------------------------------------------------------------
        # 2. System 1: k-NN match in 9D cognitive space
        # ------------------------------------------------------------------
        if active_mode in ("auto", "system1", "expert"):
            knn_matches = self.system1.match_knn(
                list(state.values), k=3, min_confidence=self.SYSTEM1_MIN_CONFIDENCE
            )
            if knn_matches:
                best = knn_matches[0]
                # Check rigidity for the nearest match
                matched_state = CognitiveState.from_values(best.state_values)
                rigidity = self.safety_guard.detect_rigidity(
                    current_state=state,
                    matched_pattern_state=matched_state,
                )
                if rigidity["rigid"]:
                    return self._run_system2(
                        input_text, state, session_id, start_time,
                        source_label="system2_rigidity", reason=rigidity["recommendation"],
                        original_pattern=best,
                    )

                alts = [m.action for m in knn_matches[1:3]]
                latency = (time.perf_counter() - start_time) * 1000
                decision = Decision(
                    action=best.action,
                    source="system1_knn",
                    confidence=best.computed_confidence,
                    system_used="system1",
                    tokens_consumed=0,
                    latency_ms=latency,
                    pattern_matched=True,
                    alternative_actions=alts,
                    cognitive_state=state.index,
                    audit_recommendation=None,
                    input_text=input_text,
                    pattern=best,
                    knn_matches=knn_matches,
                )
                self._record_decision(decision)
                return decision

        # ------------------------------------------------------------------
        # 3. System 1: fuzzy text match
        # ------------------------------------------------------------------
        if active_mode in ("auto", "system1", "expert"):
            fuzzy_match = self.system1.match_fuzzy(input_text)
            if fuzzy_match:
                matched_state = CognitiveState.from_values(fuzzy_match.state_values)
                rigidity = self.safety_guard.detect_rigidity(
                    current_state=state,
                    matched_pattern_state=matched_state,
                )
                if rigidity["rigid"]:
                    return self._run_system2(
                        input_text, state, session_id, start_time,
                        source_label="system2_rigidity", reason=rigidity["recommendation"],
                        original_pattern=fuzzy_match,
                    )

                latency = (time.perf_counter() - start_time) * 1000
                decision = Decision(
                    action=fuzzy_match.action,
                    source="system1_fuzzy",
                    confidence=fuzzy_match.computed_confidence,
                    system_used="system1",
                    tokens_consumed=0,
                    latency_ms=latency,
                    pattern_matched=True,
                    alternative_actions=[],
                    cognitive_state=state.index,
                    audit_recommendation=None,
                    input_text=input_text,
                    pattern=fuzzy_match,
                )
                self._record_decision(decision)
                return decision

        # ------------------------------------------------------------------
        # 4. System 2: LLM fallback (slow deliberation)
        # ------------------------------------------------------------------
        if active_mode in ("auto", "system2", "expert") and self.system2 is not None:
            return self._run_system2(
                input_text, state, session_id, start_time,
                source_label="system2_forced" if active_mode == "system2" else "system2",
                reason=None,
            )

        # ------------------------------------------------------------------
        # 5. No System 2 available -- return a low-confidence default
        # ------------------------------------------------------------------
        latency = (time.perf_counter() - start_time) * 1000
        decision = Decision(
            action="unknown",
            source="system1_miss",
            confidence=0.0,
            system_used="system1",
            tokens_consumed=0,
            latency_ms=latency,
            pattern_matched=False,
            alternative_actions=[],
            cognitive_state=state.index,
            audit_recommendation="No pattern match and no System 2 configured.",
            input_text=input_text,
        )
        self._record_decision(decision)
        return decision

    # ------------------------------------------------------------------
    # System 2 execution with audit integration
    # ------------------------------------------------------------------

    def _run_system2(
        self,
        input_text: str,
        state: CognitiveState,
        session_id: str,
        start_time: float,
        source_label: str,
        reason: Optional[str] = None,
        original_pattern: Optional[CognitivePattern] = None,
    ) -> Decision:
        """Execute System 2 (LLM) with optional post-decision audit of a System 1 pattern."""
        system2_result = self._invoke_system2(input_text, state, session_id)
        latency = (time.perf_counter() - start_time) * 1000

        # Build decision
        audit_recommendation = reason
        if system2_result.get("audit") and not audit_recommendation:
            audit_recommendation = system2_result["audit"]

        decision = Decision(
            action=system2_result["action"],
            source=source_label,
            confidence=system2_result.get("confidence", 0.7),
            system_used="system2",
            tokens_consumed=system2_result.get("tokens", 0),
            latency_ms=latency,
            pattern_matched=False,
            alternative_actions=system2_result.get("alternatives", []),
            cognitive_state=state.index,
            audit_recommendation=audit_recommendation,
            input_text=input_text,
            llm_response=system2_result.get("raw_response"),
        )

        # Learn from System 2 output (feed back into System 1)
        self.system1.learn(
            input_text=input_text,
            state=state,
            action=system2_result["action"],
            context={
                "input_text": input_text,
                "features": System1PatternLibrary._extract_text_features(input_text),
                "session_id": session_id,
                "source": "system2",
            },
            success=True,
            system2_audit_score=system2_result.get("confidence", 0.7),
        )

        # If there was an original System 1 pattern, audit it and update its score
        if original_pattern is not None:
            try:
                audit = self.auditor.audit_decision(
                    original_decision=replace(
                        decision,
                        action=original_pattern.action,
                        source="system1_original",
                        confidence=original_pattern.computed_confidence,
                    ),
                    input_text=input_text,
                    context={"state": state, "session_id": session_id},
                )
                # Update the pattern's audit score with the quality delta
                if audit.quality_delta != 0.0:
                    original_pattern.system2_audit_score = max(
                        0.0,
                        min(1.0, original_pattern.system2_audit_score + audit.quality_delta),
                    )
            except Exception as exc:
                logger.warning("[DualSystemDecisionEngine] Audit of original pattern failed: %s", exc)

        self._record_decision(decision)
        return decision

    # ------------------------------------------------------------------
    # System 2 invocation
    # ------------------------------------------------------------------

    def _invoke_system2(
        self,
        input_text: str,
        state: CognitiveState,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Invoke the LLM bridge for a slow, deliberate decision.

        Returns a dict with keys: action, confidence, tokens, alternatives, audit, raw_response.
        """
        if self.system2 is None:
            return {
                "action": "unknown",
                "confidence": 0.0,
                "tokens": 0,
                "alternatives": [],
                "audit": "System 2 not available.",
                "raw_response": None,
            }

        # Build a structured prompt for the LLM
        system_prompt = (
            "You are a deliberate decision engine (System 2) for the BTCU cognitive architecture. "
            "Given the user's input and the current 9D ternary cognitive state, produce a decision. "
            "Respond in JSON with keys: action (string), confidence (0.0-1.0), "
            "alternatives (list of strings), audit (string explaining reasoning)."
        )
        user_prompt = (
            f"Input: {input_text}\n"
            f"Cognitive state #{state.index} values: {list(state.values)}\n"
            f"Session: {session_id}\n"
            f"Pattern library coverage: {self.system1.get_state_coverage():.4%}"
        )

        raw_response = self.system2.query(
            f"{system_prompt}\n\n{user_prompt}"
        )

        # Attempt to parse JSON response; fall back to raw text
        try:
            parsed = json.loads(raw_response)
            return {
                "action": parsed.get("action", "unknown"),
                "confidence": parsed.get("confidence", 0.5),
                "tokens": len(raw_response.split()),  # rough proxy
                "alternatives": parsed.get("alternatives", []),
                "audit": parsed.get("audit"),
                "raw_response": raw_response,
            }
        except (json.JSONDecodeError, ValueError):
            # Raw text fallback -- treat entire response as action
            return {
                "action": raw_response.strip()[:200],
                "confidence": 0.5,
                "tokens": len(raw_response.split()),
                "alternatives": [],
                "audit": "System 2 returned non-JSON response.",
                "raw_response": raw_response,
            }

    # ------------------------------------------------------------------
    # Statistics & coverage
    # ------------------------------------------------------------------

    def _record_decision(self, decision: Decision) -> None:
        """Update internal statistics and append to history."""
        self.decision_history.append(decision)

        self.stats["total_decisions"] += 1
        self.stats["total_latency_ms"] += decision.latency_ms
        self.stats["total_tokens"] += decision.tokens_consumed

        # Update source-specific counters
        if decision.source.startswith("system1_"):
            key = decision.source.replace("system1_", "system1_")
        else:
            key = decision.source
        self.stats[key] = self.stats.get(key, 0) + 1

        # Rolling average confidence
        n = self.stats["total_decisions"]
        self.stats["avg_confidence"] = (
            self.stats["avg_confidence"] * (n - 1) + decision.confidence
        ) / n

    def get_coverage_stats(self) -> Dict[str, Any]:
        """Return System 1 coverage and engine performance metrics."""
        total = self.stats["total_decisions"]
        system1_total = (
            self.stats.get("system1_exact", 0)
            + self.stats.get("system1_knn", 0)
            + self.stats.get("system1_fuzzy", 0)
        )
        system2_total = (
            self.stats.get("system2_fallback", 0)
            + self.stats.get("system2_forced", 0)
            + self.stats.get("system2", 0)
        )

        return {
            "state_space_size": SPACE_SIZE,
            "states_covered": len(self.system1._covered_states),
            "coverage_pct": self.system1.get_state_coverage() * 100,
            "states_seen_by_engine": len(self._states_seen),
            "total_decisions": total,
            "system1_hits": system1_total,
            "system1_hit_rate": system1_total / max(1, total),
            "system2_hits": system2_total,
            "system2_hit_rate": system2_total / max(1, total),
            "avg_latency_ms": (
                self.stats["total_latency_ms"] / max(1, total)
            ),
            "avg_confidence": self.stats["avg_confidence"],
            "total_tokens_consumed": self.stats["total_tokens"],
            "pattern_library_stats": self.system1.stats(),
        }

    def reset_stats(self) -> None:
        """Reset all accumulated statistics (keeps pattern library intact)."""
        self.stats = {
            "total_decisions": 0,
            "system1_exact": 0,
            "system1_knn": 0,
            "system1_fuzzy": 0,
            "system2_fallback": 0,
            "system2_forced": 0,
            "total_latency_ms": 0.0,
            "total_tokens": 0,
            "avg_confidence": 0.0,
        }
        self.decision_history.clear()
        self._states_seen.clear()

    def summary(self) -> str:
        """Human-readable summary of engine state."""
        cov = self.get_coverage_stats()
        lines = [
            "=== DualSystemDecisionEngine ===",
            f"Mode: {self.mode}",
            f"Pattern library: {self.system1.pattern_count} patterns, "
            f"{cov['coverage_pct']:.4f}% state coverage",
            f"Decisions: {cov['total_decisions']} total",
            f"  System 1: {cov['system1_hits']} ({cov['system1_hit_rate']:.1%})",
            f"  System 2: {cov['system2_hits']} ({cov['system2_hit_rate']:.1%})",
            f"Avg latency: {cov['avg_latency_ms']:.1f} ms",
            f"Avg confidence: {cov['avg_confidence']:.2f}",
            f"Tokens consumed: {cov['total_tokens_consumed']}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"DualSystemDecisionEngine(mode={self.mode}, "
            f"patterns={self.system1.pattern_count}, "
            f"decisions={self.stats['total_decisions']})"
        )
