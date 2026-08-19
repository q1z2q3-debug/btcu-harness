"""
Flexible dimension templates for BTCU Harness.

The nine dimensions are NOT fixed dogma. They are reference templates
demonstrating how trits can be arranged into a cognitive coordinate
system. Each dimension has a name and semantic labels for its three
trit states: YIN (-1), EMPTY (0), YANG (+1).

Different domains can self-adapt, replace, or extend these dimensions.
Only the trit structure itself is fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from btcu_harness.core.btcu import T, Z, O


@dataclass(frozen=True)
class Dimension:
    """A single cognitive dimension with three semantic states."""

    key: str
    label: str
    yin: str
    empty: str
    yang: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "yin": self.yin,
            "empty": self.empty,
            "yang": self.yang,
        }

    def state_label(self, trit: int) -> str:
        """Return the semantic label for a trit."""
        return {T: self.yin, Z: self.empty, O: self.yang}[trit]


# The default nine-dimensional template
DEFAULT_DIMENSION_LIST: list[Dimension] = [
    Dimension(key="time", label="Time", yin="past", empty="now", yang="future"),
    Dimension(key="space", label="Space", yin="internal", empty="boundary", yang="external"),
    Dimension(key="causality", label="Causality", yin="cause", empty="condition", yang="effect"),
    Dimension(key="value", label="Value", yin="harmful", empty="suspended", yang="beneficial"),
    Dimension(key="relation", label="Relation", yin="opposition", empty="neutral", yang="cooperation"),
    Dimension(key="action", label="Action", yin="retreat", empty="hold", yang="advance"),
    Dimension(key="subject", label="Subject", yin="other", empty="relation", yang="self"),
    Dimension(key="intent", label="Intent", yin="defensive", empty="adaptive", yang="offensive"),
    Dimension(key="cognition", label="Cognition", yin="unknown", empty="exploring", yang="known"),
]


def default_dimensions() -> list[Dimension]:
    """Return a copy of the default nine-dimension template."""
    return list(DEFAULT_DIMENSION_LIST)


def dimension_map() -> dict[str, Dimension]:
    """Return a key-indexed map of the default dimensions."""
    return {d.key: d for d in DEFAULT_DIMENSION_LIST}


def interpret_vector(
    vector: list[int],
    dims: list[Dimension] | None = None,
) -> list[dict[str, str]]:
    """Interpret a trit vector using the given dimensions.

    Returns a list of human-readable per-dimension interpretations.
    """
    dims = dims or DEFAULT_DIMENSION_LIST
    if len(vector) != len(dims):
        raise ValueError(
            f"Vector length {len(vector)} does not match dimensions {len(dims)}"
        )

    result = []
    for trit, dim in zip(vector, dims):
        result.append(
            {
                "dimension": dim.label,
                "key": dim.key,
                "trit": trit,
                "state": dim.state_label(trit),
            }
        )
    return result


def dimensions_from_definition(definition: list[dict[str, str]]) -> list[Dimension]:
    """Create dimensions from a JSON-style definition.

    This is the entry point for self-adaptation: a domain can provide
    its own nine dimensions at runtime.
    """
    dims = []
    for item in definition:
        dims.append(
            Dimension(
                key=item["key"],
                label=item.get("label", item["key"]),
                yin=item.get("yin", "yin"),
                empty=item.get("empty", "empty"),
                yang=item.get("yang", "yang"),
            )
        )
    return dims
