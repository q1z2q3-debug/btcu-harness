"""
BTCU Harness logging configuration.

Provides structured logging with configurable levels, file output,
and integration with the cognitive architecture.

Usage:
    from btcu_harness.logging_config import get_logger, setup_logging

    # One-time setup
    setup_logging(level="INFO", log_file="btcu.log")

    # In any module
    logger = get_logger("btcu_harness.core")
    logger.info("Cognitive state projected: #%d", state_index)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, MutableMapping, Optional


# Module-level flag to prevent duplicate setup
_configured = False

# Default format includes timestamp, level, module, and message
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    fmt: str = _DEFAULT_FORMAT,
    datefmt: str = _DEFAULT_DATE_FORMAT,
) -> None:
    """
    Configure global logging for BTCU Harness.

    Args:
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR").
        log_file: Optional file path. If provided, logs to both
                  console and file. If None, console only.
        fmt: Log message format string.
        datefmt: Date format string.
    """
    global _configured

    if _configured:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)
    for handler in handlers:
        handler.setFormatter(formatter)

    root = logging.getLogger("btcu_harness")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger under the btcu_harness namespace.

    Args:
        name: Module name (e.g., "btcu_harness.core.trit").

    Returns:
        Configured logger instance.
    """
    if not name.startswith("btcu_harness"):
        name = f"btcu_harness.{name}"
    return logging.getLogger(name)


class CognitiveLogAdapter(logging.LoggerAdapter):
    """Logger adapter that injects cognitive context into log records."""

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[str, MutableMapping[str, Any]]:
        ctx = self.extra or {}
        state_idx = ctx.get("state_index")
        stage = ctx.get("growth_stage", "?")
        if state_idx is not None:
            prefix = f"[{stage}|#{state_idx}]"
        else:
            prefix = f"[{stage}]"
        return f"{prefix} {msg}", kwargs
