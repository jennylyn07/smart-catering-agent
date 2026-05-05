"""Seed the catering-inventory Cosmos DB container from mock_inventory.json."""
import asyncio
import json
import os
from pathlib import Path

from azure.cosmos.aio import CosmosClient
from dotenv import load_dotenv

load_dotenv()


async def main():
    endpoint = os.environ["COSMOS_ENDPOINT"]
    key = os.environ["COSMOS_KEY"]
    database_name = os.getenv("COSMOS_DATABASE", "smart-catering")
    container_name = os.getenv("COSMOS_INVENTORY_CONTAINER", "catering-inventory")

    path = Path(__file__).resolve().parents[1] / "data" / "mock_inventory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("inventory", [])

    print(f"Seeding {len(items)} inventory items to {container_name}...")

    async with CosmosClient(endpoint, credential=key) as client:
        db = client.get_database_client(database_name)

        # Create container if it doesn't exist
        try:
            await db.create_container(
                id=container_name,
                partition_key={"paths": ["/ingredient"], "kind": "Hash"},
            )
            print(f"Created container: {container_name}")
        except Exception:
            print(f"Container {container_name} already exists, continuing...")

        container = db.get_container_client(container_name)

        uploaded = 0
        for item in items:
            ingredient = str(item.get("ingredient", "")).strip().lower()
            if not ingredient:
                continue
            doc = {
                "id": ingredient,
                "ingredient": ingredient,
                "quantity": float(item.get("quantity", 0)),
                "unit": str(item.get("unit", "")),
            }
            await container.upsert_item(doc)
            print(f"  Uploaded: {ingredient} — {doc['quantity']} {doc['unit']}")
            uploaded += 1

        print(f"\nDone. {uploaded} inventory items uploaded to Cosmos DB.")


if __name__ == "__main__":
    asyncio.run(main())
