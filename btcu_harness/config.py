"""
BTCU Harness - Configuration

Centralized runtime configuration. Uses environment variables with sane
defaults so the harness runs anywhere without hard dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StorageConfig:
    """Storage layer configuration."""

    # MongoDB connection
    mongo_uri: str = field(
        default_factory=lambda: os.getenv(
            "BTCU_MONGO_URI", "mongodb://127.0.0.1:27017"
        )
    )
    mongo_db_name: str = field(
        default_factory=lambda: os.getenv("BTCU_MONGO_DB", "btcu_harness")
    )

    # Fallback behavior: when MongoDB is unavailable, use in-memory store
    allow_in_memory_fallback: bool = field(
        default_factory=lambda: os.getenv("BTCU_IN_MEMORY_FALLBACK", "1") == "1"
    )

    # Local file fallback directory (optional)
    local_store_dir: Optional[str] = field(
        default_factory=lambda: os.getenv("BTCU_LOCAL_STORE", None)
    )


@dataclass
class HarnessConfig:
    """Top-level harness configuration."""

    storage: StorageConfig = field(default_factory=StorageConfig)
    default_dim: int = field(
        default_factory=lambda: int(os.getenv("BTCU_DEFAULT_DIM", "9"))
    )


def load_config() -> HarnessConfig:
    """Load configuration from environment."""
    return HarnessConfig()
