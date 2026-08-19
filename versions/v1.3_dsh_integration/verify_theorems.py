"""
BTCU Mathematical Properties Verification Suite
Validates key theorems from Paper I-IV with actual computation.
"""

import math
from collections import Counter
from btcu_harness.core.state import CognitiveState, SPACE_SIZE, NUM_DIMENSIONS
from btcu_harness.core.trit import Trit


def verify_bijective_encoding():
    """Theorem 2.1 (Paper III): Encoding is bijective."""
    print("=" * 60)
    print("Theorem 2.1: Bijective Encoding Verification")
    print("=" * 60)
    
    # Test encoding/decoding round-trip for all states
    errors = 0
    for i in range(SPACE_SIZE):
        state = CognitiveState.from_index(i)
        encoded = state.index
        if encoded != i:
            errors += 1
            if errors <= 3:  # Print first 3 errors
                print(f"  ERROR: Index {i} -> State {state} -> Index {encoded}")
    
    if errors == 0:
        print(f"  PASS: All {SPACE_SIZE} states round-trip correctly")
    else:
        print(f"  FAIL: {errors} errors out of {SPACE_SIZE}")
    
    return errors == 0


def verify_symmetry_property():
    """Theorem 2.2 (Paper III): Index(-s) = 19682 - Index(s)."""
    print("=" * 60)
    print("Theorem 2.2: Symmetry Property Verification")
    print("=" * 60)
    
    errors = 0
    for i in range(SPACE_SIZE):
        state = CognitiveState.from_index(i)
        opposite = state.opposite()
        expected_opposite_index = SPACE_SIZE - 1 - i
        actual_opposite_index = opposite.index
        
        if actual_opposite_index != expected_opposite_index:
            errors += 1
            if errors <= 3:
                print(f"  ERROR: State {i}, opposite should be {expected_opposite_index}, got {actual_opposite_index}")
    
    if errors == 0:
        print(f"  PASS: Symmetry holds for all {SPACE_SIZE} states")
        # Show example
        example = CognitiveState.from_values([1, 0, -1, 0, 0, 0, 0, 0, 0])
        opp = example.opposite()
        print(f"  Example: Index({example.values}) = {example.index}")
        print(f"           Index({opp.values}) = {opp.index}")
        print(f"           Sum = {example.index + opp.index} (should be {SPACE_SIZE - 1})")
    else:
        print(f"  FAIL: {errors} errors")
    
    return errors == 0


def verify_void_center():
    """Corollary 2.2.1: Void state index = 9841."""
    print("=" * 60)
    print("Corollary 2.2.1: Void State Center Verification")
    print("=" * 60)
    
    void_state = CognitiveState.all_void()
    expected_index = (SPACE_SIZE - 1) // 2
    actual_index = void_state.index
    
    print(f"  Expected index: {expected_index}")
    print(f"  Actual index:   {actual_index}")
    print(f"  {'PASS' if actual_index == expected_index else 'FAIL'}")
    
    return actual_index == expected_index


def verify_energy_shell_distribution():
    """Theorem 3.1 (Paper II): N(k) = C(9,k) * 2^k."""
    print("=" * 60)
    print("Theorem 3.1: Energy Shell Distribution Verification")
    print("=" * 60)
    
    # Count states by energy level
    energy_counts = Counter()
    for i in range(SPACE_SIZE):
        state = CognitiveState.from_index(i)
        # Energy = number of non-VOID dimensions
        energy = NUM_DIMENSIONS - state.void_count
        energy_counts[energy] += 1
    
    # Verify against formula
    total = 0
    all_pass = True
    for k in range(NUM_DIMENSIONS + 1):
        expected = math.comb(NUM_DIMENSIONS, k) * (2 ** k)
        actual = energy_counts[k]
        total += actual
        match = "PASS" if actual == expected else "FAIL"
        if match == "FAIL":
            all_pass = False
        print(f"  Shell {k}: expected={expected:5d}, actual={actual:5d} [{match}]")
    
    print(f"  Total states: {total} (expected {SPACE_SIZE})")
    print(f"  Overall: {'PASS' if all_pass and total == SPACE_SIZE else 'FAIL'}")
    
    return all_pass and total == SPACE_SIZE


def verify_shell_transitions():
    """Theorem 3.2 (Paper II): Single-dimension change changes energy by ±1."""
    print("=" * 60)
    print("Theorem 3.2: Shell Transition Verification")
    print("=" * 60)
    
    errors = 0
    checked = 0
    for i in range(min(1000, SPACE_SIZE)):  # Sample 1000 states
        state = CognitiveState.from_index(i)
        energy = NUM_DIMENSIONS - state.void_count
        
        for neighbor in state.neighbors():
            neighbor_energy = NUM_DIMENSIONS - neighbor.void_count
            delta = neighbor_energy - energy
            checked += 1
            
            if abs(delta) != 1:
                errors += 1
                if errors <= 3:
                    print(f"  ERROR: State {i} (E={energy}) -> Neighbor (E={neighbor_energy}), delta={delta}")
    
    if errors == 0:
        print(f"  PASS: All {checked} transitions change energy by exactly ±1")
    else:
        print(f"  FAIL: {errors} errors out of {checked} transitions")
    
    return errors == 0


def verify_metric_axioms():
    """Verify Hamming and Euclidean distances satisfy metric axioms."""
    print("=" * 60)
    print("Metric Axioms Verification (Sample)")
    print("=" * 60)
    
    # Sample states for testing
    samples = [
        CognitiveState.all_void(),
        CognitiveState.all_yang(),
        CognitiveState.all_yin(),
        CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1]),
        CognitiveState.from_values([-1, 1, 0, 0, 1, -1, 1, 0, -1]),
    ]
    
    def hamming(s1, s2):
        """Number of differing dimensions."""
        return sum(1 for a, b in zip(s1.values, s2.values) if a != b)
    
    def euclidean(s1, s2):
        """Euclidean distance."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(s1.values, s2.values)))
    
    # Check metric axioms for sample pairs
    print("  Checking M1 (Non-negativity), M2 (Identity), M3 (Symmetry), M4 (Triangle Inequality)")
    
    all_pass = True
    for i, s1 in enumerate(samples):
        for j, s2 in enumerate(samples):
            for k, s3 in enumerate(samples):
                d_h_12 = hamming(s1, s2)
                d_h_23 = hamming(s2, s3)
                d_h_13 = hamming(s1, s3)
                
                d_e_12 = euclidean(s1, s2)
                d_e_23 = euclidean(s2, s3)
                d_e_13 = euclidean(s1, s3)
                
                # M1: Non-negativity
                if d_h_12 < 0 or d_e_12 < 0:
                    all_pass = False
                
                # M2: Identity
                if i == j:
                    if d_h_12 != 0 or d_e_12 != 0:
                        all_pass = False
                
                # M3: Symmetry
                if hamming(s2, s1) != d_h_12 or euclidean(s2, s1) != d_e_12:
                    all_pass = False
                
                # M4: Triangle inequality
                if d_h_13 > d_h_12 + d_h_23 + 1e-10:
                    all_pass = False
                if d_e_13 > d_e_12 + d_e_23 + 1e-10:
                    all_pass = False
    
    print(f"  {'PASS' if all_pass else 'FAIL'}: Metric axioms hold for all sample pairs")
    return all_pass


def verify_metric_hierarchy():
    """Theorem 3.5: sqrt(d_H) <= d_E <= 2*sqrt(d_H)."""
    print("=" * 60)
    print("Theorem 3.5: Metric Hierarchy Verification")
    print("=" * 60)
    
    def hamming(s1, s2):
        return sum(1 for a, b in zip(s1.values, s2.values) if a != b)
    
    def euclidean(s1, s2):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(s1.values, s2.values)))
    
    errors = 0
    checked = 0
    for i in range(0, SPACE_SIZE, 100):  # Sample every 100th state
        for j in range(i + 1, min(i + 100, SPACE_SIZE), 10):  # Sample neighbors
            s1 = CognitiveState.from_index(i)
            s2 = CognitiveState.from_index(j)
            
            d_h = hamming(s1, s2)
            d_e = euclidean(s1, s2)
            
            if d_h > 0:  # Skip identical states
                checked += 1
                lower = math.sqrt(d_h)
                upper = 2 * math.sqrt(d_h)
                
                if not (lower - 1e-10 <= d_e <= upper + 1e-10):
                    errors += 1
                    if errors <= 3:
                        print(f"  ERROR: d_H={d_h}, d_E={d_e:.3f}, bounds=[{lower:.3f}, {upper:.3f}]")
    
    if errors == 0:
        print(f"  PASS: Hierarchy holds for {checked} sampled pairs")
    else:
        print(f"  FAIL: {errors} violations out of {checked} pairs")
    
    return errors == 0


def run_all_verifications():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("BTCU Mathematical Properties Verification Suite")
    print("=" * 60 + "\n")
    
    results = []
    
    results.append(("Bijective Encoding", verify_bijective_encoding()))
    results.append(("Symmetry Property", verify_symmetry_property()))
    results.append(("Void Center", verify_void_center()))
    results.append(("Shell Distribution", verify_energy_shell_distribution()))
    results.append(("Shell Transitions", verify_shell_transitions()))
    results.append(("Metric Axioms", verify_metric_axioms()))
    results.append(("Metric Hierarchy", verify_metric_hierarchy()))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_pass = False
    
    print(f"\nOverall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    
    return all_pass


if __name__ == "__main__":
    run_all_verifications()
