"""Tests for Trit - the fundamental cognitive unit."""
import pytest
from btcu_harness.core.trit import Trit, TritEnum, YIN, VOID, YANG


class TestTritCreation:
    def test_create_from_int(self):
        assert Trit(-1).value == -1
        assert Trit(0).value == 0
        assert Trit(1).value == 1

    def test_create_from_enum(self):
        assert Trit(TritEnum.YIN) == -1
        assert Trit(TritEnum.VOID) == 0
        assert Trit(TritEnum.YANG) == 1

    def test_create_from_trit(self):
        t = Trit(1)
        assert Trit(t) == 1

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            Trit(2)
        with pytest.raises(ValueError):
            Trit(-2)
        with pytest.raises(ValueError):
            Trit(100)


class TestTritAxiom:
    """The fundamental axiom: -1 + 1 = 0"""

    def test_axiom_yang_plus_yin(self):
        result = YANG + YIN
        assert result == 0
        assert result.is_void()

    def test_axiom_yin_plus_yang(self):
        result = YIN + YANG
        assert result == 0
        assert result.is_void()


class TestTritNegation:
    def test_negate_yang(self):
        assert (-YANG) == -1
        assert (-YANG).is_yin()

    def test_negate_yin(self):
        assert (-YIN) == 1
        assert (-YIN).is_yang()

    def test_negate_void_invariant(self):
        assert (-VOID) == 0
        assert (-VOID).is_void()

    def test_double_negation(self):
        for val in (-1, 0, 1):
            t = Trit(val)
            assert (-(-t)) == t


class TestTritEncoding:
    def test_encode(self):
        assert YIN.encode() == 0
        assert VOID.encode() == 1
        assert YANG.encode() == 2

    def test_decode(self):
        assert Trit.decode(0) == -1
        assert Trit.decode(1) == 0
        assert Trit.decode(2) == 1

    def test_encode_decode_roundtrip(self):
        for val in (-1, 0, 1):
            t = Trit(val)
            assert Trit.decode(t.encode()) == t

    def test_invalid_decode(self):
        with pytest.raises(ValueError):
            Trit.decode(3)
        with pytest.raises(ValueError):
            Trit.decode(-1)


class TestTritProperties:
    def test_names(self):
        assert YIN.name == "YIN"
        assert VOID.name == "VOID"
        assert YANG.name == "YANG"

    def test_is_methods(self):
        assert YIN.is_yin() and not YIN.is_void() and not YIN.is_yang()
        assert not VOID.is_yin() and VOID.is_void() and not VOID.is_yang()
        assert not YANG.is_yin() and not YANG.is_void() and YANG.is_yang()

    def test_is_polarized(self):
        assert YIN.is_polarized()
        assert YANG.is_polarized()
        assert not VOID.is_polarized()

    def test_bool(self):
        assert bool(YANG)
        assert bool(YIN)
        assert not bool(VOID)


class TestTritMultiplication:
    def test_void_annihilates(self):
        assert (VOID * YANG) == 0
        assert (VOID * YIN) == 0
        assert (YANG * VOID) == 0

    def test_yin_yin(self):
        assert (YIN * YIN) == 1

    def test_yang_yang(self):
        assert (YANG * YANG) == 1

    def test_yin_yang(self):
        assert (YIN * YANG) == -1
