"""api/routes.py

Defines FastAPI routes for the Smart Catering API.

For Day 2, this module exposes a single endpoint used to submit a catering
order. The response is a placeholder (agents are not wired yet).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth import require_api_key
from api.models import CateringOrderRequest
from orchestrator.engine import run_orchestration
from utils.json_schema import AgentMessage
from utils.logger import log_event


router = APIRouter(prefix="/api/v1")


@router.post(
    "/catering/order",
    response_model=AgentMessage,
    tags=["catering"],
)
async def create_catering_order(
    request: CateringOrderRequest,
    _: None = Depends(require_api_key),
) -> AgentMessage:
    """Create a catering order and run the full orchestration pipeline.

    Args:
        request: Validated incoming order request body.
        _: Authentication dependency result (unused).

    Returns:
        An AgentMessage containing either a FinalPlan payload or an ErrorMessage payload.
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

    raw_customer_request = "\n".join(
        [
            f"Event name: {request.event_name or ''}".strip(),
            f"Event date: {request.event_date}",
            f"Location: {request.location}",
            f"Guests: {request.guest_count}",
            f"Budget PHP: {request.budget_php if request.budget_php is not None else ''}".strip(),
            f"Cuisine preferences: {', '.join(request.cuisine_preferences)}".strip(),
            f"Dietary restrictions: {', '.join(request.dietary_restrictions)}".strip(),
            f"Allergies: {', '.join(request.allergies)}".strip(),
            f"Notes: {request.notes or ''}".strip(),
        ]
    ).strip()

    result = await run_orchestration(raw_customer_request=raw_customer_request)

    log_event(
        agent_id="api",
        action="create_catering_order",
        status="completed",
        details={
            "orchestrator_message_type": result.header.message_type,
            "session_id": result.signature.session_id,
        },
    )

    return result
