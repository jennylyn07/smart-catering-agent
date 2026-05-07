"""utils/cosmos_store.py

Helpers for accessing Cosmos DB containers used by the Smart Catering system.

This module only constructs client/container objects. Network calls happen when
item operations are executed.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List

from utils.logger import log_event

from utils.azure_client import create_cosmos_client


def get_database_name() -> str:
    """Return the Cosmos DB database name used by the application."""

    value = os.getenv("COSMOS_DATABASE")
    return value.strip() if value and value.strip() else "smart-catering"


def get_container_name() -> str:
    """Return the Cosmos DB container name used for catering orders."""

    value = os.getenv("COSMOS_CONTAINER")
    return value.strip() if value and value.strip() else "catering-orders"


def get_inventory_container_name() -> str:
    """Return the Cosmos DB container name for inventory."""
    value = os.getenv("COSMOS_INVENTORY_CONTAINER")
    return value.strip() if value and value.strip() else "catering-inventory"


def create_orders_container_client() -> Any:
    """Create an async Cosmos container client for the orders container."""

    client = create_cosmos_client()
    database = client.get_database_client(get_database_name())
    return database.get_container_client(get_container_name())


async def read_order_document(*, order_id: str) -> Dict[str, Any]:
    """Read an order document from Cosmos DB and close the client.

    WARNING: This function makes a network call to Azure Cosmos DB.
    """

    client = create_cosmos_client()
    try:
        database = client.get_database_client(get_database_name())
        container = database.get_container_client(get_container_name())
        return await container.read_item(item=order_id, partition_key=order_id)
    finally:
        await client.close()


async def upsert_order_document(*, order_id: str, document: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert an order document into Cosmos DB and close the client.

    WARNING: This function makes a network call to Azure Cosmos DB.
    """

    client = create_cosmos_client()
    try:
        database = client.get_database_client(get_database_name())
        container = database.get_container_client(get_container_name())
        payload = dict(document)
        payload.setdefault("id", order_id)
        payload.setdefault("order_id", order_id)
        return await container.upsert_item(payload)
    finally:
        await client.close()


async def persist_final_plan(*, order_id: str, final_plan: Dict[str, Any]) -> None:
    """Persist a FinalPlan payload under the given order_id.

    WARNING: This function makes a network call to Azure Cosmos DB.
    """

    doc = {
        "id": order_id,
        "order_id": order_id,
        "final_plan": final_plan,
        "adaptation_events": [],
    }
    try:
        await upsert_order_document(order_id=order_id, document=doc)
        log_event(
            agent_id="cosmos_store",
            action="save_order",
            status="success",
            details={"order_id": order_id},
        )
    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id="cosmos_store",
            action="save_order",
            status="error",
            details={"order_id": order_id, "error": str(exc), "error_type": type(exc).__name__},
        )
        raise
    log_event(
        agent_id="api",
        action="cosmos_persist_final_plan",
        status="success",
        details={"order_id": order_id},
    )


async def append_adaptation_event(
    *,
    order_id: str,
    adaptation_event: Dict[str, Any],
    updated_final_plan: Dict[str, Any],
) -> None:
    """Append an adaptation event and persist the updated FinalPlan.

    WARNING: This function makes a network call to Azure Cosmos DB.
    """

    doc = await read_order_document(order_id=order_id)
    events = doc.get("adaptation_events")
    if not isinstance(events, list):
        events = []
    events.append(adaptation_event)

    doc["final_plan"] = updated_final_plan
    doc["adaptation_events"] = events

    await upsert_order_document(order_id=order_id, document=doc)
    log_event(
        agent_id="api",
        action="cosmos_append_adaptation_event",
        status="success",
        details={"order_id": order_id, "event_count": len(events)},
    )


def format_past_orders_context(past_orders: list) -> str:
    """Format past orders list into a readable context string for agent prompts."""
    if not past_orders:
        return ""
    lines = ["Past events with similar profile:"]
    for o in past_orders:
        dishes = ", ".join(o.get("menu_item_names") or [])
        lines.append(
            f"- {o.get('event_date')} | {o.get('guest_count')} guests | "
            f"{o.get('cuisine')} | PHP {o.get('total_cost_php')} total "
            f"(PHP {o.get('per_head_cost')} per head) | Dishes: {dishes}"
        )
    return "\n".join(lines)


async def query_past_orders(
    *,
    cuisine_preferences: list,
    guest_count: int,
) -> list:
    """Query Cosmos for past orders matching cuisine or similar guest count.

    Returns up to 3 lightweight past event dicts.
    Gracefully returns empty list on any failure.

    WARNING: This function makes a network call to Azure Cosmos DB.
    """
    try:
        client = create_cosmos_client()
        try:
            async def _fetch() -> List[Dict[str, Any]]:
                db = client.get_database_client(get_database_name())
                container = db.get_container_client(get_container_name())
                query = (
                    "SELECT c.final_plan FROM c "
                    "WHERE IS_DEFINED(c.final_plan) "
                    "ORDER BY c._ts DESC "
                    "OFFSET 0 LIMIT 20"
                )

                result: List[Dict[str, Any]] = []
                async for item in container.query_items(
                    query=query,
                    enable_cross_partition_query=True,
                ):
                    if isinstance(item, dict):
                        result.append(item)
                return result

            items = await asyncio.wait_for(_fetch(), timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            return []
        finally:
            await client.close()

        cuisines_lower = [str(c).lower() for c in (cuisine_preferences or [])]
        guest_min = guest_count * 0.7
        guest_max = guest_count * 1.3

        matches: list[dict[str, Any]] = []
        for item in items:
            fp = item.get("final_plan") or {}
            event_spec = fp.get("event_specification") or {}
            cost_report = fp.get("cost_report") or {}
            menu_plan = fp.get("menu_plan") or {}

            past_guest_count = event_spec.get("guest_count") or 0
            past_cuisines = [
                str(c).lower() for c in (event_spec.get("cuisine_preferences") or [])
            ]
            past_total = cost_report.get("total_cost_php") or 0
            past_date = event_spec.get("event_date") or "unknown date"
            menu_items = menu_plan.get("menu_items") or []
            dish_names: list[str] = []
            for m in menu_items:
                if isinstance(m, dict):
                    name = m.get("name") or m.get("dish_name")
                    if name:
                        dish_names.append(str(name))

            cuisine_match = any(c in cuisines_lower for c in past_cuisines)
            guest_match = guest_min <= past_guest_count <= guest_max

            if cuisine_match or guest_match:
                per_head = (
                    round(past_total / past_guest_count, 2)
                    if past_guest_count
                    else 0
                )
                matches.append(
                    {
                        "event_date": past_date,
                        "guest_count": past_guest_count,
                        "cuisine": ", ".join(past_cuisines) or "unspecified",
                        "total_cost_php": past_total,
                        "per_head_cost": per_head,
                        "menu_item_names": dish_names[:8],
                    }
                )

            if len(matches) >= 3:
                break

        return matches

    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id="cosmos_store",
            action="query_past_orders",
            status="error",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
        return []


async def get_recent_orders(*, limit: int = 20) -> list:
    """Fetch recent orders from Cosmos DB for history display.
    
    Returns list of lightweight order summary dicts.
    Gracefully returns empty list on any failure.
    
    WARNING: This function makes a network call to Azure Cosmos DB.
    """
    try:
        client = create_cosmos_client()
        try:
            database = client.get_database_client(get_database_name())
            container = database.get_container_client(get_container_name())
            query = (
                f"SELECT TOP {limit} c.id, c._ts, "
                "c.final_plan.event_specification, "
                "c.final_plan.cost_report "
                "FROM c "
                "ORDER BY c._ts DESC"
            )

            raw = []
            async for item in container.query_items(query=query):
                raw.append(item)

            result = []
            for item in raw:
                event_spec = item.get("event_specification") or {}
                cost = item.get("cost_report") or {}
                order_id = item.get("id")
                if not order_id or not event_spec:
                    continue
                result.append({
                    "order_id": order_id,
                    "event_name": event_spec.get("event_name")
                                  or "Unnamed Event",
                    "event_date": event_spec.get("event_date") or "",
                    "guest_count": event_spec.get("guest_count") or 0,
                    "budget_php": event_spec.get("budget_php") or 0,
                    "total_cost_php": cost.get("total_cost_php") or 0,
                    "within_budget": (
                        cost.get("within_budget")
                        or cost.get("is_within_budget")
                    ),
                    "cuisine_preferences": (
                        event_spec.get("cuisine_preferences") or []
                    ),
                    "dietary_restrictions": (
                        event_spec.get("dietary_restrictions") or []
                    ),
                    "allergies": event_spec.get("allergies") or [],
                    "notes": event_spec.get("notes") or "",
                })
            return result
        finally:
            await client.close()

    except Exception as exc:
        log_event(
            agent_id="cosmos_store",
            action="get_recent_orders",
            status="error",
            details={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return []


async def query_inventory_from_cosmos() -> list:
    """Query all inventory items from Cosmos DB catering-inventory container.
    
    Returns list of {ingredient, quantity, unit} dicts.
    Gracefully returns empty list on any failure.
    
    WARNING: This function makes a network call to Azure Cosmos DB.
    """
    try:
        client = create_cosmos_client()
        try:
            database = client.get_database_client(get_database_name())
            container = database.get_container_client(
                get_inventory_container_name()
            )

            async def _fetch():
                query = "SELECT c.ingredient, c.quantity, c.unit FROM c"
                result = []
                async for item in container.query_items(
                    query=query,
                ):
                    ingredient = item.get("ingredient")
                    quantity = item.get("quantity")
                    unit = item.get("unit")
                    if ingredient and quantity is not None and unit:
                        result.append({
                            "ingredient": ingredient,
                            "quantity": quantity,
                            "unit": unit,
                        })
                return result

            items = await asyncio.wait_for(_fetch(), timeout=3.0)
        finally:
            await client.close()

        return items

    except Exception as exc:
        log_event(
            agent_id="cosmos_store",
            action="query_inventory",
            status="error",
            details={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return []
