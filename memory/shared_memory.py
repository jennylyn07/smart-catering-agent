"""memory/shared_memory.py

Session-scoped shared memory for the Smart Catering multi-agent pipeline.

This module provides a small, explicit API for storing and retrieving shared
context across agents during one orchestrator run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from utils.logger import log_event


_IMMUTABLE_KEYS = {"dietary_restrictions", "allergies", "budget_php", "event_id", "session_id"}


@dataclass
class SharedMemory:
    """Session-scoped shared memory for one pipeline run."""

    session_id: str
    event_id: str
    _store: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._store.setdefault("session_id", self.session_id)
        self._store.setdefault("event_id", self.event_id)
        self._store.setdefault("negotiation_history", [])
        self._store.setdefault("agent_outputs", {})

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value from shared memory."""

        return self._store.get(key, default)

    def has(self, key: str) -> bool:
        """Return True if a key exists in shared memory."""

        return key in self._store

    def set(self, *, key: str, value: Any, writer_agent_id: str) -> None:
        """Write a key/value pair to shared memory.

        Protected keys are immutable after first write.
        """

        if key in _IMMUTABLE_KEYS and key in self._store:
            raise ValueError(f"SharedMemory key '{key}' is immutable once set")

        self._store[key] = value
        log_event(
            agent_id=writer_agent_id,
            action="shared_memory_write",
            status="success",
            details={"key": key},
        )

    def set_agent_output(self, *, agent_id: str, value: Any, writer_agent_id: str) -> None:
        """Store an agent's output under `agent_outputs[agent_id]`."""

        outputs = self._store.setdefault("agent_outputs", {})
        if not isinstance(outputs, dict):
            raise ValueError("SharedMemory key 'agent_outputs' must be a dict")

        outputs[agent_id] = value
        log_event(
            agent_id=writer_agent_id,
            action="shared_memory_write",
            status="success",
            details={"key": f"agent_outputs.{agent_id}"},
        )

    def append_negotiation_round(self, *, round_data: Dict[str, Any], writer_agent_id: str) -> None:
        """Append a negotiation round record to `negotiation_history`."""

        history = self._store.setdefault("negotiation_history", [])
        if not isinstance(history, list):
            raise ValueError("SharedMemory key 'negotiation_history' must be a list")

        history.append(round_data)
        log_event(
            agent_id=writer_agent_id,
            action="shared_memory_write",
            status="success",
            details={"key": "negotiation_history", "length": len(history)},
        )

    def get_dietary_restrictions(self) -> Optional[Any]:
        """Convenience accessor for `dietary_restrictions`."""

        return self._store.get("dietary_restrictions")

    def get_allergies(self) -> Optional[Any]:
        """Convenience accessor for `allergies`."""

        return self._store.get("allergies")

    def snapshot(self) -> Dict[str, Any]:
        """Return a shallow copy of the current shared memory store."""

        return dict(self._store)
