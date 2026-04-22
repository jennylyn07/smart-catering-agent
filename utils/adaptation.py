"""utils/adaptation.py

Shared types for plan adaptation features.
"""

from __future__ import annotations

from enum import Enum


class AdaptationChangeType(str, Enum):
    """Supported change types for adapting an existing catering plan."""

    GUEST_COUNT_CHANGE = "guest_count_change"
    BUDGET_CHANGE = "budget_change"
    DIETARY_ADDITION = "dietary_addition"
