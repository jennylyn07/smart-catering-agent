"""scripts/setup_search_index.py

Creates and populates the Azure AI Search index for the Smart Catering knowledge base.

WARNING: Running this script will make network calls to Azure AI Search and may incur costs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchableField,
    SimpleField,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.azure_client import get_settings


INDEX_NAME = "catering-knowledge-base"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_index(index_client: SearchIndexClient) -> None:
    fields = [
        SimpleField(name="id", type="Edm.String", key=True, filterable=True, sortable=True),
        SearchableField(name="content"),
        SimpleField(name="category", type="Edm.String", filterable=True, facetable=True, sortable=True),
        SearchableField(name="name"),
        SearchableField(name="cuisine", filterable=True, facetable=True, sortable=True),
        SearchableField(name="dish_category", filterable=True, facetable=True, sortable=True),
        SearchableField(
            name="dietary_tags",
            collection=True,
            searchable=True,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="allergens",
            type="Collection(Edm.String)",
            filterable=True,
            facetable=True,
        ),
    ]

    index = SearchIndex(name=INDEX_NAME, fields=fields)

    try:
        index_client.delete_index(INDEX_NAME)
    except ResourceNotFoundError:
        pass

    index_client.create_index(index)


def _upload_documents(search_client: SearchClient, documents: List[Dict[str, Any]]) -> None:
    batch_size = 500
    for start in range(0, len(documents), batch_size):
        chunk = documents[start : start + batch_size]
        result = search_client.upload_documents(documents=chunk)
        failed = [r for r in result if not r.succeeded]
        if failed:
            failures = ", ".join([f"{r.key}: {r.error_message}" for r in failed])
            raise RuntimeError(f"Azure AI Search upload failed for {len(failed)} documents: {failures}")


def main() -> None:
    print(
        "WARNING: This script will connect to Azure AI Search and make network calls. "
        "Only run if you intend to create/update the search index and upload documents."
    )

    settings = get_settings()

    credential = AzureKeyCredential(settings.azure_search_key)
    index_client = SearchIndexClient(endpoint=settings.azure_search_endpoint, credential=credential)
    search_client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=INDEX_NAME,
        credential=credential,
    )

    _ensure_index(index_client)

    root = _project_root()
    kb_dir = root / "knowledge_base"

    recipes_path = kb_dir / "recipes.json"
    pricing_path = kb_dir / "pricing.json"
    suppliers_path = kb_dir / "suppliers.json"

    recipes_payload = _load_json(recipes_path)
    recipes = recipes_payload.get("recipes") if isinstance(recipes_payload, dict) else None
    if not isinstance(recipes, list):
        raise ValueError("recipes.json missing 'recipes' list")

    recipe_docs: List[Dict[str, Any]] = []
    for recipe in recipes:
        if not isinstance(recipe, dict):
            continue
        rid = str(recipe.get("id") or "").strip()
        if not rid:
            continue

        name = str(recipe.get("name") or "").strip()
        print(f"Uploading recipe [{rid}] {name}")

        dietary_flags = recipe.get("dietary_flags")
        dietary_tags: list[str] = []
        if isinstance(dietary_flags, dict):
            dietary_tags = [str(k) for k, v in dietary_flags.items() if bool(v)]
        elif isinstance(dietary_flags, list):
            dietary_tags = [str(x) for x in dietary_flags if str(x).strip()]

        allergens = recipe.get("allergens")
        allergens_list: list[str] = []
        if isinstance(allergens, list):
            allergens_list = [str(a) for a in allergens if str(a).strip()]

        recipe_docs.append(
            {
                "id": rid,
                "category": "recipes",
                "name": name,
                "cuisine": str(recipe.get("cuisine") or "").strip(),
                "dish_category": str(recipe.get("category") or "").strip(),
                "dietary_tags": dietary_tags,
                "allergens": allergens_list,
                "content": json.dumps(recipe, ensure_ascii=False),
            }
        )

    knowledge_docs: List[Dict[str, Any]] = []

    pricing_payload = _load_json(pricing_path)
    knowledge_docs.append(
        {
            "id": "pricing_main",
            "category": "pricing",
            "content": json.dumps(pricing_payload, ensure_ascii=False),
        }
    )

    suppliers_payload = _load_json(suppliers_path)
    knowledge_docs.append(
        {
            "id": "suppliers_main",
            "category": "suppliers",
            "content": json.dumps(suppliers_payload, ensure_ascii=False),
        }
    )

    _upload_documents(search_client, recipe_docs + knowledge_docs)

    print(f"Done. {len(recipe_docs)} recipe documents + 2 knowledge documents uploaded.")

    count = search_client.get_document_count()
    print(f"Index '{INDEX_NAME}' document count: {count}")


if __name__ == "__main__":
    main()
