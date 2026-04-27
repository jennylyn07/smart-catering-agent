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


def _load_pricing() -> list[dict[str, Any]]:
    """Load the ingredient pricing knowledge base from disk.

    Args:
        None

    Returns:
        A list of pricing rows loaded from `knowledge_base/pricing.json`.
    """
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "pricing.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("pricing.json missing 'items' list")
    return items


def _load_recipes() -> list[dict[str, Any]]:
    """Load the recipes knowledge base from disk.

    Args:
        None

    Returns:
        A list of recipe dicts loaded from `knowledge_base/recipes.json`.
    """
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "recipes.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    recipes = payload.get("recipes")
    if not isinstance(recipes, list):
        raise ValueError("recipes.json missing 'recipes' list")
    return recipes


def _pricing_lookup(items: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    """Build a lookup table mapping (ingredient, unit) to unit price.

    Args:
        items: Pricing rows loaded from pricing.json.

    Returns:
        Dictionary keyed by (ingredient_lower, unit) with float price values.
    """
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
    """Find a recipe dict by its dish name (case-insensitive).

    Args:
        recipes: List of recipe dicts.
        dish_name: Name of the dish to look up.

    Returns:
        The matching recipe dict if found; otherwise None.
    """
    target = dish_name.strip().lower()
    for r in recipes:
        if str(r.get("name") or "").strip().lower() == target:
            return r
    return None


def _ingredient_unit_price(
    *, pricing: dict[tuple[str, str], float], ingredient: str, unit: str
) -> Optional[float]:
    """Look up the unit price for a specific ingredient and unit.

    Args:
        pricing: Pricing lookup table keyed by (ingredient, unit).
        ingredient: Ingredient name.
        unit: Unit string (e.g., "kg", "L").

    Returns:
        Unit price if found; otherwise None.
    """
    key = (ingredient.strip().lower(), unit.strip())
    return pricing.get(key)


def _estimate_scale_factor(*, servings: int) -> float:
    """Estimate a recipe scaling factor relative to a fixed base serving size.

    Args:
        servings: Target number of servings.

    Returns:
        Scale factor (>= 1.0) used to multiply base ingredient quantities.
    """
    base_servings = 8
    return max(1.0, float(servings) / float(base_servings))


def _suggest_alternative(
    *, pricing: list[dict[str, Any]], ingredient: str, unit: str
) -> Optional[AlternativeRecommendation]:
    """Suggest a cheaper alternative ingredient with the same unit.

    Args:
        pricing: Raw pricing rows loaded from pricing.json.
        ingredient: Ingredient name to replace.
        unit: Unit string that must match.

    Returns:
        An AlternativeRecommendation if a lower-priced candidate exists; otherwise None.
    """
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
    """Calculate a CostReport for a menu plan using local pricing and recipes data.

    Args:
        menu_plan_message: AgentMessage containing a MenuPlan payload.
        event_spec: Normalized event specification including guest count and budget.
        session_id: Correlation/session identifier for the request.

    Returns:
        An AgentMessage containing a CostReport payload, or an ErrorMessage on failure.
    """
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

        ingredients_cost = sum(d.cost_php for d in dish_costs)

        fixed_overhead = 2500.0 + 1500.0 + 800.0
        labor_cost = 150.0 * float(event_spec.guest_count)
        total_cost = ingredients_cost + labor_cost + fixed_overhead
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
            # Flag expensive dishes (so Head Chef can remove them by name during negotiation).
            by_dish_cost = sorted(dish_costs, key=lambda d: d.cost_php, reverse=True)
            flagged_items = [d.dish_name for d in by_dish_cost[:2]]

            # Keep ingredient-level alternative hints to support future improvements.
            by_subtotal = sorted(line_items, key=lambda li: li.subtotal_php, reverse=True)
            top = by_subtotal[:5]
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
            notes=(
                "Includes fixed overhead (setup_fee=2500, equipment_rental=1500, delivery=800) "
                "and labor cost (150 per guest) on top of ingredient costs."
            ),
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
