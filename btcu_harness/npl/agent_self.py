"""
BTCU Harness - AgentSelf

AgentSelf organizes the eight NPL levels into a coherent self.

The self is not just static metadata; every level can be projected
into the 19683 cognitive space, compared, and evolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from btcu_harness.core.btcu import T, Z, O
from btcu_harness.core.encoding import DEFAULT_DIM, CENTER_INDEX
from btcu_harness.npl.models import (
    Beliefs,
    Behaviors,
    Capabilities,
    Environment,
    Identity,
    Mission,
    NplLevel,
    Values,
    Vision,
)


@dataclass
class AgentSelf:
    """
    The eight-level self-structure of a cognitive agent.

    Upper levels (mission, vision, values, identity) give direction.
    Lower levels (beliefs, capabilities, behaviors, environment)
    give concrete expression.
    """

    mission: Mission = field(
        default_factory=lambda: Mission(name="mission", content="")
    )
    vision: Vision = field(
        default_factory=lambda: Vision(name="vision", content="")
    )
    values: Values = field(
        default_factory=lambda: Values(name="values", content="")
    )
    identity: Identity = field(
        default_factory=lambda: Identity(name="identity", content="")
    )
    beliefs: Beliefs = field(
        default_factory=lambda: Beliefs(name="beliefs", content="")
    )
    capabilities: Capabilities = field(
        default_factory=lambda: Capabilities(name="capabilities", content="")
    )
    behaviors: Behaviors = field(
        default_factory=lambda: Behaviors(name="behaviors", content="")
    )
    environment: Environment = field(
        default_factory=lambda: Environment(name="environment", content="")
    )

    # ------------------------------------------------------------------
    # Component access
    # ------------------------------------------------------------------

    def get_component(self, level: NplLevel):
        """Return the component for a logical level."""
        mapping = {
            NplLevel.MISSION: self.mission,
            NplLevel.VISION: self.vision,
            NplLevel.VALUES: self.values,
            NplLevel.IDENTITY: self.identity,
            NplLevel.BELIEFS: self.beliefs,
            NplLevel.CAPABILITIES: self.capabilities,
            NplLevel.BEHAVIORS: self.behaviors,
            NplLevel.ENVIRONMENT: self.environment,
        }
        return mapping[level]

    def all_components(self):
        """Return all components in logical order."""
        return [
            self.mission,
            self.vision,
            self.values,
            self.identity,
            self.beliefs,
            self.capabilities,
            self.behaviors,
            self.environment,
        ]

    # ------------------------------------------------------------------
    # Self projection into the 19683 space
    # ------------------------------------------------------------------

    def self_vector(self) -> list[int]:
        """
        Compute the aggregate self vector.

        The upper four levels (mission, vision, values, identity)
        define the core; lower levels refine it. Here we use the
        identity vector as the default anchor and blend values.

        This is intentionally simple for the MVP; future versions
        may support weighted blending per logical level.
        """
        # Simple blend: average by trit using majority-ish sign logic.
        result = [Z] * DEFAULT_DIM
        components = [self.mission, self.vision, self.values, self.identity]
        for i in range(DEFAULT_DIM):
            total = sum(c.vector[i] for c in components)
            if total > 0:
                result[i] = O
            elif total < 0:
                result[i] = T
            else:
                result[i] = Z
        return result

    def self_index(self) -> int:
        """Return the 19683-space index of the aggregated self."""
        from btcu_harness.core.encoding import encode

        return encode(self.self_vector())

    # ------------------------------------------------------------------
    # Self summary
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the whole self to a dictionary."""
        return {
            "mission": self.mission.to_dict(),
            "vision": self.vision.to_dict(),
            "values": self.values.to_dict(),
            "identity": self.identity.to_dict(),
            "beliefs": self.beliefs.to_dict(),
            "capabilities": self.capabilities.to_dict(),
            "behaviors": self.behaviors.to_dict(),
            "environment": self.environment.to_dict(),
            "self_index": self.self_index(),
        }

    def summary(self) -> str:
        """Return a human-readable summary of the self."""
        lines = [
            "AgentSelf Summary",
            "-----------------",
            f"Mission: {self.mission.content or '(unset)'}",
            f"Vision:  {self.vision.content or '(unset)'}",
            f"Values:  {self.values.content or '(unset)'}",
            f"Identity:{self.identity.content or '(unset)'}",
            f"Beliefs: {self.beliefs.content or '(unset)'}",
            f"Capabilities: {', '.join(self.capabilities.workflows) or '(none)'}",
            f"Behavior posture: {self.behaviors.action} (T=retreat, Z=hold, O=advance)",
            f"Environment: {self.environment.content or '(unset)'}",
            f"Self state index: {self.self_index()}",
        ]
        return "\n".join(lines)
