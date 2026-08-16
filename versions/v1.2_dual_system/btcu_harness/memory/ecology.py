"""
MemoryEcology: The living memory system that unifies state and transition memory.

Memory in BTCU is not a database - it's an ecology. Memories:
- Grow through visits and transitions
- Compete for activation (limited attention)
- Resonate with each other (visiting one activates related ones)
- Decay when not accessed (suppression, not deletion)
- Form pathways (habits) and attractors (personality)

The ecology is the agent's accumulated cognitive experience. Over time,
frequent states become "home bases" (attractors), and frequent transitions
become "thinking habits" (pathways). This is how personality emerges
from practice - not by design, but by accumulation.

Key ecological operations:
- remember(): record a cognitive event (state visit + transition)
- recall(): retrieve relevant memories for a given state
- resonate(): activate related states when one is visited
- decay(): apply temporal forgetting
- sense_making(): discover patterns (seasons, attractors, blind spots)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.state import CognitiveState, SPACE_SIZE
from .state_memory import StateMemory, StateMemoryStore
from .transition_memory import TransitionMemory, TransitionStore


@dataclass
class CognitiveEvent:
    """A single cognitive event to be remembered."""

    state: CognitiveState
    prev_state: Optional[CognitiveState] = None
    context: Dict[str, Any] = field(default_factory=dict)
    decision: Optional[str] = None
    outcome: Optional[str] = None
    outcome_positive: Optional[bool] = None
    trigger: Optional[str] = None       # What triggered the transition
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CognitiveSeason:
    """
    An emerged cognitive pattern - a "season" in the 19683 space.

    Just as agricultural seasons emerge from repeated observation of
    natural cycles, cognitive seasons emerge from repeated patterns
    in the agent's cognitive practice.

    Types:
    - "attractor": A state the agent keeps returning to
    - "pathway": A transition the agent keeps making
    - "virtue": A pathway that consistently leads to success
    - "trap": A pathway that consistently leads to failure
    - "blind_spot": A region of the space never explored
    - "resonance": Two states that frequently co-activate
    """

    season_type: str
    description: str
    state_indices: List[int] = field(default_factory=list)
    transition_pairs: List[Tuple[int, int]] = field(default_factory=list)
    strength: float = 0.0
    evidence_count: int = 0


class MemoryEcology:
    """
    The unified, living memory system.

    Combines StateMemoryStore (19683 rooms) and TransitionStore (corridors)
    into a single ecological system with resonance, decay, and emergence.

    Usage:
        ecology = MemoryEcology()

        # Record a cognitive event
        ecology.remember(CognitiveEvent(
            state=CognitiveState.from_values([1, 0, -1, ...]),
            prev_state=CognitiveState.from_values([0, 0, -1, ...]),
            decision="invest",
            outcome="profit",
            outcome_positive=True,
        ))

        # Recall relevant memories
        memories = ecology.recall(some_state)

        # Discover emerged patterns
        seasons = ecology.sense_making()
    """

    def __init__(
        self,
        resonance_radius: int = 3,
        decay_factor: float = 0.95,
    ) -> None:
        """
        Args:
            resonance_radius: Max distance for automatic resonance.
                             States within this distance activate each other.
            decay_factor: Per-cycle decay factor [0.0, 1.0].
        """
        self.state_store = StateMemoryStore()
        self.transition_store = TransitionStore()
        self.resonance_radius = resonance_radius
        self.decay_factor = decay_factor

        # Track the agent's cognitive trajectory
        self._trajectory: List[int] = []

        # Track resonance discoveries
        self._resonance_discoveries: Dict[Tuple[int, int], int] = {}

    def remember(self, event: CognitiveEvent) -> None:
        """
        Record a cognitive event in the ecology.

        This is the primary write operation. It:
        1. Records the state visit (with context, decision, outcome)
        2. If there's a previous state, records the transition
        3. Activates resonance with nearby states
        4. Updates the cognitive trajectory
        """
        state_idx = event.state.index

        # 1. Record state visit
        self.state_store.visit(
            state_index=state_idx,
            context=event.context,
            decision=event.decision,
            outcome=event.outcome,
            outcome_positive=event.outcome_positive,
            metadata=event.metadata,
        )

        # 2. Record transition if there's a previous state
        if event.prev_state is not None:
            prev_idx = event.prev_state.index
            if prev_idx != state_idx:
                changed_dims = event.prev_state.diff_dimensions(event.state)
                self.transition_store.record(
                    from_idx=prev_idx,
                    to_idx=state_idx,
                    changed_dimensions=changed_dims,
                    trigger=event.trigger,
                    decision=event.decision,
                    outcome=event.outcome,
                    outcome_positive=event.outcome_positive,
                    metadata=event.metadata,
                )

                # Discover resonance: if these two states transition frequently
                pair_key: tuple[int, int] = (
                    min(prev_idx, state_idx),
                    max(prev_idx, state_idx),
                )
                self._resonance_discoveries[pair_key] = \
                    self._resonance_discoveries.get(pair_key, 0) + 1

                # If transitioned 3+ times, create explicit resonance
                if self._resonance_discoveries[pair_key] >= 3:
                    self.state_store.get(prev_idx).add_resonance(
                        state_idx, strength=0.1
                    )
                    self.state_store.get(state_idx).add_resonance(
                        prev_idx, strength=0.1
                    )

        # 3. Activate resonance with nearby states
        self._activate_resonance(state_idx)

        # 4. Update trajectory
        self._trajectory.append(state_idx)
        if len(self._trajectory) > 10000:
            self._trajectory = self._trajectory[-10000:]

    def _activate_resonance(self, center_idx: int) -> None:
        """Activate memories of states near the given state."""
        center = CognitiveState.from_index(center_idx)

        for idx, mem in self.state_store._rooms.items():
            if idx == center_idx:
                continue
            if mem.is_empty:
                continue

            other = CognitiveState.from_index(idx)
            dist = center.distance(other)

            if dist <= self.resonance_radius:
                # Closer = stronger activation
                activation_amount = 0.1 * (1 - dist / (self.resonance_radius + 1))
                mem.activation = min(1.0, mem.activation + activation_amount)

    def recall(
        self,
        state: CognitiveState,
        include_transitions: bool = True,
        include_resonance: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant memories for a given cognitive state.

        Returns:
            Dictionary with:
            - "state": The StateMemory for this state (may be empty)
            - "incoming_transitions": How the agent got here before
            - "outgoing_transitions": Where the agent went from here
            - "resonant_states": Nearby states with memory
            - "suggestions": Actionable suggestions based on history
        """
        idx = state.index
        result: Dict[str, Any] = {}

        # State memory
        result["state"] = self.state_store.get(idx)

        # Transition memories
        if include_transitions:
            result["incoming_transitions"] = self.transition_store.pathways_to(idx)
            result["outgoing_transitions"] = self.transition_store.pathways_from(idx)

        # Resonant states
        if include_resonance:
            resonant = []
            center_mem = self.state_store.get(idx)

            # Explicit resonance links
            for other_idx, strength in center_mem.resonance_links.items():
                other_mem = self.state_store.get_or_none(other_idx)
                if other_mem and not other_mem.is_empty:
                    resonant.append((other_idx, strength, other_mem))

            # Nearby states with memory (if not enough explicit links)
            if len(resonant) < 5:
                center = CognitiveState.from_index(idx)
                for other_idx, mem in self.state_store._rooms.items():
                    if other_idx == idx or mem.is_empty:
                        continue
                    other = CognitiveState.from_index(other_idx)
                    dist = center.distance(other)
                    if dist <= self.resonance_radius:
                        strength = 1.0 / (1 + dist)
                        resonant.append((other_idx, strength, mem))

            resonant.sort(key=lambda x: x[1], reverse=True)
            result["resonant_states"] = resonant[:10]

        # Suggestions based on history
        result["suggestions"] = self._generate_suggestions(idx)

        return result

    def _generate_suggestions(self, state_idx: int) -> List[str]:
        """Generate actionable suggestions based on memory history."""
        suggestions: List[str] = []
        mem = self.state_store.get(state_idx)

        # If this state has been visited before with outcomes
        if mem.success_count > 0 and mem.failure_count == 0:
            suggestions.append(
                f"This state has a perfect record ({mem.success_count} successes). "
                f"Consider past successful decisions."
            )

        if mem.failure_count > mem.success_count and mem.failure_count >= 3:
            suggestions.append(
                f"Warning: This state has a poor track record "
                f"({mem.failure_count} failures vs {mem.success_count} successes). "
                f"Consider an alternative path."
            )

        # Check outgoing transitions for virtues and traps
        outgoing = self.transition_store.pathways_from(state_idx)
        for tm in outgoing:
            if tm.is_virtue:
                suggestions.append(
                    f"Pathway to state #{tm.to_index} is a cognitive virtue "
                    f"(success rate: {tm.success_rate:.0%})."
                )
            elif tm.is_trap:
                suggestions.append(
                    f"Warning: Pathway to state #{tm.to_index} is a cognitive trap "
                    f"(success rate: {tm.success_rate:.0%})."
                )

        # Check suppressed decisions
        if mem.suppressed_decisions:
            suggestions.append(
                f"Suppressed decisions for this state: {mem.suppressed_decisions}"
            )

        return suggestions

    def decay(self) -> None:
        """Apply one cycle of temporal decay to all memories."""
        self.state_store.decay_all(self.decay_factor)
        self.transition_store.decay_all(self.decay_factor)

    def sense_making(self) -> List[CognitiveSeason]:
        """
        Discover emerged cognitive patterns.

        This is the "cognitive seasons" mechanism - analyzing accumulated
        experience to find patterns that weren't predefined but emerged
        from practice.

        Returns a list of CognitiveSeason objects describing discovered patterns.
        """
        seasons: List[CognitiveSeason] = []

        # 1. Attractors: most visited and most activated states
        top_visited = self.state_store.most_visited(n=10)
        for mem in top_visited:
            if mem.visit_count >= 5:
                seasons.append(CognitiveSeason(
                    season_type="attractor",
                    description=f"State #{mem.state_index} is a cognitive attractor "
                               f"(visited {mem.visit_count} times, "
                               f"activation {mem.activation:.2f})",
                    state_indices=[mem.state_index],
                    strength=mem.activation,
                    evidence_count=mem.visit_count,
                ))

        # 2. Virtues: successful pathways
        for tm in self.transition_store.virtues():
            seasons.append(CognitiveSeason(
                season_type="virtue",
                description=f"Transition {tm.from_index}->{tm.to_index} "
                           f"is a cognitive virtue "
                           f"(success rate: {tm.success_rate:.0%})",
                transition_pairs=[(tm.from_index, tm.to_index)],
                strength=tm.success_rate,
                evidence_count=tm.traverse_count,
            ))

        # 3. Traps: failing pathways
        for tm in self.transition_store.traps():
            seasons.append(CognitiveSeason(
                season_type="trap",
                description=f"Transition {tm.from_index}->{tm.to_index} "
                           f"is a cognitive trap "
                           f"(failure rate: {1-tm.success_rate:.0%})",
                transition_pairs=[(tm.from_index, tm.to_index)],
                strength=1 - tm.success_rate,
                evidence_count=tm.traverse_count,
            ))

        # 4. Blind spots: unexplored regions
        visited = set(self.state_store._rooms.keys())
        if len(visited) < SPACE_SIZE:
            # Find the largest contiguous unexplored region
            unexplored_count = SPACE_SIZE - len(visited)
            seasons.append(CognitiveSeason(
                season_type="blind_spot",
                description=f"{unexplored_count} states ({unexplored_count/SPACE_SIZE:.1%}) "
                           f"of the cognitive space remain unexplored",
                strength=unexplored_count / SPACE_SIZE,
                evidence_count=unexplored_count,
            ))

        # 5. Resonance patterns: frequently co-occurring states
        for (idx_a, idx_b), count in self._resonance_discoveries.items():
            if count >= 5:
                seasons.append(CognitiveSeason(
                    season_type="resonance",
                    description=f"States #{idx_a} and #{idx_b} "
                               f"resonate (co-occurred {count} times)",
                    state_indices=[idx_a, idx_b],
                    strength=min(1.0, count / 10),
                    evidence_count=count,
                ))

        return seasons

    def export_legacy(self) -> Dict[str, Any]:
        """
        Export the entire memory ecology for transfer to a new agent.

        This is how cognitive experience is inherited - a new agent
        starts with populated rooms instead of 19683 empty ones.
        """
        return {
            "state_memories": self.state_store.to_dict(),
            "transition_memories": self.transition_store.to_dict(),
            "trajectory": self._trajectory,
            "resonance_discoveries": {
                f"{a}_{b}": c
                for (a, b), c in self._resonance_discoveries.items()
            },
            "stats": {
                "visited_states": self.state_store.visited_count,
                "total_visits": self.state_store.total_visits,
                "coverage": self.state_store.coverage,
                "total_corridors": self.transition_store.total_corridors,
                "virtues": len(self.transition_store.virtues()),
                "traps": len(self.transition_store.traps()),
            },
        }

    def import_legacy(self, data: Dict[str, Any]) -> None:
        """Import a previously exported legacy."""
        self.state_store = StateMemoryStore.from_dict(data.get("state_memories", {}))
        self.transition_store = TransitionStore.from_dict(
            data.get("transition_memories", {})
        )
        self._trajectory = data.get("trajectory", [])
        for key_str, count in data.get("resonance_discoveries", {}).items():
            a, b = key_str.split("_")
            self._resonance_discoveries[(int(a), int(b))] = count

    @property
    def trajectory(self) -> List[int]:
        """The agent's cognitive trajectory (sequence of state indices)."""
        return self._trajectory

    def __repr__(self) -> str:
        return (
            f"MemoryEcology(\n"
            f"  {self.state_store}\n"
            f"  {self.transition_store}\n"
            f")"
        )
