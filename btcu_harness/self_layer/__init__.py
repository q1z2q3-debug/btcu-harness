"""
NLP Self Layer: The agent's identity, values, and mission as cognitive attractors.

This layer implements the Dilts logical levels model adapted for BTCU:
    Mission -> Vision -> Values -> Identity -> Beliefs -> Capabilities -> Behaviors -> Environment

Each level is expressed as a cognitive state in the 19683 space. Together,
they form a "personality attractor" - the agent's daily cognitive states
orbit around this center of gravity.

The self layer is NOT a static config. It evolves:
- Initial values can be set by the creator
- Successful cognitive patterns gradually shift the attractor
- Failed patterns push the attractor away
- Over time, the agent develops its own stable personality

This is how BTCU agents gain personality - not by design, but by
accumulation of experience around a slowly moving center.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.state import CognitiveState, NUM_DIMENSIONS
from ..core.trit import Trit


@dataclass
class SelfLevel:
    """
    One level of the NLP self hierarchy.

    Each level has:
    - A name (mission, vision, values, etc.)
    - A description (natural language)
    - A cognitive state (its projection onto 19683 space)
    - A weight (how much it influences the attractor)
    - A stability (how resistant it is to change)
    """

    name: str
    description: str
    state: CognitiveState
    weight: float = 1.0  # influence on attractor
    stability: float = 0.9  # resistance to change [0, 1]
    last_updated: Optional[str] = None

    def shift(self, new_state: CognitiveState, force: float = 0.1) -> None:
        """
        Gradually shift this level's state toward a new state.

        High stability = slow change. Low stability = fast change.
        The shift is proportional to (1 - stability) * force.

        Since CognitiveState is discrete (trits), we shift one dimension
        at a time toward the target, choosing the dimension with highest force.
        """
        # Find dimensions that differ
        diffs = []
        for i in range(len(self.state)):
            if self.state[i] != new_state[i]:
                diff_val = abs(self.state[i].value - new_state[i].value)
                diffs.append((i, diff_val))

        if not diffs:
            return

        # Shift the most different dimension by one step
        diffs.sort(key=lambda x: x[1], reverse=True)
        dim_to_shift = diffs[0][0]

        current_val = self.state[dim_to_shift].value
        target_val = new_state[dim_to_shift].value

        # Move one step toward target
        if target_val > current_val:
            new_val = current_val + 1
        else:
            new_val = current_val - 1

        new_dims = list(self.state.dims)
        new_dims[dim_to_shift] = Trit(new_val)
        self.state = CognitiveState(tuple(new_dims))
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "state_index": self.state.index,
            "state_values": list(self.state.values),
            "weight": self.weight,
            "stability": self.stability,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SelfLevel":
        return cls(
            name=data["name"],
            description=data["description"],
            state=CognitiveState.from_values(data["state_values"]),
            weight=data.get("weight", 1.0),
            stability=data.get("stability", 0.9),
            last_updated=data.get("last_updated"),
        )


class NLPSelfLayer:
    """
    The agent's self-structure as a cognitive attractor.

    The self layer contains 8 levels (Dilts model adapted):
    1. Mission - why the agent exists
    2. Vision - what it wants to create
    3. Values - what it prioritizes
    4. Identity - who it is
    5. Beliefs - what it holds true
    6. Capabilities - what it can do
    7. Behaviors - how it acts
    8. Environment - where it operates

    The "attractor" is the weighted center of these levels.
    The agent's daily cognitive states fluctuate around this attractor.

    When the agent has a successful experience, the corresponding
    self levels shift slightly toward that state. When it fails,
    they shift away. Over time, the attractor stabilizes into
    the agent's personality.
    """

    # Default level names (Dilts model, bottom-up)
    DEFAULT_LEVELS = [
        "environment",    # Where/when
        "behaviors",      # What
        "capabilities",   # How
        "beliefs",        # Why
        "identity",       # Who
        "values",         # What matters
        "vision",         # What future
        "mission",        # What purpose
    ]

    def __init__(self) -> None:
        self.levels: Dict[str, SelfLevel] = {}
        self._attractor: Optional[CognitiveState] = None
        self._attractor_dirty = True

    def set_level(
        self,
        name: str,
        description: str,
        state: CognitiveState,
        weight: float = 1.0,
        stability: float = 0.9,
    ) -> SelfLevel:
        """Set or update a self level."""
        level = SelfLevel(
            name=name,
            description=description,
            state=state,
            weight=weight,
            stability=stability,
        )
        self.levels[name] = level
        self._attractor_dirty = True
        return level

    def get_level(self, name: str) -> Optional[SelfLevel]:
        return self.levels.get(name)

    @property
    def attractor(self) -> CognitiveState:
        """
        Compute the cognitive attractor: weighted center of all levels.

        The attractor is NOT a simple average. Each dimension is computed
        by weighted voting across all levels:

        For each dimension:
        - Sum (weight * value) across all levels
        - If sum > threshold -> YANG (+1)
        - If sum < -threshold -> YIN (-1)
        - Otherwise -> VOID (0)

        The threshold depends on how dispersed the levels are.
        More dispersed = higher threshold = more likely to be VOID.
        """
        if not self._attractor_dirty and self._attractor is not None:
            return self._attractor

        if not self.levels:
            self._attractor = CognitiveState.all_void()
            return self._attractor

        # Weighted sum for each dimension
        total_weight = sum(l.weight for l in self.levels.values())
        dim_sums = [0.0] * NUM_DIMENSIONS

        for level in self.levels.values():
            for i in range(NUM_DIMENSIONS):
                dim_sums[i] += level.weight * level.state[i].value

        # Normalize
        dim_scores = [s / total_weight for s in dim_sums]

        # Threshold: if all levels agree, threshold is low (decisive).
        # If levels disagree, threshold is high (cautious -> void).
        dim_variances = []
        for i in range(NUM_DIMENSIONS):
            vals = [l.state[i].value for l in self.levels.values()]
            mean_val = sum(vals) / len(vals)
            variance = sum((v - mean_val) ** 2 for v in vals) / len(vals)
            dim_variances.append(variance)

        # Convert to trits
        attractor_vals = []
        for i in range(NUM_DIMENSIONS):
            # Higher variance -> higher threshold needed
            threshold = 0.3 + dim_variances[i] * 0.5
            if dim_scores[i] > threshold:
                attractor_vals.append(1)
            elif dim_scores[i] < -threshold:
                attractor_vals.append(-1)
            else:
                attractor_vals.append(0)

        self._attractor = CognitiveState.from_values(attractor_vals)
        self._attractor_dirty = False
        return self._attractor

    def reinforce(
        self,
        experience_state: CognitiveState,
        positive: bool,
        force: float = 0.1,
    ) -> None:
        """
        Reinforce the self layer based on an experience.

        Positive experience: self levels shift slightly toward the experience state.
        Negative experience: self levels shift slightly away from the experience state.

        Higher levels (mission, vision) are more stable (change slower).
        Lower levels (environment, behaviors) are less stable (change faster).
        """
        # Stability decreases from top (mission) to bottom (environment)
        level_order = list(reversed(self.DEFAULT_LEVELS))

        for idx, level_name in enumerate(level_order):
            if level_name not in self.levels:
                continue

            level = self.levels[level_name]
            # Lower levels have lower stability
            level_stability = level.stability * (0.5 + 0.5 * idx / max(1, len(level_order) - 1))

            if positive:
                target = experience_state
            else:
                target = experience_state.opposite()

            # Adjust force based on stability
            adjusted_force = force * (1.0 - level_stability)
            if adjusted_force > 0.01:
                level.shift(target, force=adjusted_force)

        self._attractor_dirty = True

    def distance_to_attractor(self, state: CognitiveState) -> int:
        """How far a cognitive state is from the agent's personality center."""
        return state.distance(self.attractor)

    def alignment_score(self, state: CognitiveState) -> float:
        """
        How aligned a state is with the agent's self [0.0, 1.0].

        1.0 = perfectly aligned with personality
        0.0 = completely misaligned
        """
        max_dist = 18  # maximum possible distance
        dist = self.distance_to_attractor(state)
        return 1.0 - (dist / max_dist)

    def summary(self) -> str:
        """Human-readable summary of the self layer."""
        lines = [
            f"=== NLP Self Layer ===",
            f"Attractor: #{self.attractor.index} [{self.attractor}]",
            f"  Polarity: {self.attractor.polarity:+d}",
            f"  YIN:{self.attractor.yin_count} "
            f"VOID:{self.attractor.void_count} "
            f"YANG:{self.attractor.yang_count}",
            f"",
            f"Levels ({len(self.levels)}):",
        ]
        for name in self.DEFAULT_LEVELS:
            if name in self.levels:
                level = self.levels[name]
                lines.append(
                    f"  {name:15s} #{level.state.index} [{level.state}] "
                    f"w={level.weight:.1f} s={level.stability:.1f} "
                    f"- {level.description[:50]}"
                )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "levels": {name: level.to_dict() for name, level in self.levels.items()},
            "attractor_index": self.attractor.index,
            "attractor_values": list(self.attractor.values),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NLPSelfLayer":
        layer = cls()
        for name, level_data in data.get("levels", {}).items():
            layer.levels[name] = SelfLevel.from_dict(level_data)
        layer._attractor_dirty = True
        return layer

    def __repr__(self) -> str:
        return f"NLPSelfLayer(levels={len(self.levels)}, attractor=#{self.attractor.index})"
