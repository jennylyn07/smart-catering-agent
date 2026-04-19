"""api/routes.py

Defines FastAPI routes for the Smart Catering API.

For Day 2, this module exposes a single endpoint used to submit a catering
order. The response is a placeholder (agents are not wired yet).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends

from api.auth import require_api_key
from api.models import CateringOrderRequest, CateringOrderResponse, OrderStatus
from utils.logger import log_event


router = APIRouter(prefix="/api/v1")


@router.post(
    "/catering/order",
    response_model=CateringOrderResponse,
    tags=["catering"],
)
async def create_catering_order(
    request: CateringOrderRequest,
    _: None = Depends(require_api_key),
) -> CateringOrderResponse:
    """Create a catering order (placeholder implementation).

    Args:
        request: Validated incoming order request body.
        _: Authentication dependency result (unused).

    Returns:
        A placeholder CateringOrderResponse.
    """

    log_event(
        agent_id="api",
        action="create_catering_order",
        status="received",
        details={
            "event_date": request.event_date,
            "location": request.location,
            "guest_count": request.guest_count,
            "budget_php": request.budget_php,
        },
    )

    order_id = str(uuid4())

    return CateringOrderResponse(
        order_id=order_id,
        status=OrderStatus.PENDING,
        message="Order received. Agents will process this in a future step.",
        received_request=request,
    )
