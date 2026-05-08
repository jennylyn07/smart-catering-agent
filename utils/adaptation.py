"""utils/adaptation.py

Shared types for plan adaptation features.

AdaptationChangeType defines every supported in-place change to an existing
FinalPlan. Each type maps to a specific set of agents that re-run:

  LIGHTWEIGHT (Logistics + Stock Manager only — menu and cost unchanged):
    DATE_CHANGE, EVENT_TIME_CHANGE, NOTES_CHANGE, LOCATION_CHANGE

  FULL HEAD-CHEF RE-RUN (menu changes → Accountant → Logistics → Stock):
    GUEST_COUNT_CHANGE, DIETARY_ADDITION, ALLERGY_ADDITION

  ACCOUNTANT-ONLY RE-RUN (menu unchanged, budget re-evaluated):
    BUDGET_CHANGE
"""

from __future__ import annotations

from enum import Enum


class AdaptationChangeType(str, Enum):
    """Supported change types for adapting an existing catering plan."""

    # Existing
    GUEST_COUNT_CHANGE = "guest_count_change"
    BUDGET_CHANGE = "budget_change"
    DIETARY_ADDITION = "dietary_addition"

    # New — lightweight (Logistics + Stock only)
    DATE_CHANGE = "date_change"
    EVENT_TIME_CHANGE = "event_time_change"
    NOTES_CHANGE = "notes_change"
    LOCATION_CHANGE = "location_change"

    # New — full Head Chef re-run
    ALLERGY_ADDITION = "allergy_addition"
