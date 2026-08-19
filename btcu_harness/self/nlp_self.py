"""
NLP Self Layer - structured identity for BTCU Harness agents.

Implements the eight-layer NLP self model, from most fundamental
to most concrete:

    mission -> vision -> values -> identity -> beliefs
    -> capability -> behavior -> environment

Each layer can project into the 19683-state space, enabling the
self to be located, tracked, and interpreted alongside other
cognitive states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from btcu_harness.core.space import Space19683


class SelfLayer(str, Enum):
    """The eight NLP self layers."""

    MISSION = "mission"
    VISION = "vision"
    VALUES = "values"
    IDENTITY = "identity"
    BELIEFS = "beliefs"
    CAPABILITY = "capability"
    BEHAVIOR = "behavior"
    ENVIRONMENT = "environment"


@dataclass
class LayerEntry:
    """A single entry within a self layer."""

    content: str
    state_id: Optional[int] = None
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class NLPSelf:
    """
    A structured identity model for an Agent.

    The self is organized by eight layers. Entries may carry a state_id,
    connecting identity elements to the cognitive space.
    """

    def __init__(
        self,
        name: str = "BTCU Agent",
        space: Optional[Space19683] = None,
    ) -> None:
        self.name = name
        self.space = space or Space19683()
        self.layers: dict[SelfLayer, list[LayerEntry]] = {
            layer: [] for layer in SelfLayer
        }

    # ------------------------------------------------------------------
    # Layer access
    # ------------------------------------------------------------------

    def add(
        self,
        layer: SelfLayer | str,
        content: str,
        *,
        state_id: Optional[int] = None,
        weight: float = 1.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> LayerEntry:
        """Add an entry to a self layer."""
        layer = SelfLayer(layer)
        entry = LayerEntry(
            content=content,
            state_id=state_id,
            weight=weight,
            metadata=metadata or {},
        )
        self.layers[layer].append(entry)
        return entry

    def get(self, layer: SelfLayer | str) -> list[LayerEntry]:
        """Return all entries for a layer."""
        return self.layers[SelfLayer(layer)]

    def set_mission(self, content: str, *, weight: float = 1.0) -> LayerEntry:
        return self.add(SelfLayer.MISSION, content, weight=weight)

    def set_vision(self, content: str, *, target_state_id: Optional[int] = None) -> LayerEntry:
        return self.add(
            SelfLayer.VISION,
            content,
            state_id=target_state_id,
        )

    def set_identity(self, content: str, *, core_state_id: Optional[int] = None) -> LayerEntry:
        return self.add(
            SelfLayer.IDENTITY,
            content,
            state_id=core_state_id,
        )

    def add_value(self, content: str, *, priority: int = 0) -> LayerEntry:
        return self.add(
            SelfLayer.VALUES,
            content,
            weight=max(0.1, 1.0 - 0.1 * priority),
            metadata={"priority": priority},
        )

    def add_belief(self, content: str, *, strength: float = 0.5) -> LayerEntry:
        return self.add(
            SelfLayer.BELIEFS,
            content,
            weight=min(max(strength, 0.0), 1.0),
        )

    def add_capability(self, content: str, *, state_id: Optional[int] = None) -> LayerEntry:
        return self.add(SelfLayer.CAPABILITY, content, state_id=state_id)

    def add_behavior(self, content: str, *, state_id: Optional[int] = None) -> LayerEntry:
        return self.add(SelfLayer.BEHAVIOR, content, state_id=state_id)

    def add_environment(self, content: str, *, state_id: Optional[int] = None) -> LayerEntry:
        return self.add(SelfLayer.ENVIRONMENT, content, state_id=state_id)

    # ------------------------------------------------------------------
    # Projection into cognitive space
    # ------------------------------------------------------------------

    def dominant_state_id(self) -> Optional[int]:
        """
        Return the weighted-dominant state id across all layered entries
        that carry a state_id.

        This gives a single cognitive-space anchor for the current self.
        """
        weighted: dict[int, float] = {}
        for layer in SelfLayer:
            for entry in self.layers[layer]:
                if entry.state_id is None:
                    continue
                weighted[entry.state_id] = (
                    weighted.get(entry.state_id, 0.0) + entry.weight
                )
        if not weighted:
            return None
        return max(weighted, key=lambda k: weighted[k])

    def identity_vector(self) -> Optional[list[int]]:
        """Return the dominant state vector, or None."""
        state_id = self.dominant_state_id()
        if state_id is None:
            return None
        return self.space.decode(state_id)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a compact summary of the self structure."""
        return {
            "name": self.name,
            "dominant_state_id": self.dominant_state_id(),
            "layer_counts": {
                layer.value: len(entries)
                for layer, entries in self.layers.items()
            },
        }
