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
    AlternativeRecommendation,
    CostLineItem,
    CostReport,
    DishCost,
    ErrorMessage,
    EventSpecification,
    MenuPlan,
    MessageHeader,
    MessageMetadata,
    MessageSignature,
)
from utils.logger import log_event

AGENT_ID = "accountant"


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
    metadata = MessageMetadata(confidence_score=0.8)

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


def _load_pricing() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "pricing.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("pricing.json missing 'items' list")
    return items


def _load_recipes() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "recipes.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    recipes = payload.get("recipes")
    if not isinstance(recipes, list):
        raise ValueError("recipes.json missing 'recipes' list")
    return recipes


def _pricing_lookup(items: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    lookup: dict[tuple[str, str], float] = {}
    for row in items:
        ingredient = str(row.get("ingredient") or "").strip().lower()
        unit = str(row.get("unit") or "").strip()
        price = row.get("price_php")
        if not ingredient or not unit:
            continue
        if price is None:
            continue
        lookup[(ingredient, unit)] = float(price)
    return lookup


def _find_recipe_by_name(recipes: list[dict[str, Any]], dish_name: str) -> Optional[dict[str, Any]]:
    target = dish_name.strip().lower()
    for r in recipes:
        if str(r.get("name") or "").strip().lower() == target:
            return r
    return None


def _ingredient_unit_price(
    *, pricing: dict[tuple[str, str], float], ingredient: str, unit: str
) -> Optional[float]:
    key = (ingredient.strip().lower(), unit.strip())
    return pricing.get(key)


def _estimate_scale_factor(*, servings: int) -> float:
    base_servings = 50
    return max(1.0, float(servings) / float(base_servings))


def _suggest_alternative(
    *, pricing: list[dict[str, Any]], ingredient: str, unit: str
) -> Optional[AlternativeRecommendation]:
    candidates = [
        r
        for r in pricing
        if str(r.get("unit") or "").strip() == unit
        and str(r.get("ingredient") or "").strip().lower() != ingredient.strip().lower()
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda r: float(r.get("price_php") or 0))
    recommended = candidates[0]
    return AlternativeRecommendation(
        item=ingredient,
        recommended_item=str(recommended.get("ingredient")),
        reason="Lower unit price alternative from pricing knowledge base.",
    )


async def run_accountant(
    *,
    menu_plan_message: AgentMessage,
    event_spec: EventSpecification,
    session_id: str,
) -> AgentMessage:
    log_event(
        agent_id=AGENT_ID,
        action="calculate_cost_report",
        status="started",
        details={
            "event_id": event_spec.event_id,
            "budget_php": event_spec.budget_php,
        },
    )

    try:
        if not isinstance(menu_plan_message.payload, MenuPlan):
            raise ValueError("menu_plan_message payload must be a MenuPlan")

        menu_plan: MenuPlan = menu_plan_message.payload
        pricing_items = _load_pricing()
        recipes = _load_recipes()
        pricing_map = _pricing_lookup(pricing_items)

        line_items: list[CostLineItem] = []
        dish_costs: list[DishCost] = []

        for dish in menu_plan.menu_items:
            recipe = _find_recipe_by_name(recipes, dish.name)
            if recipe is None:
                continue

            scale = _estimate_scale_factor(servings=dish.servings)
            dish_total = 0.0

            for ing in recipe.get("ingredients") or []:
                ing_name = str(ing.get("name") or "").strip()
                qty = float(ing.get("quantity") or 0)
                unit = str(ing.get("unit") or "").strip()
                if not ing_name or not unit:
                    continue

                unit_price = _ingredient_unit_price(
                    pricing=pricing_map,
                    ingredient=ing_name,
                    unit=unit,
                )
                if unit_price is None:
                    continue

                scaled_qty = qty * scale
                subtotal = scaled_qty * unit_price
                dish_total += subtotal

                line_items.append(
                    CostLineItem(
                        item=ing_name,
                        quantity=scaled_qty,
                        unit=unit,
                        unit_price_php=unit_price,
                        subtotal_php=subtotal,
                    )
                )

            dish_costs.append(DishCost(dish_name=dish.name, cost_php=dish_total))

        total_cost = sum(d.cost_php for d in dish_costs)
        budget = event_spec.budget_php

        is_within_budget: Optional[bool]
        over_budget_by = 0.0
        if budget is None:
            is_within_budget = None
        else:
            is_within_budget = total_cost <= budget
            over_budget_by = max(0.0, total_cost - budget)

        flagged_items: list[str] = []
        recommended: list[AlternativeRecommendation] = []

        if is_within_budget is False:
            by_subtotal = sorted(line_items, key=lambda li: li.subtotal_php, reverse=True)
            top = by_subtotal[:5]
            flagged_items = [li.item for li in top]

            for li in top:
                alt = _suggest_alternative(pricing=pricing_items, ingredient=li.item, unit=li.unit)
                if alt is not None:
                    recommended.append(alt)

        report = CostReport(
            event_id=event_spec.event_id,
            cost_per_dish=dish_costs,
            total_cost_php=total_cost,
            budget_php=budget,
            within_budget=is_within_budget,
            is_within_budget=is_within_budget,
            over_budget_by_php=over_budget_by,
            flagged_items=flagged_items,
            recommended_alternatives=recommended,
            line_items=line_items,
            notes=None,
        )

        msg = _wrap_message(
            payload=report,
            message_type="cost_report",
            target_agent="logistics",
            session_id=session_id,
        )

        log_event(
            agent_id=AGENT_ID,
            action="calculate_cost_report",
            status="success",
            details={
                "event_id": report.event_id,
                "total_cost_php": report.total_cost_php,
                "budget_php": report.budget_php,
                "is_within_budget": report.is_within_budget,
                "over_budget_by_php": report.over_budget_by_php,
            },
        )

        return msg

    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        log_event(
            agent_id=AGENT_ID,
            action="calculate_cost_report",
            status="error",
            details={"error": str(exc)},
        )
        return _error_message(
            session_id=session_id,
            error_code="ACCOUNTANT_COST_ERROR",
            message="Failed to calculate cost report.",
            details={"error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id=AGENT_ID,
            action="calculate_cost_report",
            status="error",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
        return _error_message(
            session_id=session_id,
            error_code="ACCOUNTANT_UNEXPECTED_ERROR",
            message="Unexpected error while calculating cost report.",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
