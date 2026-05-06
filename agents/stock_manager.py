
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import ValidationError

from utils.json_schema import (
    AgentMessage,
    CostReport,
    ErrorMessage,
    EventSpecification,
    LogisticsPlan,
    MessageHeader,
    MessageMetadata,
    MessageSignature,
    ProcurementItem,
    ProcurementList,
    PurchaseItem,
    StockItem,
)
from utils.cosmos_store import query_inventory_from_cosmos
from utils.logger import log_event
from utils.azure_client import create_async_azure_openai_client, get_azure_openai_deployment_name

AGENT_ID = "stock_manager"


def _now_utc() -> datetime:
    """Return the current UTC time.

    Args:
        None

    Returns:
        A timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


def _stable_hash(value: Any) -> str:
    """Compute a stable SHA-256 hash for a JSON-serializable value.

    Args:
        value: Value to hash (Pydantic models should be converted before calling).

    Returns:
        Hex-encoded SHA-256 digest.
    """
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wrap_message(*, payload: Any, message_type: str, target_agent: str, session_id: str) -> AgentMessage:
    """Wrap a payload in the standard AgentMessage envelope.

    Args:
        payload: The message payload model or JSON-serializable object.
        message_type: The message type string for the header.
        target_agent: Downstream consumer agent identifier.
        session_id: Correlation/session identifier for the request.

    Returns:
        A fully populated AgentMessage containing header, payload, metadata, and signature.
    """
    header = MessageHeader(
        message_id=uuid4(),
        agent_id=AGENT_ID,
        target_agent=target_agent,
        timestamp=_now_utc(),
        message_type=message_type,
    )
    metadata = MessageMetadata(confidence_score=0.75)

    signature_payload: Any
    if hasattr(payload, "model_dump"):
        signature_payload = payload.model_dump()
    else:
        signature_payload = payload

    signature = MessageSignature(hash=_stable_hash(signature_payload), session_id=session_id)
    return AgentMessage(header=header, payload=payload, metadata=metadata, signature=signature)


def _error_message(
    *,
    session_id: str,
    error_code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> AgentMessage:
    """Create an error AgentMessage for failures within this agent.

    Args:
        session_id: Correlation/session identifier for the request.
        error_code: Stable error code for the failure class.
        message: Human-readable error message.
        details: Optional structured error details.

    Returns:
        An AgentMessage whose payload is an ErrorMessage.
    """
    payload = ErrorMessage(error_code=error_code, message=message, agent_id=AGENT_ID, details=details or {})
    return _wrap_message(
        payload=payload,
        message_type="error",
        target_agent="orchestrator",
        session_id=session_id,
    )


def _load_inventory() -> list[dict[str, Any]]:
    """Load the mock inventory data from disk.

    Args:
        None

    Returns:
        A list of inventory rows loaded from `data/mock_inventory.json`.
    """
    path = Path(__file__).resolve().parents[1] / "data" / "mock_inventory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    inv = payload.get("inventory")
    if not isinstance(inv, list):
        raise ValueError("mock_inventory.json missing 'inventory' list")
    return inv


def _build_inventory_index(inventory: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build an index for quick lookup of inventory quantities by ingredient.

    Args:
        inventory: Inventory rows loaded from the inventory JSON.

    Returns:
        Mapping of ingredient name (lowercase) to normalized inventory row dict.
    """
    index: dict[str, dict[str, Any]] = {}
    for row in inventory:
        ing = str(row.get("ingredient") or "").strip().lower()
        if not ing:
            continue
        try:
            qty = float(row.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        unit = str(row.get("unit") or "").strip()
        index[ing] = {"ingredient": ing, "quantity": max(qty, 0.0), "unit": unit}
    return index


def _load_suppliers() -> list[dict[str, Any]]:
    """Load supplier data from the suppliers knowledge base.

    Args:
        None

    Returns:
        A list of supplier dicts from `knowledge_base/suppliers.json`.
    """
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "suppliers.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    suppliers = payload.get("suppliers")
    if not isinstance(suppliers, list):
        return []
    return suppliers


def _supplier_for_ingredient(ingredient: str, suppliers: list[dict[str, Any]]) -> tuple[Optional[str], Optional[int]]:
    """Choose a supplier for an ingredient based on minimum lead time.

    Args:
        ingredient: Ingredient name to source.
        suppliers: Supplier dicts loaded from suppliers.json.

    Returns:
        Tuple of (supplier_name, lead_time_days), either value may be None if not found.
    """
    ing = ingredient.strip().lower()
    best_name: Optional[str] = None
    best_lead: Optional[int] = None

    for s in suppliers:
        products = s.get("products") or []
        if not isinstance(products, list):
            continue
        if ing not in {str(p).strip().lower() for p in products}:
            continue

        name = str(s.get("name") or "").strip() or None
        try:
            lead = int(s.get("lead_time_days") or 0)
        except (TypeError, ValueError):
            lead = 0

        if best_lead is None or lead < best_lead:
            best_name = name
            best_lead = lead

    return best_name, best_lead


def _waste_risk(ingredient: str) -> bool:
    """Heuristically determine whether an ingredient is likely to spoil quickly.

    Args:
        ingredient: Ingredient name.

    Returns:
        True if the ingredient is considered perishable; otherwise False.
    """
    # Simple heuristic: fresh meats + vegetables are more perishable.
    perishable_keywords = [
        "chicken",
        "pork",
        "beef",
        "ground pork",
        "tomato",
        "radish",
        "kangkong",
        "eggplant",
        "string beans",
        "bok choy",
        "cabbage",
        "carrot",
        "squash",
        "ginger",
        "garlic",
        "onion",
        "chili",
        "taro leaves",
        "young coconut",
    ]
    ing = ingredient.strip().lower()
    return ing in perishable_keywords


async def _gpt_waste_risk_assessment(
    *,
    waste_risk_items: list[str],
    purchase_items: list[Any],
    event_date: str,
    guest_count: int,
    prep_start_time: Any,
) -> str:
    """Generate event-specific waste risk assessment using GPT-4o.

    Args:
        waste_risk_items: Deterministically identified perishable ingredients.
        purchase_items: Items that need to be purchased (name + quantity).
        event_date: Event date string from EventSpecification.
        guest_count: Number of guests for the event.
        prep_start_time: Prep start datetime from LogisticsPlan.

    Returns:
        Event-specific waste minimization notes string. Falls back to static
        string on any failure.
    """
    _STATIC_FALLBACK = (
        "Prioritize early purchase of long lead-time items per logistics critical path. "
        "Buy perishables (meat/vegetables) closer to prep start time to reduce spoilage risk."
    )

    if not waste_risk_items:
        return _STATIC_FALLBACK

    try:
        client = create_async_azure_openai_client()
        deployment = get_azure_openai_deployment_name()

        purchase_summary = ", ".join(
            f"{p.ingredient} ({p.quantity:.1f} {p.unit})"
            for p in purchase_items
            if p.ingredient in waste_risk_items
        ) or "none identified"

        system_prompt = (
            "You are the Stock Manager agent for a professional catering operation. "
            "Your job is to provide specific, actionable waste minimization guidance "
            "based on the actual event details and ingredients involved.\n\n"
            "PRINCIPLES TO APPLY:\n"
            "- FIFO (First In First Out): older stock must be used before newer purchases\n"
            "- Yield analysis: account for trimming/prep loss (meat ~15-20%, vegetables ~10-15%)\n"
            "- Timing: perishables should arrive as close to prep start as possible\n"
            "- Quantity awareness: larger quantities of perishables = higher spoilage risk\n"
            "- Be specific to the actual ingredients listed — do not give generic advice\n\n"
            "OUTPUT: 2-3 sentences maximum. Mention specific ingredients by name. "
            "Give concrete timing or handling instructions. No bullet points. Plain text only."
        )

        user_prompt = (
            f"Event date: {event_date}\n"
            f"Guest count: {guest_count}\n"
            f"Prep start time: {prep_start_time}\n"
            f"Perishable items to purchase: {purchase_summary}\n\n"
            "Provide specific waste minimization guidance for this event."
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=deployment,
                temperature=0.2,
                max_tokens=150,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            timeout=8.0,
        )

        result = (response.choices[0].message.content or "").strip()
        if not result:
            return _STATIC_FALLBACK
        return result

    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return _STATIC_FALLBACK


async def _gpt_supplier_rationale(
    *,
    purchase_items: list[Any],
    event_date: str,
    total_procurement_cost_php: float,
) -> str:
    """Generate a brief supplier selection rationale using GPT-4o.

    Args:
        purchase_items: PurchaseItem list with suggested_supplier and lead_time_days.
        event_date: Event date string for urgency context.
        total_procurement_cost_php: Total procurement cost for budget context.

    Returns:
        Short supplier rationale string. Falls back to static string on any failure.
    """
    _STATIC_FALLBACK = "Suppliers selected based on shortest lead time to meet event timeline."

    if not purchase_items:
        return _STATIC_FALLBACK

    try:
        client = create_async_azure_openai_client()
        deployment = get_azure_openai_deployment_name()

        supplier_summary = []
        for p in purchase_items:
            if p.suggested_supplier:
                supplier_summary.append(
                    f"{p.ingredient}: {p.suggested_supplier} "
                    f"(lead time {p.lead_time_days} days, "
                    f"est. PHP {p.estimated_cost_php:.2f})"
                )
        if not supplier_summary:
            return _STATIC_FALLBACK

        system_prompt = (
            "You are the Stock Manager agent for a professional catering operation. "
            "Explain in 1-2 sentences why these suppliers were selected for this event, "
            "referencing lead time relative to the event date and the budget context. "
            "Be specific — mention supplier names and ingredients. Plain text only. "
            "No bullet points."
        )

        user_prompt = (
            f"Event date: {event_date}\n"
            f"Total procurement cost: PHP {total_procurement_cost_php:,.2f}\n"
            f"Supplier assignments:\n" + "\n".join(supplier_summary) + "\n\n"
            "Explain the supplier selection rationale for this event."
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=deployment,
                temperature=0.2,
                max_tokens=100,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            timeout=8.0,
        )

        result = (response.choices[0].message.content or "").strip()
        if not result:
            return _STATIC_FALLBACK
        return result

    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return _STATIC_FALLBACK


async def run_stock_manager(
    *,
    logistics_plan_message: Optional[AgentMessage] = None,
    cost_report_message: AgentMessage,
    session_id: str,
    event_date_fallback: Optional[str] = None,
) -> AgentMessage:
    """Generate a ProcurementList by comparing required ingredients to inventory and suppliers.

    Args:
        logistics_plan_message: Optional AgentMessage containing a LogisticsPlan payload.
            When None (parallel execution mode), event_date_fallback is used for timing.
        cost_report_message: AgentMessage containing a CostReport payload.
        session_id: Correlation/session identifier for the request.
        event_date_fallback: ISO date string (YYYY-MM-DD) used for waste timing when
            logistics_plan_message is not provided (parallel execution mode).

    Returns:
        An AgentMessage containing a ProcurementList payload, or an ErrorMessage on failure.
    """
    log_event(
        agent_id=AGENT_ID,
        action="build_procurement_list",
        status="started",
        details={"inputs": ["cost_report"] if logistics_plan_message is None else ["logistics_plan", "cost_report"]},
    )

    try:
        if logistics_plan_message is not None and not isinstance(logistics_plan_message.payload, LogisticsPlan):
            raise ValueError("logistics_plan_message payload must be a LogisticsPlan")
        if not isinstance(cost_report_message.payload, CostReport):
            raise ValueError("cost_report_message payload must be a CostReport")

        logistics_plan: Optional[LogisticsPlan] = (
            logistics_plan_message.payload if logistics_plan_message is not None else None
        )
        cost_report: CostReport = cost_report_message.payload

        # Try Cosmos DB inventory first, fall back to mock file
        cosmos_inventory = await query_inventory_from_cosmos()
        if cosmos_inventory:
            inventory_rows = cosmos_inventory
            log_event(
                agent_id=AGENT_ID,
                action="load_inventory",
                status="success",
                details={
                    "source": "cosmos_db",
                    "item_count": len(inventory_rows),
                },
            )
        else:
            inventory_rows = _load_inventory()
            log_event(
                agent_id=AGENT_ID,
                action="load_inventory",
                status="success",
                details={
                    "source": "mock_file",
                    "item_count": len(inventory_rows),
                },
            )
        inv_index = _build_inventory_index(inventory_rows)
        suppliers = _load_suppliers()

        items_in_stock: list[StockItem] = []
        for row in inventory_rows:
            ingredient = str(row.get("ingredient") or "").strip()
            if not ingredient:
                continue
            try:
                qty = float(row.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            unit = str(row.get("unit") or "").strip()
            items_in_stock.append(StockItem(ingredient=ingredient, quantity=max(qty, 0.0), unit=unit))

        required: dict[str, dict[str, Any]] = {}
        for li in cost_report.line_items:
            ing = li.item.strip().lower()
            if not ing:
                continue
            entry = required.get(ing)
            if entry is None:
                required[ing] = {
                    "ingredient": li.item.strip(),
                    "quantity": float(li.quantity),
                    "unit": li.unit,
                    "unit_price_php": float(li.unit_price_php),
                }
            else:
                entry["quantity"] += float(li.quantity)
                # Keep first seen unit + price; assume cost_report uses consistent units.

        procurement_items: list[ProcurementItem] = []
        purchase_items: list[PurchaseItem] = []
        out_of_stock_alerts: list[str] = []
        waste_risk_items: list[str] = []

        total_procurement_cost = 0.0

        for ing_key, req in sorted(required.items()):
            req_qty = float(req["quantity"])
            unit = str(req["unit"])
            unit_price = float(req["unit_price_php"])

            inv = inv_index.get(ing_key)
            in_stock_qty = float(inv.get("quantity") if inv else 0.0)
            to_buy = max(req_qty - in_stock_qty, 0.0)

            procurement_items.append(
                ProcurementItem(
                    ingredient=req["ingredient"],
                    required_quantity=req_qty,
                    unit=unit,
                    in_stock_quantity=in_stock_qty,
                    to_buy_quantity=to_buy,
                )
            )

            if to_buy > 0:
                supplier_name, lead_days = _supplier_for_ingredient(req["ingredient"], suppliers)
                est_cost = to_buy * unit_price
                total_procurement_cost += est_cost
                purchase_items.append(
                    PurchaseItem(
                        ingredient=req["ingredient"],
                        quantity=to_buy,
                        unit=unit,
                        estimated_cost_php=est_cost,
                        suggested_supplier=supplier_name,
                        lead_time_days=lead_days,
                    )
                )

            if in_stock_qty <= 0 and req_qty > 0:
                out_of_stock_alerts.append(req["ingredient"])

            # Waste risk if we have lots already OR we're buying a lot of perishables
            if _waste_risk(req["ingredient"]) and (in_stock_qty > 0 or to_buy > 0):
                waste_risk_items.append(req["ingredient"])

        # Use logistics plan critical path to set preferred suppliers ordering (simple heuristic)
        preferred_suppliers: list[str] = []
        for p in purchase_items:
            if p.suggested_supplier and p.suggested_supplier not in preferred_suppliers:
                preferred_suppliers.append(p.suggested_supplier)

        # Derive event date for waste timing.
        # Prefer the logistics plan's prep_start_time; fall back to event_date_fallback
        # when running in parallel mode (logistics_plan not yet available).
        if logistics_plan is not None:
            event_date = str(logistics_plan.prep_start_time)[:10]
            prep_start_time_for_gpt: Any = logistics_plan.prep_start_time
        else:
            event_date = event_date_fallback or str(datetime.now(timezone.utc).date())
            # Approximate 6 AM prep start when logistics plan is unavailable
            prep_start_time_for_gpt = f"{event_date}T06:00:00+08:00"

        guest_count_proxy = len(cost_report.line_items)

        waste_minimization_notes, supplier_rationale = await asyncio.gather(
            _gpt_waste_risk_assessment(
                waste_risk_items=sorted(set(waste_risk_items)),
                purchase_items=purchase_items,
                event_date=event_date,
                guest_count=guest_count_proxy,
                prep_start_time=prep_start_time_for_gpt,
            ),
            _gpt_supplier_rationale(
                purchase_items=purchase_items,
                event_date=event_date,
                total_procurement_cost_php=round(total_procurement_cost, 2),
            ),
        )

        procurement = ProcurementList(
            event_id=cost_report.event_id,
            items_in_stock=items_in_stock,
            items_to_purchase=purchase_items,
            out_of_stock_alerts=sorted(set(out_of_stock_alerts)),
            waste_risk_items=sorted(set(waste_risk_items)),
            total_procurement_cost_php=round(total_procurement_cost, 2),
            items=procurement_items,
            preferred_suppliers=preferred_suppliers,
            waste_minimization_notes=waste_minimization_notes,
        )

        msg = _wrap_message(
            payload=procurement,
            message_type="procurement_list",
            target_agent="orchestrator",
            session_id=session_id,
        )

        log_event(
            agent_id=AGENT_ID,
            action="build_procurement_list",
            status="success",
            details={
                "event_id": procurement.event_id,
                "purchase_count": len(procurement.items_to_purchase),
                "out_of_stock_count": len(procurement.out_of_stock_alerts),
                "total_procurement_cost_php": procurement.total_procurement_cost_php,
                "timeline_hint": prep_start_time_for_gpt,
                "stock_manager_ai_reasoning": supplier_rationale,
            },
        )

        return msg

    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        log_event(
            agent_id=AGENT_ID,
            action="build_procurement_list",
            status="error",
            details={"error": str(exc)},
        )
        return _error_message(
            session_id=session_id,
            error_code="PROCUREMENT_LIST_ERROR",
            message="Failed to generate procurement list.",
            details={"error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id=AGENT_ID,
            action="build_procurement_list",
            status="error",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
        return _error_message(
            session_id=session_id,
            error_code="PROCUREMENT_UNEXPECTED_ERROR",
            message="Unexpected error while generating procurement list.",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
