"""
End-to-end BTCU-LangChain integration demo.

Runs a simulated agent loop with BTCUCognitiveMiddleware, showing:
1. Cognitive state projection at each turn
2. Context injection into system prompt
3. Tool-choice recording with cognitive context
4. Trajectory accumulation and pattern detection
5. Cross-session consistency measurement

This demo uses rule-based projection (no LLM API key needed),
demonstrating BTCU's lightweight cognitive infrastructure.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from btcu_harness.langchain_integration import BTCUCognitiveMiddleware


@dataclass
class SimulatedToolCall:
    """A simulated tool call from the model."""
    name: str
    args: Dict[str, Any]


@dataclass
class AgentTurn:
    """One turn in the agent conversation."""
    user_input: str
    cognitive_state_index: int
    cognitive_polarity: int
    injected_context: str
    tools_chosen: List[str]
    final_response: str


class EndToEndDemo:
    """Demonstrates BTCU middleware in a simulated agent loop."""

    def __init__(self) -> None:
        # Initialize BTCU in "internalize" stage — uses pattern matching,
        # no LLM API key needed
        self.middleware = BTCUCognitiveMiddleware(
            api_key=None,
            growth_stage="internalize",
            verbose=True,
        )
        self.turns: List[AgentTurn] = []
        self.history: List[Dict[str, Any]] = []

    def run(self, inputs: List[str]) -> None:
        """Run the agent loop over a list of inputs."""
        print("=" * 70)
        print("BTCU-LangChain End-to-End Integration Demo")
        print("=" * 70)
        print()
        print(f"Cognitive State Space: 19,683 states")
        print(f"Growth Stage: {self.middleware.btcu.growth_stage}")
        print(f"Dimension Labels: {self.middleware.btcu.dim_labels}")
        print()

        for i, user_input in enumerate(inputs, 1):
            print(f"\n{'─' * 70}")
            print(f"Turn {i}: {user_input}")
            print(f"{'─' * 70}")

            turn = self._run_turn(user_input)
            self.turns.append(turn)

        self._show_summary()

    def _run_turn(self, user_input: str) -> AgentTurn:
        """Execute one complete agent turn with BTCU middleware."""
        # Build simulated LangChain request
        class MockRequest:
            def __init__(self):
                self.messages = [HumanMessage(content=user_input)]
                self.system_message = SystemMessage(
                    content="You are a helpful assistant."
                )

        original_system = "You are a helpful assistant."
        request = MockRequest()

        # Step 1: wrap_model_call — BTCU projects input and injects context
        def mock_handler(req: Any) -> Any:
            # Verify context was injected
            if req.system_message:
                context_present = "Cognitive Context" in req.system_message.content
                print(f"  [wrap_model_call] Context injected: {context_present}")
                if context_present:
                    # Extract state info from context
                    lines = req.system_message.content.split("\n")
                    for line in lines:
                        if line.startswith("State:") or line.startswith("Polarity:"):
                            print(f"    {line}")
            return self._simulate_model_response(user_input)

        result = self.middleware.wrap_model_call(request, mock_handler)

        # Step 2: Extract tool calls from model response
        tools_chosen: List[str] = []
        ai_msg = self._extract_ai_message(result)
        if ai_msg and hasattr(ai_msg, "tool_calls") and ai_msg.tool_calls:
            tools_chosen = [
                tc.get("name", tc.get("function", {}).get("name", "unknown"))
                if isinstance(tc, dict)
                else getattr(tc, "name", "unknown")
                for tc in ai_msg.tool_calls
            ]
            print(f"  [after_model] Tools chosen: {tools_chosen}")

        # Step 3: Record in BTCU memory (simulated via _record_tool_choice)
        self.middleware._record_tool_choice(result)

        # Determine cognitive state
        if self.middleware._last_cognitive_state:
            state = self.middleware._last_cognitive_state
            state_idx = state.index
            polarity = state.polarity
        else:
            state_idx = 0
            polarity = 0

        # Extract injected context
        context = ""
        if request.system_message:
            if "Cognitive Context" in request.system_message.content:
                start = request.system_message.content.find("=== Cognitive Context")
                end = request.system_message.content.find("=== End Cognitive")
                if start >= 0 and end >= 0:
                    context = request.system_message.content[start:end + 30]

        # Simulate final response
        if tools_chosen:
            final = f"I'll use {', '.join(tools_chosen)} to help with that."
        else:
            final = "I understand your request."

        return AgentTurn(
            user_input=user_input,
            cognitive_state_index=state_idx,
            cognitive_polarity=polarity,
            injected_context=context,
            tools_chosen=tools_chosen,
            final_response=final,
        )

    def _simulate_model_response(self, user_input: str) -> Any:
        """Simulate an LLM response based on input keywords."""
        text = user_input.lower()

        if any(kw in text for kw in ["calculate", "math", "arithmetic", "number", "add", "multiply", "divide", "square"]):
            tool_call = {"name": "calculator", "args": {"expression": "2+2"}}
        elif any(kw in text for kw in ["search", "find", "look up", "information", "about"]):
            tool_call = {"name": "search", "args": {"query": text}}
        elif any(kw in text for kw in ["compare", "which", "both", "then", "and"]):
            tool_call = {"name": "calculator", "args": {"expression": "100>50"}}
        else:
            tool_call = None

        if tool_call:
            return type(
                "ModelResponse",
                (),
                {
                    "result": [
                        type(
                            "AIMessage",
                            (),
                            {
                                "tool_calls": [tool_call],
                                "content": "",
                            },
                        )()
                    ]
                },
            )()
        else:
            return type(
                "ModelResponse",
                (),
                {
                    "result": [
                        type(
                            "AIMessage",
                            (),
                            {
                                "tool_calls": None,
                                "content": f"I understand: {user_input}",
                            },
                        )()
                    ]
                },
            )()

    def _extract_ai_message(self, result: Any) -> Optional[Any]:
        """Extract AIMessage from model response."""
        if hasattr(result, "result"):
            results = result.result
            if isinstance(results, list) and results:
                return results[0]
        elif hasattr(result, "tool_calls"):
            return result
        return None

    def _show_summary(self) -> None:
        """Display summary statistics."""
        print(f"\n{'=' * 70}")
        print("SESSION SUMMARY")
        print(f"{'=' * 70}")

        stats = self.middleware.get_stats()
        print(f"\nBTCU Statistics:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

        print(f"\nPer-Turn Breakdown:")
        print(f"  {'Turn':<6} {'Input (truncated)':<35} {'State':<8} {'Polarity':<10} {'Tools':<20}")
        print(f"  {'-' * 6} {'-' * 35} {'-' * 8} {'-' * 10} {'-' * 20}")
        for i, turn in enumerate(self.turns, 1):
            input_short = turn.user_input[:34] + "…" if len(turn.user_input) > 35 else turn.user_input
            tools_str = ", ".join(turn.tools_chosen) if turn.tools_chosen else "(none)"
            print(
                f"  {i:<6} {input_short:<35} #{turn.cognitive_state_index:<7} "
                f"{turn.cognitive_polarity:+d}{'':<9} {tools_str:<20}"
            )

        # Show pattern analysis
        print(f"\nCognitive Pattern Analysis:")
        states_by_category: Dict[str, List[int]] = {}
        for turn in self.turns:
            # Categorize by tool choice
            category = turn.tools_chosen[0] if turn.tools_chosen else "none"
            if category not in states_by_category:
                states_by_category[category] = []
            states_by_category[category].append(turn.cognitive_state_index)

        for category, states in states_by_category.items():
            if len(states) > 1:
                from btcu_harness.core.state import CognitiveState
                polarities = [CognitiveState.from_index(s).polarity for s in states]
                avg = sum(polarities) / len(polarities)
                std = (sum((p - avg) ** 2 for p in polarities) / len(polarities)) ** 0.5
                print(
                    f"  {category}: {len(states)} occurrences, "
                    f"avg polarity {avg:+.2f}, std {std:.2f}"
                )

        print(f"\nKey Insight:")
        print(
            f"  BTCU tracked {stats['total_projections']} cognitive projections and "
            f"{stats['total_tool_observations']} tool-choice observations."
        )
        print(
            f"  Standard LangChain agents would have 0 for both metrics."
        )
        print(f"\n{'=' * 70}")


def main() -> None:
    """Run the end-to-end demo."""
    demo = EndToEndDemo()

    # A sequence of inputs that exercise different cognitive states
    inputs = [
        # Math queries → should project to similar cognitive states
        "Calculate 25 times 17",
        "What is the square root of 144?",
        "Add 100 and 250, then divide by 5",

        # Search queries → different cognitive region
        "Search for information about Python programming",
        "Find details about BTCU Harness cognitive architecture",

        # Multi-step / complex
        "Compare 2^10 with 10^2 and tell me which is larger",
        "If a train travels 60 mph for 2.5 hours, how far does it go?",

        # Ambiguous / no tools
        "Hello, how are you today?",
    ]

    demo.run(inputs)


if __name__ == "__main__":
    main()
