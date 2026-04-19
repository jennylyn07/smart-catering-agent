"""api/auth.py

Provides API key authentication for the FastAPI API layer.

This module checks the incoming request header X-API-Key and compares it to the
expected API key loaded from the environment (.env via python-dotenv).

If the key is missing or incorrect, requests are rejected.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status


def _load_env() -> None:
    """Load environment variables from a local .env file if present."""

    load_dotenv(override=False)


def get_expected_api_key() -> str:
    """Return the expected API key loaded from the environment.

    Returns:
        The expected API key string.

    Raises:
        RuntimeError: If API_KEY is missing.
    """

    _load_env()
    value = os.getenv("API_KEY")
    if value is None or not value.strip():
        raise RuntimeError("Missing required environment variable: API_KEY")
    return value.strip()


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    """FastAPI dependency that enforces API key authentication.

    Args:
        x_api_key: The API key value from the X-API-Key header.

    Returns:
        None

    Raises:
        HTTPException: If the key is missing or invalid.
    """

    expected = get_expected_api_key()

    if x_api_key is None or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
