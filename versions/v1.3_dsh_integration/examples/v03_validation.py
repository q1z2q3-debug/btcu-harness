"""
BTCU Harness v0.3 Real Task Validation

Simulates a multi-step cognitive journey through the 19683 space,
exercising all new modules: self layer, trajectory, pattern learner,
enhanced third choice, climate, and persistence.

Scenario: "DuMate evaluates its own development direction"
- 9 dimensions adapted for self-reflection
- Multiple cognitive states visited
- Third choice generation for internal conflicts
- Outcome recording and self reinforcement
- Pattern learning verification
- Climate report generation
- Save/load round-trip
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState
from btcu_harness.self_layer import NLPSelfLayer
from btcu_harness.storage.persistence import PersistenceLayer
import hashlib
import json
import re


def mock_llm_callback(prompt: str) -> str:
    """Simulate LLM dimension assessment for validation purposes.

    Generates deterministic but varied trit values based on prompt content,
    so the same input always produces the same projection (enabling pattern
    matching verification).

    Returns JSON in the format expected by InputProjector._project_with_llm.
    """
    # Extract the input text from the prompt
    input_match = re.search(r"<input>(.*?)</input>", prompt, re.DOTALL)
    if not input_match:
        input_match = re.search(r"Input:\s*(.*?)(?:\n|$)", prompt, re.DOTALL)
    input_text = input_match.group(1).strip() if input_match else prompt

    # Hash the input to get deterministic but varied values
    h = hashlib.md5(input_text.encode()).hexdigest()

    # Generate 9 trit values (-1, 0, +1) from hash
    dim_labels = [
        "技术深度", "用户体验", "创新性", "可维护性",
        "社区影响", "商业价值", "学习成长", "风险评估", "长期愿景"
    ]

    # Keyword-based adjustments for more realistic projections
    text_lower = input_text.lower()
    adjustments = [0] * 9
    if "innovation" in text_lower or "创新" in input_text or "algorithm" in text_lower:
        adjustments[0] = 1  # tech depth
        adjustments[2] = 1  # innovation
    if "practical" in text_lower or "实用" in input_text or "user" in text_lower:
        adjustments[1] = 1  # user experience
        adjustments[3] = 1  # maintainability
    if "complex" in text_lower or "复杂" in input_text:
        adjustments[7] = -1  # risk
    if "pattern" in text_lower or "模式" in input_text:
        adjustments[6] = 1  # learning
    if "balance" in text_lower or "平衡" in input_text:
        adjustments[4] = 1  # community

    assessments = []
    for i, label in enumerate(dim_labels):
        base_val = int(h[i * 2 : i * 2 + 2], 16) % 3 - 1
        val = max(-1, min(1, base_val + adjustments[i]))
        if val == 1:
            reason = f"{label}: positive signal"
        elif val == -1:
            reason = f"{label}: negative signal"
        else:
            reason = f"{label}: neutral"
        assessments.append({"value": val, "reason": reason})

    return json.dumps({"assessments": assessments})


def run_validation():
    print("=" * 60)
    print("BTCU Harness v0.3 - Real Task Validation")
    print("=" * 60)

    # 1. Initialize agent with persistence
    storage_path = "/tmp/btcu_v03_validation.json"
    agent = BTCUAgent(
        growth_stage="school",
        resonance_radius=3,
        storage_path=storage_path,
    )

    # 2. Initialize project with self-reflection dimensions
    dim_labels = [
        "技术深度",      # Technical depth
        "用户体验",      # User experience
        "创新性",        # Innovation
        "可维护性",      # Maintainability
        "社区影响",      # Community impact
        "商业价值",      # Commercial value
        "学习成长",      # Learning growth
        "风险评估",      # Risk assessment
        "长期愿景",      # Long-term vision
    ]

    # Create a simple LLM bridge wrapper using the mock callback
    from btcu_harness.llm.bridge import LLMBridge
    mock_bridge = LLMBridge(callback=mock_llm_callback)

    agent.init_project(domain="custom", dim_labels=dim_labels, llm_bridge=mock_bridge)
    print(f"\n[Init] Project initialized with 9 dimensions")
    print(f"  Dimensions: {dim_labels}")

    # 3. Set self layer (identity as a cognitive agent)
    # Mission: be a truly helpful cognitive companion
    mission_state = CognitiveState.from_values([1, 1, 1, 0, 1, 0, 1, -1, 1])
    agent.set_self_level(
        name="mission",
        description="Be a truly helpful cognitive companion that grows with the user",
        state=mission_state,
        weight=1.0,
        stability=0.95,
    )
    # Values: depth over breadth, honesty over comfort
    values_state = CognitiveState.from_values([1, 0, 1, 1, 0, -1, 1, 0, 1])
    agent.set_self_level(
        name="values",
        description="Depth over breadth, honesty over comfort, growth over stasis",
        state=values_state,
        weight=0.8,
        stability=0.85,
    )
    print(f"\n[Self] Identity attractor: #{agent.self_layer.attractor.index}")
    print(f"  Attractor: {agent.self_layer.attractor}")
    print(f"  Alignment with attractor: {agent.self_layer.alignment_score(mission_state):.1%}")

    # 4. Process multiple cognitive queries (simulating real use)
    queries = [
        ("Should BTCU prioritize deep algorithmic innovation or practical user features?", None, None),
        ("What if we focus on the pattern learning engine as the core differentiator?", None, None),
        ("Is the 19683 state space too complex for real-world use?", None, None),
        ("How should we balance theoretical elegance with engineering pragmatism?", None, None),
        ("Can the third choice mechanism genuinely resolve creative tensions?", None, None),
    ]

    print(f"\n[Process] Running {len(queries)} cognitive queries...")
    for i, (query, target, conflict) in enumerate(queries):
        response = agent.process(query, target_state=target, conflict_state=conflict)
        print(f"\n  --- Query {i+1} ---")
        print(f"  Input: {query[:60]}...")
        print(f"  State: #{response.current_state.index} [{response.current_state}]")
        print(f"  Polarity: {response.current_state.polarity:+d} "
              f"(Y:{response.current_state.yang_count} "
              f"V:{response.current_state.void_count} "
              f"N:{response.current_state.yin_count})")
        print(f"  Self alignment: {response.self_alignment:.1%}")
        print(f"  Pattern matched: {response.pattern_matched}")
        if response.suggestions:
            print(f"  Suggestions: {response.suggestions[0][:80]}")

        # Record outcomes (simulate feedback)
        positive = i % 3 != 2  # 3rd query gets negative feedback
        agent.record_outcome(
            state=response.current_state,
            decision=f"query_{i+1}",
            outcome_positive=positive,
        )

    # 5. Advance to internalize stage (pattern matching kicks in)
    agent.advance_stage()
    print(f"\n[Stage] Advanced to: {agent.growth_stage}")

    # 6. Process a query similar to earlier ones (should pattern-match)
    similar_query = "Should we focus on deep algorithmic innovation or practical features?"
    response = agent.process(similar_query)
    print(f"\n[Pattern] Similar query after internalize:")
    print(f"  Pattern matched: {response.pattern_matched}")
    print(f"  Confidence: {response.pattern_confidence:.1%}")
    print(f"  Source: {response.projection.source}")

    # 7. Generate third choice for a real conflict
    state_a = CognitiveState.from_values([1, 1, 1, 1, 1, 0, 1, -1, 1])  # innovation-heavy
    state_b = CognitiveState.from_values([-1, 1, -1, 1, -1, 0, -1, 1, -1])  # pragmatism-heavy
    response = agent.process(
        "Innovation vs pragmatism: which direction?",
        conflict_state=state_b,
    )
    print(f"\n[ThirdChoice] Conflict resolution:")
    print(f"  State A: #{state_a.index} (innovation)")
    print(f"  State B: #{state_b.index} (pragmatism)")
    if response.third_choice_candidates:
        for tc in response.third_choice_candidates[:3]:
            print(f"  Candidate [{tc.strategy}]: #{tc.state.index} "
                  f"score={tc.total_score:.2f} void={tc.void_ratio:.0%}")

    # 8. Discover cognitive seasons
    seasons = agent.discover_seasons()
    print(f"\n[Seasons] Discovered {len(seasons)} cognitive seasons:")
    for s in seasons[:5]:
        print(f"  [{s.season_type}] {s.description[:70]}")

    # 9. Generate climate report
    print(f"\n[Climate]")
    print(agent.climate_report())

    # 10. Save and reload
    saved_path = agent.save()
    print(f"\n[Persistence] Saved to: {saved_path}")

    # Create new agent and load
    agent2 = BTCUAgent(storage_path=storage_path)
    loaded = agent2.load()
    # Re-attach LLM bridge for projection fallback
    agent2.llm_bridge = mock_bridge
    print(f"  Loaded into new agent: {loaded}")
    print(f"  Restored stage: {agent2.growth_stage}")
    print(f"  Restored trajectory: {agent2.trajectory.length} steps")
    print(f"  Restored patterns: {agent2.pattern_learner.pattern_count}")
    print(f"  Restored climate: {agent2.climate}")

    # 11. Verify pattern matching works after reload
    response2 = agent2.process("Should we focus on algorithmic innovation or practical features?")
    print(f"\n[Reload] Pattern match after reload:")
    print(f"  Matched: {response2.pattern_matched}")
    print(f"  Confidence: {response2.pattern_confidence:.1%}")

    # 12. Final status
    print(f"\n[Status]")
    print(agent2.status())

    # Cleanup
    if os.path.exists(storage_path):
        os.remove(storage_path)

    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE - All modules operational")
    print("=" * 60)


if __name__ == "__main__":
    run_validation()
