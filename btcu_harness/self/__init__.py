"""
BTCU Harness - NLP Self Layer

The NLP self layer gives an Agent a structured sense of identity.

Layers (top-down, from most fundamental to most concrete):
    mission     - why the Agent exists
    vision      - what the world or self should become
    values      - what is important
    identity    - who the Agent is
    beliefs     - how the Agent judges situations
    capability  - what the Agent can do
    behavior    - what the Agent actually does
    environment - where and when the Agent operates

Each layer can be projected into the 19683-state space, so the self
layer and the cognitive space share one coordinate system.
"""

from btcu_harness.self.nlp_self import NLPSelf, SelfLayer

__all__ = ["NLPSelf", "SelfLayer"]
