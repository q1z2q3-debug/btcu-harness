"""
BTCU-LangChain Middleware: Cognitive enhancement for LangChain agents.

Provides BTCUCognitiveMiddleware — an AgentMiddleware that uses BTCU's
structured cognitive space (19,683 states) to enhance tool selection,
memory, and decision-making in LangChain agents.

Integration points (LangChain 1.x middleware hooks):
- before_agent: Initialize BTCU cognitive space for this session
- wrap_model_call: Project input → cognitive state → inject into system prompt
- after_model: Record tool choice in BTCU memory
- after_agent: Save cognitive trajectory for future sessions

Usage:
    from langchain.agents import create_agent
    from btcu_harness.langchain_integration import BTCUCognitiveMiddleware

    graph = create_agent(
        model=llm,
        tools=tools,
        middleware=[BTCUCognitiveMiddleware(api_key="sk-...")],
    )
    result = graph.invoke({"messages": [HumanMessage("What is 25 + 17?")]})
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from langchain.agents.middleware import AgentMiddleware
except ImportError:
    raise ImportError(
        "LangChain 1.x+ required. Install with: pip install 'btcu-harness[langchain]'"
    )

from langchain_core.messages import SystemMessage

from ..agent import BTCUAgent
from ..core.state import CognitiveState
from ..llm.bridge import LLMBridge

logger = logging.getLogger("btcu_harness.langchain")


class BTCUCognitiveMiddleware(AgentMiddleware):
    """
    LangChain AgentMiddleware that enhances agents with BTCU cognitive space.

    This middleware integrates BTCU's structured 19,683-state cognitive space
    into LangChain's agent execution pipeline. The cognitive state influences
    the agent by:
    - Adding structured context to the system prompt (polarity, intensity, stage)
    - Tracking which tools are chosen from which cognitive positions
    - Detecting patterns: "when in state #X, the agent usually picks tool Y"
    - Measuring decision consistency across sessions
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        dim_labels: Optional[List[str]] = None,
        growth_stage: str = "school",
        verbose: bool = False,
    ) -> None:
        """
        Initialize BTCU cognitive middleware.

        Args:
            api_key: LLM API key for BTCU cognitive projection
            provider: LLM provider (openai/anthropic/gemini)
            model: Model for cognitive projection
            dim_labels: 9 dimension labels for cognitive space
            growth_stage: school/internalize/graduate
            verbose: Log cognitive state at each step
        """
        super().__init__()

        self.btcu = BTCUAgent(growth_stage=growth_stage)
        self.btcu.init_project(
            domain="agent",
            dim_labels=dim_labels or [
                "Task_Understanding", "Tool_Matching", "Risk_Assessment",
                "User_Intent", "Resource_Cost", "Innovation",
                "Explainability", "Timeliness", "Long_Term_Value",
            ],
        )

        if api_key:
            self.btcu.llm_bridge = LLMBridge(
                provider=provider, api_key=api_key, model=model,
            )

        self.verbose = verbose
        self.total_projections = 0
        self.total_tool_observations = 0
        self._last_cognitive_state: Optional[CognitiveState] = None

    def before_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Initialize BTCU cognitive state for this agent session."""
        if self.verbose:
            logger.info(
                "[BTCU] Agent session started. Growth stage: %s",
                self.btcu.growth_stage,
            )
        return None

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        """
        Intercept model call to inject BTCU cognitive context.

        Projects the latest user message onto BTCU cognitive space,
        then appends the cognitive state as additional system context
        before calling the model. This is the primary integration point
        where BTCU influences the agent's tool selection.
        """
        user_text = self._extract_user_text(request.messages)

        if user_text:
            try:
                response = self.btcu.process(user_text)
                self.total_projections += 1
                self._last_cognitive_state = response.current_state

                if self.verbose:
                    cs = response.current_state
                    logger.info(
                        "[BTCU] State #%d | polarity=%+d | "
                        "YIN=%d VOID=%d YANG=%d",
                        cs.index, cs.polarity,
                        cs.yin_count, cs.void_count, cs.yang_count,
                    )

                context = self._format_cognitive_context(
                    response.current_state, response,
                )

                if request.system_message:
                    request.system_message = SystemMessage(
                        content=request.system_message.content + "\n\n" + context
                    )
                else:
                    request.system_message = SystemMessage(content=context)

            except Exception as e:
                logger.warning("[BTCU] Projection failed: %s", e)

        result = handler(request)
        self._record_tool_choice(result)
        return result

    def after_model(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Record tool choice in BTCU memory (if not already done in wrap_model_call)."""
        return None

    def after_agent(self, state: Any, runtime: Any) -> Optional[Dict[str, Any]]:
        """Session complete — save cognitive trajectory and summarize."""
        trajectory_len = self.btcu.trajectory.length
        pattern_count = (
            self.btcu.pattern_learner.pattern_count
            if hasattr(self.btcu.pattern_learner, "pattern_count")
            else 0
        )

        if self.verbose:
            logger.info(
                "[BTCU] Session complete. Trajectory: %d steps, "
                "Patterns: %d, Projections: %d",
                trajectory_len, pattern_count, self.total_projections,
            )
        return None

    def _extract_user_text(self, messages: List[Any]) -> str:
        """Extract the latest human message content from the message list."""
        for msg in reversed(messages):
            msg_type = getattr(msg, "type", None)
            msg_role = getattr(msg, "role", None)
            if msg_type == "human" or msg_role == "user":
                return getattr(msg, "content", str(msg))
        return ""

    def _record_tool_choice(self, result: Any) -> None:
        """Extract tool calls from model response and record in BTCU memory."""
        # Result can be ModelResponse, AIMessage, or ExtendedModelResponse
        ai_message = None
        if hasattr(result, "result"):
            # ModelResponse
            results = result.result
            if isinstance(results, list) and results:
                ai_message = results[0]
        elif hasattr(result, "tool_calls"):
            # AIMessage directly
            ai_message = result

        if ai_message is None:
            return

        tool_calls = getattr(ai_message, "tool_calls", None)
        if not tool_calls:
            if self.verbose:
                logger.info("[BTCU] Model returned final answer (no tools)")
            return

        self.total_tool_observations += len(tool_calls)

        for tc in tool_calls:
            tool_name = (
                tc.get("name")
                or tc.get("function", {}).get("name", "unknown")
                if isinstance(tc, dict)
                else getattr(tc, "name", "unknown")
            )

            # Record tool choice mapped to cognitive state
            if self._last_cognitive_state and self.btcu.ecology:
                from ..memory.ecology import CognitiveEvent
                event = CognitiveEvent(
                    state=self._last_cognitive_state,
                    prev_state=getattr(self.btcu, "_prev_state", None),
                    context={"tool": tool_name, "trigger": "model_decision"},
                )
                self.btcu.ecology.remember(event)
                self.btcu._prev_state = self._last_cognitive_state

        if self.verbose:
            names = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    names.append(
                        tc.get("name")
                        or tc.get("function", {}).get("name", "unknown")
                    )
                else:
                    names.append(getattr(tc, "name", "unknown"))
            logger.info("[BTCU] Tools chosen: %s", ", ".join(names))

    def _format_cognitive_context(
        self, state: CognitiveState, response: Any,
    ) -> str:
        """Format BTCU cognitive state as prompt context."""
        lines = [
            "=== Cognitive Context ===",
            f"State: #{state.index}",
            f"Polarity: {state.polarity:+d} "
            f"(YIN={state.yin_count}, VOID={state.void_count}, YANG={state.yang_count})",
        ]

        if state.polarity > 3:
            lines.append(
                "Disposition: High activation — action-oriented approach recommended"
            )
        elif state.polarity < -3:
            lines.append(
                "Disposition: High suppression — analytical, cautious approach recommended"
            )
        elif state.void_count >= 5:
            lines.append(
                "Disposition: Open/transformative — creative exploration recommended"
            )

        alignment = getattr(response, "self_alignment", None)
        if alignment is not None and alignment < 0.3:
            lines.append(
                f"Warning: Low self-alignment ({alignment:.0%}) — "
                "this response is far from the agent's typical profile"
            )

        lines.append("=== End Cognitive Context ===")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Return middleware statistics."""
        return {
            "total_projections": self.total_projections,
            "total_tool_observations": self.total_tool_observations,
            "trajectory_length": self.btcu.trajectory.length,
            "growth_stage": self.btcu.growth_stage,
            "unique_states_visited": len(set(
                p.state_index for p in
                getattr(self.btcu.pattern_learner, "patterns", [])
            )),
        }
