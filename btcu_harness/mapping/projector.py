"""
Cognitive projector for BTCU Harness.

Maps external inputs (structured features) into the nine-dimensional
ternary state space. This is a rule-based MVP projector that can be
replaced or augmented by LLM-based or human-AI collaborative projectors.
"""

from __future__ import annotations

from typing import Any, Mapping

from btcu_harness.core.btcu import T, Z, O
from btcu_harness.core.encoding import encode
from btcu_harness.mapping.dimensions import (
    DEFAULT_DIMENSION_LIST,
    Dimension,
    interpret_vector,
)


class RuleProjector:
    """Rule-based cognitive projector.

    Maps a feature dictionary to a nine-dimensional trit vector.
    The MVP version uses explicit feature keys, one per dimension.
    Each feature value should be -1, 0, or 1; missing keys default to 0.
    """

    def __init__(self, dims: list[Dimension] | None = None) -> None:
        self.dims = dims or DEFAULT_DIMENSION_LIST
        self.keys = [d.key for d in self.dims]

    def project(self, features: Mapping[str, Any]) -> list[int]:
        """Project a feature map into a trit vector.

        Missing keys default to EMPTY (0).
        """
        vector: list[int] = []
        for key in self.keys:
            raw = features.get(key, Z)
            vector.append(self._coerce(raw))
        return vector

    def project_to_index(self, features: Mapping[str, Any]) -> int:
        """Project a feature map and return the encoded state index."""
        return encode(self.project(features))

    def interpret(self, features: Mapping[str, Any]) -> list[dict[str, str]]:
        """Project and interpret the resulting trit vector."""
        return interpret_vector(self.project(features), self.dims)

    @staticmethod
    def _coerce(raw: Any) -> int:
        if raw is None:
            return Z
        if isinstance(raw, bool):
            return O if raw else T
        if isinstance(raw, (int, float)):
            if raw > 0:
                return O
            if raw < 0:
                return T
            return Z
        if isinstance(raw, str):
            text = raw.strip().lower()
            return {"positive": O, "pos": O, "yang": O, "+": O,
                    "negative": T, "neg": T, "yin": T, "-": T}.get(text, Z)
        return Z
