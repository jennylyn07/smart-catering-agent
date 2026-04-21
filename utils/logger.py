"""utils/logger.py

Provides structured JSON logging for the Smart Catering multi-agent system.

All services (API layer, orchestrator, and agents) should use this module so logs
are consistent and machine-searchable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Optional


LOGGER_NAME = "smart_catering"


def _utc_iso_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()


class _JsonLineFormatter(logging.Formatter):
    """Format log records as one-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        """Format a LogRecord into a JSON string.

        Args:
            record: Standard library logging record to format.

        Returns:
            A single-line JSON string containing the structured log payload.
        """
        payload: dict[str, Any] = {
            "timestamp": _utc_iso_timestamp(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        agent_id = getattr(record, "agent_id", None)
        if agent_id is not None:
            payload["agent_id"] = agent_id

        action = getattr(record, "action", None)
        if action is not None:
            payload["action"] = action

        status = getattr(record, "status", None)
        if status is not None:
            payload["status"] = status

        details = getattr(record, "details", None)
        if details is not None:
            payload["details"] = details

        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger() -> logging.Logger:
    """Return the application logger configured for JSON output."""

    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(_JsonLineFormatter())

    logger.addHandler(handler)
    return logger


@dataclass(frozen=True)
class LogEvent:
    """A structured log entry describing an agent/system action."""

    agent_id: str
    action: str
    status: str
    details: Mapping[str, Any] | None = None


def log_event(
    *,
    agent_id: str,
    action: str,
    status: str,
    details: Optional[Mapping[str, Any]] = None,
    level: int = logging.INFO,
) -> None:
    """Write a structured event log.

    Args:
        agent_id: ID of the component producing the log (e.g., "concierge").
        action: The action being performed (e.g., "parse_request").
        status: Result status (e.g., "started", "success", "error").
        details: Extra structured context for debugging/audit.
        level: Standard Python logging level.

    Returns:
        None
    """

    logger = get_logger()

    safe_details: MutableMapping[str, Any] | None
    if details is None:
        safe_details = None
    else:
        safe_details = dict(details)

    logger.log(
        level,
        action,
        extra={
            "agent_id": agent_id,
            "action": action,
            "status": status,
            "details": safe_details,
        },
    )
