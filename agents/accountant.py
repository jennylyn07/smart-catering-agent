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
from utils.azure_client import (
    create_async_azure_openai_client,
    get_azure_openai_deployment_name,
    create_search_client,
    try_load_settings,
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


async def _gpt_flagged_analysis(
    dish_with_pct: list[dict],
    gap: float,
    gap_pct: float,
    top_driver_name: str,
    single_item_dominant: bool,
    total_cost: float,
    budget: float,
    event_spec: EventSpecification,
    dish_costs: list,
) -> list[str]:
    """
    GPT receives pre-computed cost analysis and reasons about which dishes
    to flag for revision. Math is done in code before this call.
    GPT judges: reformulate before remove, minimum flagging, event context.
    Falls back to top-2 rule on any failure.
    """
    try:
        client = create_async_azure_openai_client()
        deployment = get_azure_openai_deployment_name()

        overage_pattern = (
            f"{top_driver_name} is driving more than 50% of the gap (single item dominant)"
            if single_item_dominant
            else "overage is spread across multiple dishes (no single dominant driver)"
        )

        dish_lines = "\n".join(
            f"- {d['name']}: PHP {d['cost_php']} ({d['pct_of_total']}% of total cost)"
            for d in dish_with_pct
        )

        system_prompt = """You are a professional catering cost controller with deep expertise in food cost management and menu engineering.

You will receive a pre-computed cost analysis. Do not recalculate — the numbers are given to you as facts.
Your job is to reason: given this cost profile and this specific event context, which dishes should be flagged for revision?

Before flagging any dish, always consider reformulation first in this order:
1. Protein Down-Tiering — can the expensive protein be swapped for a high-flavor lower-cost alternative?
2. Portion Re-balancing — can the protein portion be reduced by 1oz while increasing a low-cost sophisticated starch?
3. Service Style — if the gap is large, note whether a buffet style could reduce labor cost (note only, do not flag a dish for this)
4. Only if reformulation cannot close the gap — flag the dish for replacement

Rules:
- Flag the MINIMUM number of dishes necessary to close the gap
- Never flag a dish that directly serves a hard dietary restriction for this event
- Anchor dishes (high-popularity proteins, cultural centerpieces for this event type) should be reformulated not removed
- Consider the event type and guest profile when judging dish importance

Respond with a JSON object only. No explanation, no markdown, no preamble.
Format: {"flagged_dishes": ["dish name 1"], "reformulation_notes": "brief reasoning"}"""

        cuisine = ", ".join(event_spec.cuisine_preferences or []) if event_spec.cuisine_preferences else "(none specified)"
        event_name = event_spec.event_name or "(not specified)"

        user_prompt = f"""EVENT CONTEXT:
Event name / type: {event_name}
Guests: {event_spec.guest_count}
Cuisine preferences: {cuisine}
Hard dietary restrictions: {event_spec.dietary_restrictions}

PRE-COMPUTED COST ANALYSIS (do not recalculate — trust these numbers):
Budget: PHP {budget:.2f}
Total cost: PHP {total_cost:.2f}
Over budget by: PHP {gap:.2f} ({gap_pct}% over budget)
Overage pattern: {overage_pattern}

DISH COST BREAKDOWN:
{dish_lines}

Based on this analysis and the event context, which dishes should be flagged for revision?
Try reformulation before removal. Return only the JSON object."""

        response = await client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        flagged = parsed.get("flagged_dishes", [])

        # Validate — flagged names must match actual dish names
        valid_names = {d.dish_name for d in dish_costs}
        flagged = [name for name in flagged if name in valid_names]

        # Safety: if GPT returns empty list while over budget, fall back
        if not flagged:
            raise ValueError("GPT returned empty flagged list while over budget")

        return flagged

    except Exception as e:
        import logging

        logging.warning(f"GPT flagged analysis failed, falling back to top-2: {e}")
        by_dish_cost = sorted(dish_costs, key=lambda d: d.cost_php, reverse=True)
        return [d.dish_name for d in by_dish_cost[:2]]


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


async def _load_candidate_pricing() -> list[dict[str, Any]]:
    """Load ingredient pricing via Azure AI Search RAG. Falls back to local _load_pricing() on any failure."""
    try:
        settings = try_load_settings()
        if not settings:
            return _load_pricing()
        search_client = create_search_client(index_name="catering-knowledge-base")
        async with search_client:
            results = await search_client.search(
                search_text="*",
                filter="category eq 'pricing'",
                select=["content"],
                top=5,
            )
            combined_content = ""
            async for doc in results:
                combined_content += doc.get("content", "") + "\n"
        if not combined_content.strip():
            return _load_pricing()
        # Parse pricing from content — extract JSON block if present
        import re, json as _json
        match = re.search(r'\{[\s\S]+\}', combined_content)
        if not match:
            return _load_pricing()
        pricing_data = _json.loads(match.group())

        # Normalize to list[dict] matching _load_pricing() shape: {ingredient, unit, price_php}
        if "ingredient_prices_php_per_kg" in pricing_data:
            return [
                {"ingredient": k, "unit": "kg", "price_php": v}
                for k, v in pricing_data["ingredient_prices_php_per_kg"].items()
            ]
        if "items" in pricing_data and isinstance(pricing_data["items"], list):
            return pricing_data["items"]
        # If it's already a flat dict of name->price
        if all(isinstance(v, (int, float)) for v in pricing_data.values()):
            return [
                {"ingredient": k, "unit": "kg", "price_php": v}
                for k, v in pricing_data.items()
            ]
        return _load_pricing()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Accountant RAG pricing fallback: {e}")
        return _load_pricing()


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
        pricing_items = await _load_candidate_pricing()
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
            # Math in code — pre-compute analysis before GPT call
            gap_pct = round((over_budget_by / budget) * 100, 1)
            dish_with_pct = [
                {
                    "name": d.dish_name,
                    "cost_php": round(d.cost_php, 2),
                    "pct_of_total": round(d.cost_php / total_cost * 100, 1),
                }
                for d in dish_costs
            ]
            top_driver = max(dish_costs, key=lambda d: d.cost_php)
            single_item_dominant = (top_driver.cost_php / over_budget_by) > 0.5 if over_budget_by > 0 else False

            flagged_items = await _gpt_flagged_analysis(
                dish_with_pct=dish_with_pct,
                gap=over_budget_by,
                gap_pct=gap_pct,
                top_driver_name=top_driver.dish_name,
                single_item_dominant=single_item_dominant,
                total_cost=total_cost,
                budget=budget,
                event_spec=event_spec,
                dish_costs=dish_costs,
            )

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
