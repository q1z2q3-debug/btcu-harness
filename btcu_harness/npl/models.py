"""
BTCU Harness - NPL Self Models

The eight Neuro-Linguistic Programming logical levels, each mapped
to a balanced ternary vector in the 19683 cognitive space.

Logical level ordering (top-down):
    0. Mission       - why we exist
    1. Vision        - what future we aim for
    2. Values        - what matters most
    3. Identity      - who we are
    4. Beliefs       - what we assume to be true
    5. Capabilities  - what we can do
    6. Behaviors     - what we actually do
    7. Environment   - where and when we operate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from btcu_harness.core.btcu import T, Z, O
from btcu_harness.core.encoding import DEFAULT_DIM, encode, decode


class NplLevel(IntEnum):
    """NLP logical levels, ordered from most abstract to most concrete."""

    MISSION = 0
    VISION = 1
    VALUES = 2
    IDENTITY = 3
    BELIEFS = 4
    CAPABILITIES = 5
    BEHAVIORS = 6
    ENVIRONMENT = 7


@dataclass
class NplComponent:
    """
    Base class for every self component.

    Each component owns a nine-trit state vector. This vector is the
    component's position in the 19683 cognitive space.
    """

    name: str
    content: str = ""
    vector: list[int] = field(default_factory=lambda: [Z] * DEFAULT_DIM)
    meta: dict = field(default_factory=dict)

    @property
    def state_index(self) -> int:
        """Return the 19683-space index of this component."""
        return encode(self.vector)

    @property
    def polarity(self) -> int:
        """Return net polarity of this component."""
        return sum(self.vector)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "content": self.content,
            "vector": list(self.vector),
            "state_index": self.state_index,
            "meta": self.meta,
        }


@dataclass
class Mission(NplComponent):
    """Mission: the deepest reason this agent exists."""


@dataclass
class Vision(NplComponent):
    """Vision: the target state we aim to realize."""

    target_state: Optional[int] = None


@dataclass
class Values(NplComponent):
    """Values: what matters most, expressed as a weighted trit vector."""

    priority: int = 0


@dataclass
class Identity(NplComponent):
    """Identity: the stable core position in the cognitive space."""

    core_state: int = 9841  # all-EMPTY center


@dataclass
class Beliefs(NplComponent):
    """Beliefs: assumptions that shape interpretation."""

    strength: float = 0.5


@dataclass
class Capabilities(NplComponent):
    """Capabilities: what the agent can actually do."""

    workflows: list[str] = field(default_factory=list)


@dataclass
class Behaviors(NplComponent):
    """Behaviors: concrete actions and their trit posture."""

    action: int = Z  # T=retreat, Z=hold, O=advance


@dataclass
class Environment(NplComponent):
    """Environment: where and when the agent operates."""

    location: str = ""
    timestamp: str = ""
