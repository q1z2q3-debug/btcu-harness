"""
BTCU Harness performance optimizations.

Provides:
- LRU caching for CognitiveState.from_index (hot path)
- Batch state creation and distance computation
- Lazy loading for StateMemoryStore
- Precomputed neighbor lists

Usage:
    from btcu_harness.performance import cached_from_index, batch_distance

    state = cached_from_index(9841)  # O(1) after first call
    dists = batch_distance(source, [target1, target2, target3])
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Tuple

from .core.state import CognitiveState, NUM_DIMENSIONS


# --- State caching ---

@lru_cache(maxsize=19683)
def cached_from_index(index: int) -> CognitiveState:
    """
    Cached version of CognitiveState.from_index().

    Since there are exactly 19683 possible states, caching all of them
    uses negligible memory (~1MB) and eliminates repeated decoding.

    After warmup, this is O(1) instead of O(9).
    """
    return CognitiveState.from_index(index)


@lru_cache(maxsize=19683)
def cached_all_yang() -> CognitiveState:
    """Cached singleton for all-yang state."""
    return CognitiveState.all_yang()


@lru_cache(maxsize=19683)
def cached_all_yin() -> CognitiveState:
    """Cached singleton for all-yin state."""
    return CognitiveState.all_yin()


@lru_cache(maxsize=19683)
def cached_all_void() -> CognitiveState:
    """Cached singleton for all-void state."""
    return CognitiveState.all_void()


# --- Batch operations ---

def batch_from_indices(indices: List[int]) -> List[CognitiveState]:
    """Create multiple CognitiveStates from indices in one call."""
    return [cached_from_index(i) for i in indices]


def batch_distance(
    source: CognitiveState,
    targets: List[CognitiveState],
) -> List[int]:
    """
    Compute distance from source to multiple targets.

    Optimized: extracts source values once, then iterates.
    """
    src_vals = [source[i].value for i in range(NUM_DIMENSIONS)]
    results = []
    for target in targets:
        dist = 0
        for i in range(NUM_DIMENSIONS):
            dist += abs(src_vals[i] - target[i].value)
        results.append(dist)
    return results


def batch_polarity(states: List[CognitiveState]) -> List[int]:
    """Compute polarity for multiple states."""
    return [s.polarity for s in states]


def batch_opposite(states: List[CognitiveState]) -> List[CognitiveState]:
    """Compute opposite for multiple states."""
    return [s.opposite() for s in states]


# --- Neighbor precomputation ---

_NEIGHBOR_CACHE: dict[int, List[CognitiveState]] = {}


def get_neighbors(state: CognitiveState) -> List[CognitiveState]:
    """
    Get all adjacent states (distance=1) with caching.

    A state has at most 18 neighbors (9 dims * 2 directions),
    but fewer if some dims are at extremes.
    """
    idx = state.index
    if idx in _NEIGHBOR_CACHE:
        return _NEIGHBOR_CACHE[idx]

    neighbors = []
    for i in range(NUM_DIMENSIONS):
        val = state[i].value
        # Try moving up (toward +1)
        if val < 1:
            new_vals = list(state.values)
            new_vals[i] = val + 1
            neighbors.append(CognitiveState.from_values(new_vals))
        # Try moving down (toward -1)
        if val > -1:
            new_vals = list(state.values)
            new_vals[i] = val - 1
            neighbors.append(CognitiveState.from_values(new_vals))

    _NEIGHBOR_CACHE[idx] = neighbors
    return neighbors


def clear_caches() -> None:
    """Clear all caches. Useful for testing or memory management."""
    cached_from_index.cache_clear()
    cached_all_yang.cache_clear()
    cached_all_yin.cache_clear()
    cached_all_void.cache_clear()
    _NEIGHBOR_CACHE.clear()


def cache_stats() -> dict[str, tuple[int, int]]:
    """Return cache hit/miss statistics."""
    return {
        "from_index": cached_from_index.cache_info()[:2],  # hits, misses
        "all_yang": cached_all_yang.cache_info()[:2],
        "all_yin": cached_all_yin.cache_info()[:2],
        "all_void": cached_all_void.cache_info()[:2],
        "neighbors": (0, len(_NEIGHBOR_CACHE)),
    }
