"""
BTCU Harness - Memory Layer

Memory is not static storage. It is a cognitive ecology.

Three memory layers:
    1. Experience memory (experiment logs)
    2. Capability memory (skills and workflows)
    3. Life course memory (agent growth records)

Plus the core trace mechanism: state transition paths.
"""

from btcu_harness.memory.trace import MemoryTrace, TraceRecord
from btcu_harness.memory.repositories import (
    ExperienceLogRepo,
    LifeCourseRepo,
    CapabilityRepo,
)

__all__ = [
    "MemoryTrace",
    "TraceRecord",
    "ExperienceLogRepo",
    "LifeCourseRepo",
    "CapabilityRepo",
]
