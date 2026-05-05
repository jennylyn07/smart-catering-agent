"""api/routes.py

Defines FastAPI routes for the Smart Catering API.

For Day 2, this module exposes a single endpoint used to submit a catering
order. The response is a placeholder (agents are not wired yet).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth import require_api_key
from api.models import CateringAdaptRequest, CateringMultiOrderRequest, CateringOrderRequest, CateringRawTextOrderRequest
from orchestrator.engine import adapt_from_existing_plan, run_orchestration
from utils.cosmos_store import (
    append_adaptation_event, 
    persist_final_plan, 
    read_order_document,
    get_recent_orders,
)
from utils.json_schema import AgentMessage
from utils.logger import log_event


router = APIRouter(prefix="/api/v1")


def _to_raw_customer_request(order: CateringOrderRequest) -> str:
    return "\n".join(
        [
            f"Event name: {order.event_name or ''}".strip(),
            f"Event date: {order.event_date}",
            f"Location: {order.location}",
            f"Guests: {order.guest_count}",
            f"Budget PHP: {order.budget_php if order.budget_php is not None else ''}".strip(),
            f"Cuisine preferences: {', '.join(order.cuisine_preferences)}".strip(),
            f"Dietary restrictions: {', '.join(order.dietary_restrictions)}".strip(),
            f"Allergies: {', '.join(order.allergies)}".strip(),
            f"Notes: {order.notes or ''}".strip(),
        ]
    ).strip()


@router.post(
    "/catering/order",
    response_model=AgentMessage,
    tags=["catering"],
)
async def create_catering_order(
    request: CateringRawTextOrderRequest,
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
            "text_length": len(request.raw_customer_text),
        },
    )

    result = await run_orchestration(raw_customer_request=request.raw_customer_text)

    if result.header.message_type == "final_plan" and hasattr(result.payload, "model_dump"):
        order_id = str(getattr(result.payload, "event_id", "")).strip()
        if order_id:
            log_event(
                agent_id="api",
                action="cosmos_warning",
                status="started",
                details={"order_id": order_id},
            )
            await persist_final_plan(order_id=order_id, final_plan=result.payload.model_dump())

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


@router.get(
    "/catering/orders",
    tags=["catering"],
)
async def list_catering_orders(
    _: None = Depends(require_api_key),
) -> dict:
    """Return recent catering orders from Cosmos DB for history display."""
    log_event(
        agent_id="api",
        action="list_catering_orders",
        status="received",
        details={},
    )
    orders = await get_recent_orders(limit=20)
    log_event(
        agent_id="api",
        action="list_catering_orders",
        status="completed",
        details={"order_count": len(orders)},
    )
    return {"orders": orders}


@router.post(
    "/catering/adapt",
    response_model=AgentMessage,
    tags=["catering"],
)
async def adapt_catering_order(
    request: CateringAdaptRequest,
    _: None = Depends(require_api_key),
) -> AgentMessage:
    """Adapt an existing catering order by re-running only affected agents."""

    log_event(
        agent_id="api",
        action="adapt_catering_order",
        status="received",
        details={
            "order_id": request.order_id,
            "change_type": str(request.change_type),
        },
    )

    # WARNING: The following Cosmos DB operation will make Azure network calls at runtime.
    try:
        doc = await read_order_document(order_id=request.order_id)
    except Exception as exc:  # noqa: BLE001
        from datetime import datetime, timezone
        from uuid import uuid4

        from utils.json_schema import ErrorMessage, MessageHeader, MessageMetadata, MessageSignature

        log_event(
            agent_id="api",
            action="adapt_catering_order",
            status="error",
            details={"error": str(exc), "order_id": request.order_id, "error_type": type(exc).__name__},
        )
        return AgentMessage(
            header=MessageHeader(
                message_id=uuid4(),
                agent_id="api",
                target_agent="client",
                timestamp=datetime.now(timezone.utc),
                message_type="error",
            ),
            payload=ErrorMessage(
                error_code="COSMOS_READ_ERROR",
                message="Failed to load existing order from Cosmos DB.",
                agent_id="api",
                details={"error": str(exc), "error_type": type(exc).__name__},
            ),
            metadata=MessageMetadata(confidence_score=0.5),
            signature=MessageSignature(hash="", session_id=""),
        )

    candidate = doc.get("final_plan") if isinstance(doc, dict) else None
    if candidate is None and isinstance(doc, dict):
        candidate = doc

    try:
        from datetime import datetime, timezone
        from uuid import uuid4

        from utils.json_schema import FinalPlan, MessageHeader, MessageMetadata, MessageSignature

        existing_plan = FinalPlan.model_validate(candidate)
    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id="api",
            action="adapt_catering_order",
            status="error",
            details={"error": str(exc), "order_id": request.order_id, "error_type": type(exc).__name__},
        )
        return AgentMessage(
            header=MessageHeader(
                message_id=uuid4(),
                agent_id="api",
                target_agent="client",
                timestamp=datetime.now(timezone.utc),
                message_type="error",
            ),
            payload=ErrorMessage(
                error_code="INVALID_STORED_PLAN",
                message="Stored plan is missing or invalid.",
                agent_id="api",
                details={"error": str(exc), "error_type": type(exc).__name__},
            ),
            metadata=MessageMetadata(confidence_score=0.5),
            signature=MessageSignature(hash="", session_id=""),
        )

    result = await adapt_from_existing_plan(
        existing_plan=existing_plan,
        change_type=request.change_type,
        new_value=request.new_value,
        order_id=request.order_id,
    )

    if result.header.message_type == "final_plan" and hasattr(result.payload, "model_dump"):
        from datetime import datetime, timezone

        log_event(
            agent_id="api",
            action="cosmos_warning",
            status="started",
            details={"order_id": request.order_id},
        )
        await append_adaptation_event(
            order_id=request.order_id,
            adaptation_event={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "change_type": str(request.change_type),
                "new_value": request.new_value,
                "session_id": result.signature.session_id,
            },
            updated_final_plan=result.payload.model_dump(),
        )

    log_event(
        agent_id="api",
        action="adapt_catering_order",
        status="completed",
        details={
            "order_id": request.order_id,
            "orchestrator_message_type": result.header.message_type,
            "session_id": result.signature.session_id,
        },
    )

    return result


@router.post(
    "/catering/multi-order",
    response_model=AgentMessage,
    tags=["catering"],
)
async def create_multi_catering_order(
    request: CateringMultiOrderRequest,
    _: None = Depends(require_api_key),
) -> AgentMessage:
    """Run up to 3 catering orders through the pipeline and optimize shared procurement."""

    from datetime import datetime, timezone
    from uuid import uuid4

    from utils.json_schema import (
        ErrorMessage,
        MessageHeader,
        MessageMetadata,
        MessageSignature,
        MultiEventPlan,
        ProcurementOptimizationSummary,
        PurchaseItem,
    )

    log_event(
        agent_id="api",
        action="create_multi_catering_order",
        status="received",
        details={"order_count": len(request.orders)},
    )

    if not request.acknowledge_azure_openai:
        # WARNING GATE: run_orchestration may invoke Azure OpenAI via Concierge.
        return AgentMessage(
            header=MessageHeader(
                message_id=uuid4(),
                agent_id="api",
                target_agent="client",
                timestamp=datetime.now(timezone.utc),
                message_type="error",
            ),
            payload=ErrorMessage(
                error_code="AZURE_OPENAI_ACK_REQUIRED",
                message=(
                    "This endpoint may trigger Azure OpenAI calls (via Concierge). "
                    "Resend with acknowledge_azure_openai=true to proceed."
                ),
                agent_id="api",
                details={"order_count": len(request.orders)},
            ),
            metadata=MessageMetadata(confidence_score=0.5),
            signature=MessageSignature(hash="", session_id=""),
        )

    log_event(
        agent_id="api",
        action="azure_openai_warning",
        status="acknowledged",
        details={"order_count": len(request.orders)},
    )

    plans = []
    for order in request.orders:
        raw_customer_request = _to_raw_customer_request(order)
        msg = await run_orchestration(raw_customer_request=raw_customer_request)
        if msg.header.message_type == "error":
            return msg
        plans.append(msg.payload)

    totals_by_ingredient: dict[tuple[str, str], dict[str, float]] = {}
    appearances: dict[tuple[str, str], int] = {}
    original_total = 0.0

    for plan in plans:
        original_total += float(plan.procurement_list.total_procurement_cost_php)
        for item in plan.procurement_list.items_to_purchase:
            key = (str(item.ingredient).strip().lower(), str(item.unit).strip().lower())
            bucket = totals_by_ingredient.setdefault(key, {"qty": 0.0, "cost": 0.0})
            bucket["qty"] += float(item.quantity)
            bucket["cost"] += float(item.estimated_cost_php)
            appearances[key] = appearances.get(key, 0) + 1

    shared_keys = [k for k, count in appearances.items() if count >= 2]
    shared_ingredients = [k[0] for k in shared_keys]

    optimized_shared: list[PurchaseItem] = []
    optimized_shared_total = 0.0
    for key in shared_keys:
        ingredient, unit = key
        qty = totals_by_ingredient[key]["qty"]
        cost = totals_by_ingredient[key]["cost"]
        discounted = round(cost * 0.95, 2)
        optimized_shared_total += discounted
        optimized_shared.append(
            PurchaseItem(
                ingredient=ingredient,
                quantity=qty,
                unit=unit,
                estimated_cost_php=discounted,
                suggested_supplier=None,
                lead_time_days=None,
            )
        )

    non_shared_total = 0.0
    for key, bucket in totals_by_ingredient.items():
        if key in shared_keys:
            continue
        non_shared_total += bucket["cost"]

    optimized_total = round(optimized_shared_total + non_shared_total, 2)
    savings = max(0.0, round(original_total - optimized_total, 2))

    multi_payload = MultiEventPlan(
        plans=plans,
        optimized_shared_procurement=optimized_shared,
        procurement_optimization_summary=ProcurementOptimizationSummary(
            shared_ingredients=sorted(set(shared_ingredients)),
            original_total_procurement_cost_php=round(original_total, 2),
            optimized_total_procurement_cost_php=optimized_total,
            estimated_savings_php=savings,
            notes="Bulk discount heuristic applied to ingredients shared across 2+ events.",
        ),
    )

    result = AgentMessage(
        header=MessageHeader(
            message_id=uuid4(),
            agent_id="api",
            target_agent="client",
            timestamp=datetime.now(timezone.utc),
            message_type="multi_event_plan",
        ),
        payload=multi_payload,
        metadata=MessageMetadata(confidence_score=0.75),
        signature=MessageSignature(hash="", session_id=""),
    )

    log_event(
        agent_id="api",
        action="create_multi_catering_order",
        status="completed",
        details={
            "order_count": len(request.orders),
            "shared_ingredient_count": len(multi_payload.procurement_optimization_summary.shared_ingredients),
            "estimated_savings_php": multi_payload.procurement_optimization_summary.estimated_savings_php,
        },
    )

    return result
