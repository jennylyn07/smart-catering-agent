"""scripts/setup_search_index.py

Creates and populates the Azure AI Search index for the Smart Catering knowledge base.

WARNING: Running this script will make network calls to Azure AI Search and may incur costs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchableField,
    SimpleField,
)

from utils.azure_client import get_settings


INDEX_NAME = "catering-knowledge-base"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_documents(*, source_file: Path, category: str, payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    else:
        items = [payload]

    for i, item in enumerate(items):
        if isinstance(item, (dict, list)):
            content = json.dumps(item, ensure_ascii=False)
        else:
            content = str(item)

        yield {
            "id": f"{category}_{source_file.stem}_{i}",
            "content": content,
            "category": category,
            "source_file": source_file.name,
        }


def _ensure_index(index_client: SearchIndexClient) -> None:
    fields = [
        SimpleField(name="id", type="Edm.String", key=True, filterable=True, sortable=True),
        SearchableField(name="content", type="Edm.String"),
        SimpleField(name="category", type="Edm.String", filterable=True, facetable=True, sortable=True),
        SimpleField(name="source_file", type="Edm.String", filterable=True, facetable=True, sortable=True),
    ]

    index = SearchIndex(name=INDEX_NAME, fields=fields)

    # Create or update so repeated runs are safe.
    index_client.create_or_update_index(index)


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

    sources = [
        (kb_dir / "recipes.json", "recipes"),
        (kb_dir / "pricing.json", "pricing"),
        (kb_dir / "suppliers.json", "suppliers"),
    ]

    all_docs: List[Dict[str, Any]] = []
    for path, category in sources:
        payload = _load_json(path)
        all_docs.extend(list(_iter_documents(source_file=path, category=category, payload=payload)))

    _upload_documents(search_client, all_docs)

    count = search_client.get_document_count()
    print(f"Index '{INDEX_NAME}' document count: {count}")


if __name__ == "__main__":
    main()
