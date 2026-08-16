"""
BTCU Harness - Basic Usage Example

This example demonstrates the full lifecycle of a BTCU agent:
1. Initialize with default dimensions
2. Process cognitive inputs
3. Record outcomes
4. Generate third choices
5. Discover cognitive seasons
6. Advance growth stages
"""
import json
from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState
from btcu_harness.llm.bridge import LLMBridge


def mock_llm(prompt: str) -> str:
    """Simple mock LLM for demonstration."""
    return json.dumps({
        "assessments": [
            {"dimension": "past", "value": 1, "reason": "positive trend"},
            {"dimension": "present", "value": 1, "reason": "current strength"},
            {"dimension": "future", "value": -1, "reason": "uncertainty ahead"},
            {"dimension": "inner", "value": 1, "reason": "strong capability"},
            {"dimension": "middle", "value": 0, "reason": "moderate position"},
            {"dimension": "outer", "value": -1, "reason": "external risk"},
            {"dimension": "cause", "value": 1, "reason": "solid foundation"},
            {"dimension": "condition", "value": 0, "reason": "timing unclear"},
            {"dimension": "effect", "value": -1, "reason": "risk-reward poor"},
        ]
    })


def main():
    # 1. Create agent with mock LLM
    bridge = LLMBridge(callback=mock_llm)
    agent = BTCUAgent(growth_stage="school")
    agent.init_project(domain="default", llm_bridge=bridge)

    print(agent.status())
    print()

    # 2. Process an input
    response = agent.process("Should our team adopt a new framework?")
    print(response.summary())
    print()

    # 3. Record the outcome
    agent.record_outcome(
        state=response.current_state,
        decision="adopt",
        outcome="successful adoption",
        outcome_positive=True,
    )
    print("Recorded outcome: adopt -> success\n")

    # 4. Process a conflicting input
    response2 = agent.process("Or should we stick with the current stack?")
    print(response2.summary())
    print()

    # 5. Generate third choice
    third = agent.third_choice_gen.generate(
        response.current_state, response2.current_state
    )
    print(third.summary())
    print()

    # 6. Find decision path
    target = CognitiveState.all_yang()  # ideal state
    path = agent.pathfinder.find_path(response.current_state, target)
    print(path.summary())
    print()

    # 7. Discover patterns
    seasons = agent.discover_seasons()
    for s in seasons:
        print(f"[{s.season_type}] {s.description}")

    # 8. Advance growth stage
    print(f"\nAdvancing: {agent.advance_stage()}")
    print(f"Advancing: {agent.advance_stage()}")

    # 9. Export memory for transfer
    legacy = agent.export_memory()
    print(f"\nLegacy: {legacy['stats']}")


if __name__ == "__main__":
    main()
