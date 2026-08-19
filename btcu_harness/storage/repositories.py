"""
Repository layer for BTCU Harness storage.

Each repository wraps a MongoDB collection and provides domain-specific
operations. The StateSpaceRepository is the core mapping between the
19683-state space and persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from uuid import uuid4

from btcu_harness.core.encoding import encode, decode, DEFAULT_DIM
from btcu_harness.storage.mongo_client import MongoManager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class StateSpaceRepository:
    """
    Persist the mapping between state vectors and their indices.

    This is the foundational store that connects cognitive states to
    durable records.
    """

    COLLECTION = "state_space"

    def __init__(self, manager: MongoManager) -> None:
        self.collection = manager.collection(self.COLLECTION)

    def save_state(
        self,
        vector: Sequence[int],
        *,
        label: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Persist a state vector and return its record."""
        state_id = encode(vector)
        record: dict[str, Any] = {
            "state_id": state_id,
            "vector": list(vector),
            "symbol": self._symbol(vector),
            "polarity": sum(vector),
            "empty_count": sum(1 for v in vector if v == 0),
            "label": label,
            "metadata": metadata or {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        existing = self.find_by_id(state_id)
        if existing is None:
            self.collection.insert_one(record)
        else:
            record["created_at"] = existing.get("created_at", record["created_at"])
            self.collection.update_one(
                {"state_id": state_id},
                {"$set": record},
            )
        return record

    def find_by_id(self, state_id: int) -> Optional[dict[str, Any]]:
        """Return the record for a state index, or None."""
        return self.collection.find_one({"state_id": state_id})

    def find_by_vector(self, vector: Sequence[int]) -> Optional[dict[str, Any]]:
        """Return the record for a state vector, or None."""
        return self.find_by_id(encode(vector))

    def list_all(self) -> list[dict[str, Any]]:
        """Return all persisted state records."""
        return self.collection.find({})

    def count(self) -> int:
        """Number of persisted states."""
        return self.collection.count_documents({})

    @staticmethod
    def _symbol(vector: Sequence[int]) -> str:
        symbols = {-1: "T", 0: "0", 1: "1"}
        return "".join(symbols[v] for v in reversed(list(vector)))


class ExperimentLogRepository:
    """
    Daily experiment logs, similar to a researcher's lab notebook.

    Records include date, weather, task, state transitions, token usage,
    tags, and results.
    """

    COLLECTION = "experiment_logs"

    def __init__(self, manager: MongoManager) -> None:
        self.collection = manager.collection(self.COLLECTION)

    def add_log(
        self,
        *,
        date: Optional[str] = None,
        weather: Optional[str] = None,
        agent_id: Optional[str] = None,
        task: Optional[str] = None,
        state_before: Optional[int] = None,
        state_after: Optional[int] = None,
        actions: Optional[list[str]] = None,
        result: Optional[str] = None,
        tokens_used: int = 0,
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Append an experiment log entry."""
        record: dict[str, Any] = {
            "log_id": _new_id("EL"),
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "weather": weather,
            "agent_id": agent_id,
            "task": task,
            "state_before": state_before,
            "state_after": state_after,
            "actions": actions or [],
            "result": result,
            "tokens_used": tokens_used,
            "tags": tags or [],
            "created_at": _now(),
        }
        self.collection.insert_one(record)
        return record

    def list_by_date(self, date: str) -> list[dict[str, Any]]:
        """Return all logs for a given date."""
        return self.collection.find({"date": date})

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent logs. In-memory fallback returns insertion order."""
        docs = self.collection.find({})
        return docs[-limit:]


class LifeCourseRepository:
    """
    Life course memory: the growth autobiography of the Agent.

    Records key events such as skill acquisition, phase transitions,
    and other milestones.
    """

    COLLECTION = "life_course"

    def __init__(self, manager: MongoManager) -> None:
        self.collection = manager.collection(self.COLLECTION)

    def add_event(
        self,
        *,
        event_type: str,
        description: str,
        state_id: Optional[int] = None,
        phase: Optional[str] = None,
        date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record a life course event."""
        record: dict[str, Any] = {
            "life_event_id": _new_id("LE"),
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "event_type": event_type,
            "description": description,
            "state_id": state_id,
            "phase": phase,
            "created_at": _now(),
        }
        self.collection.insert_one(record)
        return record

    def list_events(self, event_type: Optional[str] = None) -> list[dict[str, Any]]:
        """List life course events, optionally filtered by type."""
        query = {"event_type": event_type} if event_type else {}
        return self.collection.find(query)


class CapabilityRepository:
    """
    Capability memory: skills, workflows, and task templates.

    Each capability has a unique index so tasks can reuse known workflows
    and save tokens.
    """

    COLLECTION = "capabilities"

    def __init__(self, manager: MongoManager) -> None:
        self.collection = manager.collection(self.COLLECTION)

    def add_capability(
        self,
        *,
        name: str,
        workflow: list[str],
        description: Optional[str] = None,
        input_schema: Optional[list[str]] = None,
        output_schema: Optional[list[str]] = None,
        avg_tokens: int = 0,
        success_rate: float = 0.0,
        state_template: Optional[Sequence[int]] = None,
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Register a reusable capability."""
        record: dict[str, Any] = {
            "capability_id": _new_id("CAP"),
            "name": name,
            "description": description,
            "workflow": workflow,
            "input_schema": input_schema or [],
            "output_schema": output_schema or [],
            "avg_tokens": avg_tokens,
            "success_rate": success_rate,
            "state_template": list(state_template) if state_template else None,
            "tags": tags or [],
            "last_used": None,
            "created_at": _now(),
        }
        self.collection.insert_one(record)
        return record

    def list_all(self) -> list[dict[str, Any]]:
        """Return all capabilities."""
        return self.collection.find({})

    def find_by_name(self, name: str) -> Optional[dict[str, Any]]:
        """Return a capability by name, or None."""
        return self.collection.find_one({"name": name})

    def mark_used(self, capability_id: str) -> None:
        """Update last_used timestamp for a capability."""
        self.collection.update_one(
            {"capability_id": capability_id},
            {"$set": {"last_used": _now()}},
        )
