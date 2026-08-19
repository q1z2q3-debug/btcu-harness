"""
BTCU Harness - Core Tests
"""

import pytest

from btcu_harness.core import (
    BTCU,
    T,
    Z,
    O,
    neg,
    add,
    sub,
    mul,
    similarity,
    hamming_distance,
    encode,
    decode,
    Space19683,
)


class TestBTCU:
    def test_values(self):
        assert T == -1
        assert Z == 0
        assert O == 1
        assert BTCU.YIN == -1
        assert BTCU.EMPTY == 0
        assert BTCU.YANG == 1


class TestTernary:
    def test_neg(self):
        assert neg([-1, 0, 1]) == [1, 0, -1]

    def test_add_opposite_gives_zero(self):
        assert add([1], [-1]) == [0]

    def test_add_carry(self):
        assert add([1, 1], [1]) == [-1, -1, 1]

    def test_sub(self):
        assert sub([1], [1]) == [0]

    def test_mul(self):
        assert mul([1, -1, 0], [-1, -1, 1]) == [-1, 1, 0]

    def test_similarity(self):
        assert similarity([1, -1, 0], [1, -1, 0]) == 2
        assert similarity([1, -1, 0], [-1, 1, 0]) == -2

    def test_hamming_distance(self):
        assert hamming_distance([1, -1, 0], [1, -1, 0]) == 0
        assert hamming_distance([1, -1, 0], [-1, 1, 0]) == 2


class TestEncoding:
    def test_encode_decode_roundtrip(self):
        vector = [1, 0, -1, 1, -1, 0, 1, 0, -1]
        idx = encode(vector)
        assert decode(idx) == vector

    def test_special_states(self):
        all_yin = [-1] * 9
        all_empty = [0] * 9
        all_yang = [1] * 9
        assert encode(all_yin) == 0
        assert encode(all_empty) == 9841
        assert encode(all_yang) == 19682

    def test_decode_out_of_range(self):
        with pytest.raises(ValueError):
            decode(19683)


class TestSpace19683:
    def test_size(self):
        space = Space19683()
        assert space.size == 19683
        assert space.center == 9841

    def test_mirror(self):
        space = Space19683()
        assert space.mirror(0) == 19682
        assert space.mirror(9841) == 9841
        assert space.mirror(19682) == 0

    def test_polarity(self):
        space = Space19683()
        assert space.polarity(0) == -9
        assert space.polarity(9841) == 0
        assert space.polarity(19682) == 9

    def test_neighbors(self):
        space = Space19683()
        neighbors = space.neighbors(9841)
        assert len(neighbors) == 18

    def test_distance(self):
        space = Space19683()
        assert space.distance(9841, 9841) == 0
