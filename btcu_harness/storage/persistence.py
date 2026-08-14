"""
PersistenceLayer: Save and load the entire BTCU cognitive state.

Enables the agent's memory, self layer, trajectory, and patterns
to survive across sessions. The agent can shut down and restart
with all cognitive experience intact.

Storage format: JSON (human-readable, debuggable)
Future: MongoDB adapter for production use.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..core.space import CognitiveSpace
from ..memory.ecology import MemoryEcology
from ..memory.trajectory import CognitiveTrajectory
from ..mapping.pattern_learner import PatternLearner


class PersistenceLayer:
    """
    Persists and restores the complete BTCU cognitive state.

    The cognitive state includes:
    - Memory ecology (state memories + transition memories)
    - Cognitive trajectory (sequence of visited states)
    - Pattern learner (learned projection patterns)
    - Self layer (identity, values, attractor)
    - Dimension configuration (locked dimension labels)
    - Growth stage
    """

    def __init__(self, storage_path: str) -> None:
        self.storage_path = storage_path

    def save(
        self,
        ecology: MemoryEcology,
        trajectory: CognitiveTrajectory,
        pattern_learner: PatternLearner,
        self_layer: Any,  # NLPSelfLayer
        dim_labels: list,
        growth_stage: str,
        metadata: Optional[Dict[str, Any]] = None,
        climate: Any = None,  # CognitiveClimate
    ) -> str:
        """Save the complete cognitive state to disk."""
        data = {
            "version": "0.3",
            "saved_at": _now_iso(),
            "dimension_labels": dim_labels,
            "growth_stage": growth_stage,
            "memory_ecology": ecology.export_legacy(),
            "trajectory": trajectory.to_dict(),
            "pattern_learner": pattern_learner.to_dict(),
            "self_layer": self_layer.to_dict() if self_layer else None,
            "climate": climate.to_dict() if climate else None,
            "metadata": metadata or {},
        }

        os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return self.storage_path

    def load(self) -> Optional[Dict[str, Any]]:
        """Load cognitive state from disk. Returns None if file doesn't exist."""
        if not os.path.exists(self.storage_path):
            return None

        with open(self.storage_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def restore_ecology(self, data: Dict[str, Any]) -> MemoryEcology:
        eco = MemoryEcology()
        eco.import_legacy(data.get("memory_ecology", {}))
        return eco

    def restore_trajectory(self, data: Dict[str, Any]) -> CognitiveTrajectory:
        return CognitiveTrajectory.from_dict(data.get("trajectory", {}))

    def restore_pattern_learner(self, data: Dict[str, Any]) -> PatternLearner:
        return PatternLearner.from_dict(data.get("pattern_learner", {}))

    def restore_self_layer(self, data: Dict[str, Any]):
        from ..self_layer import NLPSelfLayer
        sl_data = data.get("self_layer")
        if sl_data:
            return NLPSelfLayer.from_dict(sl_data)
        return NLPSelfLayer()

    def restore_climate(self, data: Dict[str, Any]):
        from ..memory.climate import CognitiveClimate
        cl_data = data.get("climate")
        if cl_data:
            return CognitiveClimate.from_dict(cl_data)
        return CognitiveClimate()

    @property
    def exists(self) -> bool:
        return os.path.exists(self.storage_path)

    def info(self) -> str:
        """Human-readable info about the persisted state."""
        if not self.exists:
            return f"PersistenceLayer: no saved state at {self.storage_path}"

        data = self.load()
        if not data:
            return "PersistenceLayer: unable to read saved state"

        eco_stats = data.get("memory_ecology", {}).get("stats", {})
        traj = data.get("trajectory", {})
        patterns = data.get("pattern_learner", {})

        lines = [
            f"PersistenceLayer: {self.storage_path}",
            f"  Version: {data.get('version', 'unknown')}",
            f"  Saved: {data.get('saved_at', 'unknown')}",
            f"  Growth stage: {data.get('growth_stage', 'unknown')}",
            f"  Dimensions: {data.get('dimension_labels', [])}",
            f"  Memory: {eco_stats.get('visited_states', 0)} states visited, "
            f"{eco_stats.get('total_visits', 0)} total visits",
            f"  Trajectory: {len(traj.get('points', []))} points",
            f"  Patterns: {len(patterns.get('patterns', []))} learned",
            f"  Self layer: {'set' if data.get('self_layer') else 'none'}",
        ]
        return "\n".join(lines)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
