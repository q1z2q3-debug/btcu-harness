"""
System 2 Audit for System 1 in the BTCU dual-system architecture.

Kahneman's "Thinking Fast and Slow" -- System 2 is the slow, analytical,
deliberate counterpart to System 1's fast intuition.  The ``CognitiveAuditor``
periodically re-evaluates System 1 decisions using full LLM reasoning to
detect quality degradation, hidden biases, and blind spots that fast
pattern-matching cannot self-correct.

The auditor is designed to run asynchronously or in a background thread,
sampling a configurable fraction of System 1 decisions and producing
structured audit reports with actionable recommendations.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..core.state import CognitiveState, NUM_DIMENSIONS
from ..llm.bridge import LLMBridge
from .system1 import CognitivePattern

if TYPE_CHECKING:
    from .dual_system import Decision

logger = logging.getLogger("btcu_harness.cognition.audit")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditConstants:
    """Tunable hyper-parameters for the System 2 cognitive auditor."""

    DEFAULT_SAMPLE_RATE: float = 0.05
    MIN_SAMPLE_SIZE: int = 1
    MAX_BATCH_SIZE: int = 100
    DEFAULT_AUDIT_TEMPERATURE: float = 0.1
    MAX_RETRIES_ON_BRIDGE_FAILURE: int = 1
    QUALITY_DELTA_SCALE: float = 2.0
    HIGH_QUALITY_THRESHOLD: float = 0.5
    LOW_QUALITY_THRESHOLD: float = -0.3


# ---------------------------------------------------------------------------
# AuditResult
# ---------------------------------------------------------------------------

@dataclass
class AuditResult:
    """Result of a single decision audit.

    Captures the comparison between System 1's original decision and
    System 2's recommended decision, along with quality metrics.
    """

    original_action: str
    recommended_action: str
    agreement: bool
    quality_delta: float
    concerns: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)
    input_text: str = ""
    state_index: int = 0
    pattern_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_action": self.original_action,
            "recommended_action": self.recommended_action,
            "agreement": self.agreement,
            "quality_delta": round(self.quality_delta, 4),
            "concerns": self.concerns,
            "suggestions": self.suggestions,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
            "input_text": self.input_text,
            "state_index": self.state_index,
            "pattern_hash": self.pattern_hash,
        }


# ---------------------------------------------------------------------------
# AuditReport
# ---------------------------------------------------------------------------

@dataclass
class AuditReport:
    """Aggregated batch-audit report.

    Summarises the findings of a batch audit, including overall agreement
    rates, average quality deltas, and flagged patterns.
    """

    total_audited: int
    agreement_rate: float
    avg_quality_delta: float
    concerns_found: int
    patterns_flagged: List[str]
    individual_results: List[AuditResult]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_audited": self.total_audited,
            "agreement_rate": round(self.agreement_rate, 4),
            "avg_quality_delta": round(self.avg_quality_delta, 4),
            "concerns_found": self.concerns_found,
            "patterns_flagged": self.patterns_flagged,
            "timestamp": self.timestamp,
            "individual_results": [r.to_dict() for r in self.individual_results],
        }


# ---------------------------------------------------------------------------
# CognitiveAuditor
# ---------------------------------------------------------------------------

class CognitiveAuditor:
    """System 2 periodic auditor for System 1 decisions.

    Re-evaluates System 1's fast-intuition decisions with full LLM reasoning,
detecting quality degradation, bias drift, and hidden errors that fast
pattern-matching cannot self-correct.

    Workflow
    --------
    1. ``audit_decision`` -- re-run a single System 1 decision through System 2
    2. ``audit_batch``    -- randomly sample 5 % of recent decisions for audit
    3. ``generate_report``-- produce a markdown summary of findings
    """

    def __init__(
        self,
        llm_bridge: Optional[LLMBridge] = None,
        constants: Optional[AuditConstants] = None,
    ) -> None:
        self.llm_bridge = llm_bridge
        self.constants = constants or AuditConstants()
        self._audit_history: List[AuditResult] = []

    # ------------------------------------------------------------------
    # 1. Single decision audit
    # ------------------------------------------------------------------

    def audit_decision(
        self,
        original_decision: "Decision",
        input_text: str,
        context: Dict[str, Any],
    ) -> AuditResult:
        """Re-run a single System 1 decision through System 2 (LLM) and compare.

        The original decision (from fast System 1 pattern matching) is
        re-evaluated by slow, deliberate System 2 reasoning.  The comparison
        reveals whether the fast intuition was sound or if it missed important
        nuance.

        Args:
            original_decision: the Decision produced by System 1.
            input_text: the raw user/agent input that triggered the decision.
            context: additional context dict (may contain ``state``, ``session_id``,
                etc.).

        Returns:
            ``AuditResult`` with the comparison and quality assessment.
        """
        if self.llm_bridge is None:
            logger.warning("[CognitiveAuditor] No LLM bridge configured -- skipping audit.")
            return AuditResult(
                original_action=original_decision.action,
                recommended_action=original_decision.action,
                agreement=True,
                quality_delta=0.0,
                concerns=["LLM bridge not available -- audit skipped."],
                suggestions=["Configure an LLM bridge for System 2 auditing."],
                reasoning="No System 2 available to perform audit.",
                input_text=input_text,
                state_index=original_decision.cognitive_state,
                pattern_hash=getattr(original_decision.pattern, "input_hash", None),
            )

        # Build the audit prompt for System 2
        system_prompt = self._build_audit_prompt(input_text, original_decision, context)

        try:
            raw_response = self.llm_bridge.query(system_prompt)
        except Exception as exc:
            logger.error("[CognitiveAuditor] LLM query failed: %s", exc)
            return AuditResult(
                original_action=original_decision.action,
                recommended_action="unknown",
                agreement=False,
                quality_delta=0.0,
                concerns=[f"LLM query failed: {exc}"],
                suggestions=["Retry with a different LLM provider or reduce load."],
                reasoning="System 2 audit failed due to LLM error.",
                input_text=input_text,
                state_index=original_decision.cognitive_state,
                pattern_hash=getattr(original_decision.pattern, "input_hash", None),
            )

        # Parse the structured audit response
        parsed = self._parse_audit_response(raw_response, original_decision)
        parsed.input_text = input_text
        parsed.state_index = original_decision.cognitive_state
        parsed.pattern_hash = getattr(original_decision.pattern, "input_hash", None)

        self._audit_history.append(parsed)
        return parsed

    def _build_audit_prompt(
        self, input_text: str, decision: Decision, context: Dict[str, Any]
    ) -> str:
        """Construct the System 2 audit prompt."""
        state_str = str(list(context.get("state", CognitiveState.all_void()).values))

        prompt = (
            "You are a cognitive auditor (System 2) evaluating a System 1 "
            "decision in the BTCU dual-system architecture.\n\n"
            "Your task:\n"
            "1. Review the input and the System 1 decision.\n"
            "2. Produce the decision YOU would make with full deliberation.\n"
            "3. Compare: does the System 1 decision agree with yours?\n"
            "4. Rate the quality difference on a scale from -1 (much worse) "
            "to +1 (much better).\n"
            "5. List any concerns or suggestions for improvement.\n\n"
            "Respond ONLY in valid JSON with this exact structure:\n"
            "{\n"
            '  "recommended_action": "string",\n'
            '  "agreement": true|false,\n'
            '  "quality_delta": float,\n'
            '  "concerns": ["string", ...],\n'
            '  "suggestions": ["string", ...],\n'
            '  "reasoning": "string"\n'
            "}\n\n"
            "--- Input ---\n"
            f"{input_text}\n\n"
            "--- System 1 Decision ---\n"
            f"Action: {decision.action}\n"
            f"Source: {decision.source}\n"
            f"Confidence: {decision.confidence:.3f}\n"
            f"Cognitive State: #{decision.cognitive_state} ({state_str})\n"
            f"Pattern Matched: {decision.pattern_matched}\n\n"
            "--- System 2 Audit ---\n"
        )
        return prompt

    def _parse_audit_response(
        self, raw_response: str, original_decision: Decision
    ) -> AuditResult:
        """Parse the LLM's JSON audit response, falling back to safe defaults."""
        try:
            data = json.loads(raw_response)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "[CognitiveAuditor] Non-JSON response from LLM: %s",
                raw_response[:200],
            )
            return AuditResult(
                original_action=original_decision.action,
                recommended_action=raw_response.strip()[:200],
                agreement=False,
                quality_delta=0.0,
                concerns=["LLM returned non-JSON audit response."],
                suggestions=["Check LLM prompt or reduce temperature."],
                reasoning=f"Parse error: {exc}",
            )

        recommended = str(data.get("recommended_action", "unknown"))
        agreement = bool(data.get("agreement", False))
        quality_delta = float(data.get("quality_delta", 0.0))
        concerns = list(data.get("concerns", []))
        suggestions = list(data.get("suggestions", []))
        reasoning = str(data.get("reasoning", ""))

        # Clamp quality_delta to [-1, +1]
        quality_delta = max(-1.0, min(1.0, quality_delta))

        return AuditResult(
            original_action=original_decision.action,
            recommended_action=recommended,
            agreement=agreement,
            quality_delta=quality_delta,
            concerns=concerns,
            suggestions=suggestions,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # 2. Batch audit
    # ------------------------------------------------------------------

    def audit_batch(
        self,
        decisions: List[Decision],
        sample_rate: Optional[float] = None,
        context_provider=None,
    ) -> AuditReport:
        """Randomly sample and audit a fraction of System 1 decisions.

        System 2 auditing is expensive (LLM calls cost time and money).  This
        method limits the audit to a random sample, with a minimum of one
        decision per batch to ensure continuous feedback.

        Args:
            decisions: list of recent ``Decision`` objects to sample from.
            sample_rate: fraction ``[0, 1]`` of decisions to audit;
                defaults to ``AuditConstants.DEFAULT_SAMPLE_RATE`` (5 %).
            context_provider: optional callable ``(Decision) -> Dict`` that
                supplies context for each decision; defaults to empty dict.

        Returns:
            ``AuditReport`` with aggregated statistics.
        """
        sample_rate = sample_rate if sample_rate is not None else self.constants.DEFAULT_SAMPLE_RATE

        if not decisions:
            return AuditReport(
                total_audited=0,
                agreement_rate=0.0,
                avg_quality_delta=0.0,
                concerns_found=0,
                patterns_flagged=[],
                individual_results=[],
            )

        # Determine sample size
        sample_size = max(
            self.constants.MIN_SAMPLE_SIZE,
            int(len(decisions) * sample_rate),
        )
        sample_size = min(sample_size, self.constants.MAX_BATCH_SIZE, len(decisions))

        # Randomly sample decisions
        sampled = random.sample(decisions, sample_size)

        results: List[AuditResult] = []
        patterns_flagged: set = set()

        for decision in sampled:
            ctx = {}
            if context_provider is not None:
                try:
                    ctx = context_provider(decision)
                except Exception as exc:
                    logger.warning(
                        "[CognitiveAuditor] context_provider failed: %s", exc
                    )

            result = self.audit_decision(
                original_decision=decision,
                input_text=decision.input_text,
                context=ctx,
            )
            results.append(result)

            # Flag patterns with low quality delta
            if (
                result.quality_delta < self.constants.LOW_QUALITY_THRESHOLD
                and result.pattern_hash
            ):
                patterns_flagged.add(result.pattern_hash)

        # Aggregate statistics
        agreement_count = sum(1 for r in results if r.agreement)
        avg_qd = (
            sum(r.quality_delta for r in results) / len(results) if results else 0.0
        )
        concerns_count = sum(len(r.concerns) for r in results)

        report = AuditReport(
            total_audited=len(results),
            agreement_rate=agreement_count / max(1, len(results)),
            avg_quality_delta=avg_qd,
            concerns_found=concerns_count,
            patterns_flagged=sorted(patterns_flagged),
            individual_results=results,
        )

        logger.info(
            "[CognitiveAuditor] Batch audit complete: "
            "n=%d, agreement=%.2f, avg_qd=%.3f, flagged=%d",
            report.total_audited,
            report.agreement_rate,
            report.avg_quality_delta,
            len(report.patterns_flagged),
        )

        return report

    # ------------------------------------------------------------------
    # 3. Report generation
    # ------------------------------------------------------------------

    def generate_report(self) -> str:
        """Generate a markdown report of all accumulated audit findings.

        This aggregates the entire audit history (not just the most recent
        batch) and produces a human-readable markdown document suitable for
        logging, dashboards, or version control.

        Returns:
            Markdown-formatted string.
        """
        if not self._audit_history:
            return "# Cognitive Audit Report\n\nNo audits have been performed yet.\n"

        total = len(self._audit_history)
        agreements = sum(1 for r in self._audit_history if r.agreement)
        avg_qd = sum(r.quality_delta for r in self._audit_history) / total
        total_concerns = sum(len(r.concerns) for r in self._audit_history)

        flagged_patterns = sorted(
            {
                r.pattern_hash
                for r in self._audit_history
                if r.pattern_hash and r.quality_delta < self.constants.LOW_QUALITY_THRESHOLD
            }
        )

        lines = [
            "# Cognitive Audit Report",
            "",
            "## Summary",
            "",
            f"- **Total Audits**: {total}",
            f"- **Agreement Rate**: {agreements / total:.1%}",
            f"- **Average Quality Delta**: {avg_qd:+.3f}",
            f"- **Total Concerns**: {total_concerns}",
            f"- **Flagged Patterns**: {len(flagged_patterns)}",
            "",
            "## Flagged Patterns",
            "",
        ]

        if flagged_patterns:
            for ph in flagged_patterns:
                lines.append(f"- `{ph[:16]}`")
        else:
            lines.append("No patterns flagged.")

        lines.extend(["", "## Recent Audit Details", ""])

        # Show the most recent 10 audits in detail
        for i, result in enumerate(reversed(self._audit_history[-10:]), 1):
            status = "OK" if result.agreement else "MISMATCH"
            lines.extend(
                [
                    f"### Audit #{i} [{status}]",
                    "",
                    f"- **Original Action**: {result.original_action[:60]}",
                    f"- **Recommended Action**: {result.recommended_action[:60]}",
                    f"- **Quality Delta**: {result.quality_delta:+.3f}",
                    f"- **State**: #{result.state_index}",
                ]
            )
            if result.pattern_hash:
                lines.append(f"- **Pattern Hash**: {result.pattern_hash[:16]}")
            if result.concerns:
                lines.append("- **Concerns**:")
                for c in result.concerns:
                    lines.append(f"  - {c}")
            if result.suggestions:
                lines.append("- **Suggestions**:")
                for s in result.suggestions:
                    lines.append(f"  - {s}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 4. History management
    # ------------------------------------------------------------------

    def get_audit_history(self) -> List[AuditResult]:
        """Return a copy of all accumulated audit results."""
        return list(self._audit_history)

    def clear_history(self) -> None:
        """Clear the accumulated audit history."""
        self._audit_history.clear()

    def get_pattern_quality_scores(self) -> Dict[str, float]:
        """Compute average quality delta per pattern hash.

        Returns:
            Mapping ``pattern_hash -> avg_quality_delta``.
        """
        scores: Dict[str, List[float]] = {}
        for result in self._audit_history:
            if result.pattern_hash:
                scores.setdefault(result.pattern_hash, []).append(result.quality_delta)

        return {
            ph: sum(vals) / len(vals) for ph, vals in scores.items() if vals
        }
