"""
BTCU Harness - Memory Repository (In-Memory MVP)

Local in-memory repository for memory traces. Provides state
resonance and trajectory retrieval without external dependencies.

MongoDB persistence is introduced in btcu_harness.storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from btcu_harness.core.space import Space19683
from btcu_harness.memory.trace import MemoryTrace


@dataclass
class MemoryRepository:
    """In-memory repository for cognitive memory traces.

    Attributes:
        space: The 19683 state space for distance and similarity.
        traces: Mapping from trace_id to MemoryTrace.
    """

    space: Space19683 = field(default_factory=Space19683)
    traces: dict[str, MemoryTrace] = field(default_factory=dict)

    def write(self, trace: MemoryTrace) -> None:
        """Store a memory trace.

        Args:
            trace: MemoryTrace to store.
        """

        self.traces[trace.trace_id] = trace

    def get(self, trace_id: str) -> Optional[MemoryTrace]:
        """Retrieve a memory trace by id.

        Args:
            trace_id: Trace identifier.

        Returns:
            MemoryTrace if found, otherwise None.
        """

        return self.traces.get(trace_id)

    def find_similar(
        self,
        current_state: int,
        limit: int = 5,
    ) -> list[MemoryTrace]:
        """Find traces whose last state resonates with current_state.

        Resonance is measured using ternary similarity; higher score
        means stronger resonance.

        Args:
            current_state: Decimal state index to match against.
            limit: Maximum number of traces to return.

        Returns:
            List of traces sorted by descending similarity.
        """

        scored: list[tuple[int, MemoryTrace]] = []
        for trace in self.traces.values():
            score = self.space.similarity(current_state, trace.last_state())
            scored.append((score, trace))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [trace for _, trace in scored[:limit]]

    def suspend(self, trace_id: str) -> None:
        """Mark a trace as suspended (0).

        Args:
            trace_id: Trace identifier.

        Raises:
            KeyError: If the trace is not found.
        """

        trace = self.traces[trace_id]
        trace.suspend()

    def reinforce(self, trace_id: str) -> None:
        """Mark a trace as reinforced (+1).

        Args:
            trace_id: Trace identifier.

        Raises:
            KeyError: If the trace is not found.
        """

        trace = self.traces[trace_id]
        trace.reinforce()

    def suppress(self, trace_id: str) -> None:
        """Mark a trace as suppressed (-1).

        Args:
            trace_id: Trace identifier.

        Raises:
            KeyError: If the trace is not found.
        """

        trace = self.traces[trace_id]
        trace.suppress()
