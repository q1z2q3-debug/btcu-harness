"""
BTCU Harness - NLP Self Layer

The self-structure of a cognitive agent, organized as eight logical
levels (inspired by NLP logical levels):

    Mission       - ultimate purpose
    Vision        - desired future state
    Values        - what is important
    Identity      - who the agent is
    Beliefs       - what the agent believes
    Capabilities  - what the agent can do
    Behavior      - what the agent actually does
    Environment   - where and when the agent operates

Each level can be mapped to a state or state preference in the
19683 cognitive space.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class NLPSelf:
    """The eight-level self-structure of a cognitive agent.

    Attributes:
        agent_id: Unique agent identifier.
        mission: Ultimate purpose statement.
        vision: Desired future state or state index.
        values: Mapping of value name to importance trit (-1/0/+1).
        identity: Identity statement.
        beliefs: List of belief statements.
        capabilities: List of capability IDs the agent can invoke.
        behaviors: List of typical behavior descriptors.
        environment: Environment descriptor string.
        updated_at: ISO timestamp of last update.
    """

    agent_id: str
    mission: str
    vision: str
    values: dict[str, int] = field(default_factory=dict)
    identity: str = "balanced ternary cognitive agent"
    beliefs: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    behaviors: list[str] = field(default_factory=list)
    environment: str = ""
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        for key, value in self.values.items():
            if value not in (-1, 0, 1):
                raise ValueError(
                    f"Value {key} must be a trit (-1, 0, 1). Got {value}."
                )

    def set_value(self, name: str, importance: int) -> None:
        """Set or update a value's importance trit.

        Args:
            name: Value name.
            importance: Trit importance, -1/0/+1.
        """

        if importance not in (-1, 0, 1):
            raise ValueError(f"Importance must be -1, 0, or 1. Got {importance}.")
        self.values[name] = importance
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_belief(self, belief: str) -> None:
        """Add a belief statement.

        Args:
            belief: Belief string.
        """

        if belief not in self.beliefs:
            self.beliefs.append(belief)
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_capability(self, capability_id: str) -> None:
        """Add a capability reference.

        Args:
            capability_id: Capability index ID, e.g. "CAP-001".
        """

        if capability_id not in self.capabilities:
            self.capabilities.append(capability_id)
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_behavior(self, behavior: str) -> None:
        """Add a typical behavior descriptor.

        Args:
            behavior: Behavior string.
        """

        if behavior not in self.behaviors:
            self.behaviors.append(behavior)
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Serialize the self-structure to a dictionary."""

        return asdict(self)
