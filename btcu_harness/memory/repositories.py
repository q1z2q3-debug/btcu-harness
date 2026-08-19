"""
Memory repositories - the three concrete memory banks of BTCU Harness.

    1. ExperienceLogRepo : daily project logs / experiment notebooks
    2. LifeCourseRepo    : agent growth and evolution records
    3. CapabilityRepo    : reusable skills and workflows (token-saving index)

Every record carries a cognitive state id (0..19682) so memory is
anchored in the same coordinate system as cognition itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from btcu_harness.storage.mongo_client import MongoStore


def _now() -> int:
    return int(time.time() * 1000)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


@dataclass
class ExperienceLog:
    """A daily experiment / task record, like a researcher's lab notebook."""

    date: str = field(default_factory=_today)
    weather: str = ""
    agent_id: str = "agent_001"
    task: str = ""
    state_before: Optional[int] = None
    state_after: Optional[int] = None
    actions: list[str] = field(default_factory=list)
    result: str = ""
    tokens_used: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "log_id": f"EL-{self.date}-{_now()}",
            **self.__dict__,
        }


@dataclass
class LifeEvent:
    """A single growth event in the agent's life course."""

    event_type: str = ""
    description: str = ""
    date: str = field(default_factory=_today)
    state_id: Optional[int] = None
    phase: str = "schooling"  # schooling | internalizing | graduated

    def to_dict(self) -> dict:
        return {
            "life_event_id": f"LE-{_now()}",
            **self.__dict__,
        }


@dataclass
class Capability:
    """A reusable skill / workflow, addressed by a unique id to save tokens."""

    name: str = ""
    version: int = 1
    input_desc: str = ""
    workflow: list[str] = field(default_factory=list)
    output_desc: str = ""
    avg_tokens: int = 0
    state_template: list[int] = field(default_factory=list)
    success_rate: float = 0.0
    last_used: str = field(default_factory=_today)

    def to_dict(self) -> dict:
        return {
            "capability_id": f"CAP-{self.name.upper().replace(' ', '-')}",
            **self.__dict__,
        }


class ExperienceLogRepo:
    """Daily project log memory, like a lab notebook."""

    COLLECTION = "experiment_logs"

    def __init__(self, store: MongoStore) -> None:
        self.store = store

    def add(self, log: ExperienceLog) -> dict:
        return self.store.insert(self.COLLECTION, log.to_dict())

    def by_date(self, date: str) -> list[dict]:
        return self.store.find(self.COLLECTION, {"date": date})

    def by_tag(self, tag: str, limit: int = 20) -> list[dict]:
        return self.store.find(
            self.COLLECTION, {"tags": tag}, limit=limit
        )


class LifeCourseRepo:
    """Growth record of the agent's life: schooling -> graduated."""

    COLLECTION = "life_course"

    def __init__(self, store: MongoStore) -> None:
        self.store = store

    def add(self, event: LifeEvent) -> dict:
        return self.store.insert(self.COLLECTION, event.to_dict())

    def by_phase(self, phase: str) -> list[dict]:
        return self.store.find(self.COLLECTION, {"phase": phase})

    def all(self) -> list[dict]:
        return self.store.find(self.COLLECTION, {})


class CapabilityRepo:
    """
    Reusable skills and workflows.

    The core token-saving mechanism: known tasks hit an indexed
    capability instead of calling the LLM from scratch.
    """

    COLLECTION = "capabilities"

    def __init__(self, store: MongoStore) -> None:
        self.store = store

    def add(self, cap: Capability) -> dict:
        return self.store.insert(self.COLLECTION, cap.to_dict())

    def find_by_name(self, name: str):
        return self.store.find_one(
            self.COLLECTION, {"capability_id": f"CAP-{name.upper().replace(' ', '-')}"}
        )

    def all(self) -> list[dict]:
        return self.store.find(self.COLLECTION, {})
