"""utils/cosmos_store.py

Helpers for accessing Cosmos DB containers used by the Smart Catering system.

This module only constructs client/container objects. Network calls happen when
item operations are executed.
"""

from __future__ import annotations

import os
from typing import Any, Dict

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
    await upsert_order_document(order_id=order_id, document=doc)
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
