"""
BTCU Harness - Decision & Action Layer

Decision is not choosing an option; it is generating a state
transition path from the current trigram to a target trigram.

Action has three postures:
    T (-1) = retreat
    Z ( 0) = hold
    O (+1) = advance

The EMPTY (0) posture is not inaction; it is the third action that
keeps the system open to transformation.
"""

from btcu_harness.decision.action import Action, action_to_trit, trit_to_action
from btcu_harness.decision.path import generate_path, is_legal_step
from btcu_harness.decision.third_choice import generate_third_choice

__all__ = [
    "Action",
    "action_to_trit",
    "trit_to_action",
    "generate_path",
    "is_legal_step",
    "generate_third_choice",
]
