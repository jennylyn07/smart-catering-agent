"""api/models.py

Defines Pydantic models for the FastAPI API layer.

These models are used to validate incoming requests and to standardize outgoing
responses so the API is consistent and predictable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(str, Enum):
    """Allowed states for a catering order."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class CateringOrderRequest(BaseModel):
    """Incoming request body for creating a catering order."""

    model_config = ConfigDict(extra="forbid")

    customer_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    event_name: Optional[str] = None
    event_date: str = Field(
        ..., description='Event date in "YYYY-MM-DD" format (validated in later steps).'
    )
    location: str

    guest_count: int = Field(..., ge=1)
    budget_php: Optional[float] = Field(default=None, ge=0)

    cuisine_preferences: List[str] = Field(default_factory=list)
    dietary_restrictions: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)

    notes: Optional[str] = None


class CateringOrderResponse(BaseModel):
    """API response returned after an order is accepted for processing."""

    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: OrderStatus
    message: str
    received_request: Optional[CateringOrderRequest] = None


class ErrorResponse(BaseModel):
    """Standard error response shape for API failures."""

    model_config = ConfigDict(extra="forbid")

    error: str
    details: Dict[str, Any] = Field(default_factory=dict)
