"""
Minimal smoke test for BTCU Harness core.

Run with: python examples/smoke_test.py

This verifies the core without any external dependencies:
    - trit validation
    - balanced ternary operations
    - 19683 encoding / decoding
    - space landmarks (yin / empty / yang)
"""

from btcu_harness.core.btcu import T, Z, O, is_valid_trit
from btcu_harness.core.ternary import neg, add, similarity, hamming_distance
from btcu_harness.core.encoding import encode, decode, CENTER_INDEX, MAX_INDEX
from btcu_harness.core.space import Space19683


def check(name: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise SystemExit(1)


def main() -> None:
    print("BTCU Harness - Core Smoke Test\n")

    # 1. Trit primitives
    check("T is -1", T == -1)
    check("Z is 0", Z == 0)
    check("O is +1", O == 1)
    check("is_valid_trit(-1)", is_valid_trit(-1))
    check("is_valid_trit(0)", is_valid_trit(0))
    check("is_valid_trit(1)", is_valid_trit(1))
    check("is_valid_trit(2) is False", not is_valid_trit(2))

    # 2. Balanced ternary operations
    check("neg([-1,0,1]) == [1,0,-1]", neg([-1, 0, 1]) == [1, 0, -1])
    check("add([1,0], [1,0]) == [T,1]", add([1, 0], [1, 0]) == [-1, 1])
    check(
        "similarity([1,0,-1], [1,0,-1]) == 2",
        similarity([1, 0, -1], [1, 0, -1]) == 2,
    )
    check(
        "hamming_distance([1,0,-1], [1,0,1]) == 1",
        hamming_distance([1, 0, -1], [1, 0, 1]) == 1,
    )

    # 3. 19683 encoding
    all_yin = [T] * 9
    all_empty = [Z] * 9
    all_yang = [O] * 9

    check("encode(all_yin) == 0", encode(all_yin) == 0)
    check("encode(all_empty) == 9841", encode(all_empty) == CENTER_INDEX)
    check("encode(all_yang) == 19682", encode(all_yang) == MAX_INDEX)
    check("decode(0) == all_yin", decode(0) == all_yin)
    check("decode(9841) == all_empty", decode(9841) == all_empty)
    check("decode(19682) == all_yang", decode(19682) == all_yang)

    # 4. Round-trip
    for idx in [0, 1, 10, 100, 9841, 19682]:
        check(f"round-trip {idx}", encode(decode(idx)) == idx)

    # 5. Space landmarks
    space = Space19683()
    check("space.center_index == 9841", space.center_index == 9841)
    check("space.mirror(0) == 19682", space.mirror(0) == 19682)
    check("space.mirror(19682) == 0", space.mirror(19682) == 0)
    check("space.polarity(0) == -9", space.polarity(0) == -9)
    check("space.polarity(19682) == 9", space.polarity(19682) == 9)
    check("space.polarity(9841) == 0", space.polarity(9841) == 0)

    # 6. Neighbors
    neighbors = space.neighbors(9841)
    check("center has 18 neighbors", len(neighbors) == 18)

    print("\nAll checks passed. Core is operational.")


if __name__ == "__main__":
    main()
