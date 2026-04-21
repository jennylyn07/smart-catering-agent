
from __future__ import annotations

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
    LogisticsPlan,
    MessageHeader,
    MessageMetadata,
    MessageSignature,
    ProcurementItem,
    ProcurementList,
    PurchaseItem,
    StockItem,
)
from utils.logger import log_event

AGENT_ID = "stock_manager"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wrap_message(*, payload: Any, message_type: str, target_agent: str, session_id: str) -> AgentMessage:
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
    payload = ErrorMessage(error_code=error_code, message=message, agent_id=AGENT_ID, details=details or {})
    return _wrap_message(
        payload=payload,
        message_type="error",
        target_agent="orchestrator",
        session_id=session_id,
    )


def _load_inventory() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "data" / "mock_inventory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    inv = payload.get("inventory")
    if not isinstance(inv, list):
        raise ValueError("mock_inventory.json missing 'inventory' list")
    return inv


def _build_inventory_index(inventory: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
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
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "suppliers.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    suppliers = payload.get("suppliers")
    if not isinstance(suppliers, list):
        return []
    return suppliers


def _supplier_for_ingredient(ingredient: str, suppliers: list[dict[str, Any]]) -> tuple[Optional[str], Optional[int]]:
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


async def run_stock_manager(
    *,
    logistics_plan_message: AgentMessage,
    cost_report_message: AgentMessage,
    session_id: str,
) -> AgentMessage:
    log_event(
        agent_id=AGENT_ID,
        action="build_procurement_list",
        status="started",
        details={"inputs": ["logistics_plan", "cost_report"]},
    )

    try:
        if not isinstance(logistics_plan_message.payload, LogisticsPlan):
            raise ValueError("logistics_plan_message payload must be a LogisticsPlan")
        if not isinstance(cost_report_message.payload, CostReport):
            raise ValueError("cost_report_message payload must be a CostReport")

        logistics_plan: LogisticsPlan = logistics_plan_message.payload
        cost_report: CostReport = cost_report_message.payload

        inventory_rows = _load_inventory()
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

        waste_minimization_notes = (
            "Prioritize early purchase of long lead-time items per logistics critical path. "
            "Buy perishables (meat/vegetables) closer to prep start time to reduce spoilage risk."
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
                "timeline_hint": logistics_plan.prep_start_time,
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
