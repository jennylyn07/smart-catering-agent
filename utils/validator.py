"""utils/validator.py

Provides small, reusable input validation helpers for the Smart Catering system.

These functions are used by the API layer and agents to ensure inputs are
reasonable before business logic runs.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Optional


# Configuration constants (easy to change later without hunting through code)
MIN_GUEST_COUNT = 1
MAX_GUEST_COUNT = 5000

MIN_BUDGET_PHP = 0.0
MAX_BUDGET_PHP = 50_000_000.0

# We accept a simple, unambiguous date format for Day 1.
# Example: "2026-04-18"
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# We keep these lists small for now; we can expand as we build the knowledge base.
ALLOWED_CUISINE_TYPES = {
    "filipino",
    "asian",
    "western",
    "italian",
    "japanese",
    "korean",
    "chinese",
    "indian",
}

ALLOWED_DIETARY_FLAGS = {
    "vegetarian",
    "vegan",
    "halal",
    "kosher",
    "gluten_free",
    "dairy_free",
    "nut_free",
    "low_sodium",
}


def validate_guest_count(guest_count: int) -> int:
    """Validate and return a guest count.

    Args:
        guest_count: Number of guests for the event.

    Returns:
        The same guest_count if valid.

    Raises:
        ValueError: If guest_count is outside the allowed range.
    """

    if not (MIN_GUEST_COUNT <= guest_count <= MAX_GUEST_COUNT):
        raise ValueError(
            f"guest_count must be between {MIN_GUEST_COUNT} and {MAX_GUEST_COUNT}, got {guest_count}"
        )

    return guest_count


def validate_budget_php(budget_php: Optional[float]) -> Optional[float]:
    """Validate a PHP budget.

    Args:
        budget_php: Budget in PHP. None means "no budget provided".

    Returns:
        The same budget if valid.

    Raises:
        ValueError: If the budget is negative or unreasonably large.
    """

    if budget_php is None:
        return None

    if not (MIN_BUDGET_PHP <= budget_php <= MAX_BUDGET_PHP):
        raise ValueError(
            f"budget_php must be between {MIN_BUDGET_PHP} and {MAX_BUDGET_PHP}, got {budget_php}"
        )

    return float(budget_php)


def validate_event_date(event_date: str) -> str:
    """Validate an event date string.

    For now, we require ISO-like "YYYY-MM-DD" to avoid ambiguity.

    Args:
        event_date: Date string.

    Returns:
        The same event_date if valid.

    Raises:
        ValueError: If the date format is invalid or not a real calendar date.
    """

    if not DATE_REGEX.match(event_date):
        raise ValueError('event_date must be in format "YYYY-MM-DD"')

    year_str, month_str, day_str = event_date.split("-")

    # This ensures the date is a real calendar date (e.g., rejects 2026-02-30).
    date(int(year_str), int(month_str), int(day_str))

    return event_date


def normalize_cuisine_type(cuisine: str) -> str:
    """Normalize a cuisine type into a stable, lowercase identifier."""

    return cuisine.strip().lower().replace(" ", "_")


def validate_cuisine_types(cuisine_types: Iterable[str]) -> list[str]:
    """Validate cuisine preference values.

    Args:
        cuisine_types: Iterable of cuisine names.

    Returns:
        A normalized list of cuisine identifiers.

    Raises:
        ValueError: If any cuisine type is not recognized.
    """

    normalized: list[str] = []
    for cuisine in cuisine_types:
        value = normalize_cuisine_type(cuisine)
        if value not in ALLOWED_CUISINE_TYPES:
            raise ValueError(
                f"Unsupported cuisine type: {cuisine}. Allowed: {sorted(ALLOWED_CUISINE_TYPES)}"
            )
        normalized.append(value)

    return normalized


def normalize_dietary_flag(flag: str) -> str:
    """Normalize dietary restriction flags into stable identifiers."""

    return flag.strip().lower().replace(" ", "_")


def validate_dietary_flags(flags: Iterable[str]) -> list[str]:
    """Validate dietary restriction flags.

    Args:
        flags: Iterable of restriction names.

    Returns:
        A normalized list of restriction identifiers.

    Raises:
        ValueError: If any dietary flag is not recognized.
    """

    normalized: list[str] = []
    for flag in flags:
        value = normalize_dietary_flag(flag)
        if value not in ALLOWED_DIETARY_FLAGS:
            raise ValueError(
                f"Unsupported dietary restriction: {flag}. Allowed: {sorted(ALLOWED_DIETARY_FLAGS)}"
            )
        normalized.append(value)

    return normalized
