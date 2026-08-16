"""
BTCU Harness - Quickstart Demo

This script demonstrates the core capabilities of BTCU in 5 minutes:
    1. Initialize a project with custom dimensions
    2. Process inputs through the cognitive pipeline
    3. Explore the 19,683-state space
    4. Generate third choices from conflicts
    5. Save and restore cognitive state

Run:
    python examples/quickstart.py

No LLM API key required - uses callback mode for demonstration.
"""

from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState, SPACE_SIZE
from btcu_harness.llm.bridge import LLMBridge


def demo_llm_callback(prompt: str) -> str:
    """Simulate LLM responses for demonstration (no API key needed)."""
    import json
    import re

    # If the prompt asks for dimension evaluation, return mock assessments
    if "assessments" in prompt or "dimension" in prompt.lower():
        assessments = []
        for i in range(9):
            assessments.append({
                "dimension": f"d{i}",
                "value": [1, -1, 0, 1, 0, -1, 1, 0, 1][i],
                "reason": f"demo assessment for dimension {i}",
            })
        return json.dumps({"assessments": assessments})

    return "Demo LLM response: The input suggests a balanced cognitive approach."


def main():
    print("=" * 60)
    print("BTCU Harness - Quickstart Demo")
    print("=" * 60)

    # 1. Initialize project
    print("\n[1] Initializing project...")
    agent = BTCUAgent(growth_stage="school", storage_path="/tmp/btcu_demo.json")
    agent.init_project(
        domain="agent",
        dim_labels=[
            "Task understanding", "Tool matching", "Risk assessment",
            "User intent", "Resource cost", "Innovation",
            "Explainability", "Timeliness", "Long-term value",
        ],
    )
    print(f"  Project initialized: 9 dimensions, {SPACE_SIZE} states")

    # 2. Explore the cognitive space
    print("\n[2] Exploring cognitive space...")
    all_void = CognitiveState.from_index(9841)  # all-void = center
    all_yang = CognitiveState.from_index(19682)  # all-yang
    print(f"  Center (all-void):  #{all_void.index}")
    print(f"    polarity={all_void.polarity}, void_count={all_void.void_count}")
    print(f"  Extreme (all-yang): #{all_yang.index}")
    print(f"    polarity={all_yang.polarity}, yang_count={all_yang.yang_count}")
    print(f"  Distance: {all_void.distance(all_yang)}")

    # 3. Process an input
    print("\n[3] Processing input...")
    agent.llm_bridge = LLMBridge(callback=demo_llm_callback)
    response = agent.process("Should we prioritize speed over quality?")
    print(f"  State: #{response.current_state.index}")
    print(f"  Polarity: {response.current_state.polarity:+d}")
    print(f"  YIN={response.current_state.yin_count} "
          f"VOID={response.current_state.void_count} "
          f"YANG={response.current_state.yang_count}")
    print(f"  Projection source: {response.projection.source}")
    print(f"  Self-alignment: {response.self_alignment:.2f}")
    print(f"  Trajectory length: {response.trajectory_length}")

    # 4. Generate third choices
    print("\n[4] Third choice generation...")
    state_a = CognitiveState.from_values([1, 1, 1, 1, 1, 1, 1, 1, 1])  # all YANG
    state_b = CognitiveState.from_values([-1, -1, -1, -1, -1, -1, -1, -1, -1])  # all YIN
    candidates = agent.third_choice_gen.generate_all(state_a, state_b)
    print(f"  Conflict: #{state_a.index} (all-YANG) vs #{state_b.index} (all-YIN)")
    print(f"  Generated {len(candidates)} third-choice candidates:")
    for i, c in enumerate(candidates[:3]):
        print(f"    [{i+1}] Strategy: {c.strategy}")
        print(f"        State #{c.state.index}, score={c.total_score:.2f}, "
              f"void={c.void_ratio:.0%}")

    # 5. Save and restore
    print("\n[5] Save and restore...")
    agent.save()
    print(f"  Saved to /tmp/btcu_demo.json")

    agent2 = BTCUAgent()
    success = agent2.load()
    print(f"  Restored: {success}")
    print(f"  Trajectory: {agent2.trajectory.length} points")
    print(f"  Growth stage: {agent2.growth_stage}")

    # 6. Status
    print("\n[6] Agent status:")
    print(agent2.status())

    print("\n" + "=" * 60)
    print("Quickstart complete! Next steps:")
    print("  - Set BTCU_LLM_API_KEY to use real LLM projection")
    print("  - Try: btcu init --domain decision")
    print("  - Try: uvicorn btcu_harness.api:app --port 8000")
    print("  - Read: docs/BTCU_Harness_Paper_v1.0.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
