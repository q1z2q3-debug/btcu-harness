"""
BTCU Harness - End-to-End Demo

Demonstrates the full MVP flow:
    input -> project -> encode -> interpret -> memory -> decision

Run:
    python examples/end_to_end_demo.py
    or
    python -m examples.end_to_end_demo
"""

import sys
from pathlib import Path

# Bootstrap: make the project root importable when running this file directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from btcu_harness.core import encode, Space19683
from btcu_harness.mapping import CognitiveProjector
from btcu_harness.mapping.dimensions import DEFAULT_DIMENSION_SET
from btcu_harness.memory import MemoryRepository, MemoryTrace
from btcu_harness.decision import generate_path, generate_third_choice


def main() -> None:
    print("=" * 60)
    print("BTCU Harness - End-to-End MVP Demo")
    print("=" * 60)

    # 1. Project raw features into a nine-trit state vector.
    projector = CognitiveProjector(DEFAULT_DIMENSION_SET)
    features = {
        "time": 1,          # future
        "space": 1,         # external
        "causality": 0,     # condition / yuan
        "value": 0,         # suspended
        "relation": -1,     # opposed
        "action": 0,        # hold
        "subject": 1,       # self
        "intent": -1,       # defend
        "cognition": 0,     # exploring
    }
    vector = projector.project(features)
    state_id = encode(vector)

    print("\n[1] Projected State")
    print("    Vector:", vector)
    print("    Index :", state_id)
    print("    Semantics:", projector.interpret(vector))

    # 2. Inspect space properties.
    space = Space19683()
    print("\n[2] 19683 Space")
    print("    Size  :", space.size)
    print("    Center:", space.center)
    print("    Mirror:", space.mirror(state_id))
    print("    Polarity:", space.polarity(state_id))

    # 3. Write a memory trace.
    repository = MemoryRepository(space)
    trace = MemoryTrace.from_vectors(
        trace_id="demo-001",
        agent_id="agent-001",
        vectors=[vector],
        value=0,
    )
    repository.write(trace)

    similar = repository.find_similar(state_id, limit=1)
    print("\n[3] Memory")
    print("    Trace ID   :", trace.trace_id)
    print("    Last State :", trace.last_state())
    print("    Similar    :", similar[0].trace_id if similar else "none")

    # 4. Generate a decision path to a target state.
    target_vector = [0, 0, 0, 1, 0, 1, 0, 0, 1]
    target_id = encode(target_vector)
    path = generate_path(state_id, target_id)

    print("\n[4] Decision Path")
    print("    From :", state_id)
    print("    To   :", target_id)
    print("    Steps:", len(path) - 1)
    print("    Path :", path[:5], "..." if len(path) > 5 else "")

    # 5. Generate third-choice candidates.
    candidates = generate_third_choice(state_id)
    print("\n[5] Third Choice Candidates")
    print("    Count:", len(candidates))
    print("    First 5:", candidates[:5])

    print("\n" + "=" * 60)
    print("Demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
