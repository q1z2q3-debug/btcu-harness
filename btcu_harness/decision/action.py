"""
BTCU Harness - Action

Three action postures mapped from balanced ternary trits.
"""

from __future__ import annotations

from enum import IntEnum

from btcu_harness.core.btcu import T, Z, O, is_valid_trit


class Action(IntEnum):
    """Three action postures."""

    RETREAT = -1
    HOLD = 0
    ADVANCE = 1


def action_to_trit(action: Action) -> int:
    """Convert an Action to its trit value."""
    return int(action)


def trit_to_action(trit: int) -> Action:
    """Convert a trit to its Action."""
    if not is_valid_trit(trit):
        raise ValueError(f"Invalid action trit: {trit}")
    return Action(trit)


def action_name(action: Action) -> str:
    """Return the human-readable action name."""
    return {
        Action.RETREAT: "retreat",
        Action.HOLD: "hold",
        Action.ADVANCE: "advance",
    }[action]
