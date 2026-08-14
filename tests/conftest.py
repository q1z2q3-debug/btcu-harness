"""Test fixtures for BTCU Harness."""
import pytest


@pytest.fixture
def default_dims():
    return ["past", "present", "future", "inner", "middle", "outer", "cause", "condition", "effect"]
