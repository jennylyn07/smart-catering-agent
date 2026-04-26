"""utils/azure_client.py

Creates Azure SDK client objects for the Smart Catering multi-agent system.

This module is intentionally safe by default:
- Loads configuration from environment variables (via a local .env file)
- Constructs client objects only
- Does NOT make network calls or send LLM requests
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from dotenv import load_dotenv


AZURE_OPENAI_API_VERSION = "2024-02-15-preview"


@dataclass(frozen=True)
class AzureSettings:
    """Azure configuration loaded from environment variables."""

    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    cosmos_endpoint: str
    cosmos_key: str
    azure_search_endpoint: str
    azure_search_key: str
    azure_storage_connection_string: Optional[str]


def _load_env() -> None:
    """Load environment variables from a local .env file if present."""

    load_dotenv(override=False)


def _require_env(name: str) -> str:
    """Read a required environment variable.

    Args:
        name: Environment variable key.

    Returns:
        The environment variable value.

    Raises:
        RuntimeError: If the variable is missing or empty.
    """

    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _optional_env(name: str) -> Optional[str]:
    """Read an optional environment variable."""

    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


@lru_cache(maxsize=1)
def get_settings() -> AzureSettings:
    """Load and cache Azure settings from the environment."""

    _load_env()

    return AzureSettings(
        azure_openai_endpoint=_require_env("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_key=_require_env("AZURE_OPENAI_API_KEY"),
        azure_openai_deployment=_require_env("AZURE_OPENAI_DEPLOYMENT"),
        cosmos_endpoint=_require_env("COSMOS_ENDPOINT"),
        cosmos_key=_require_env("COSMOS_KEY"),
        azure_search_endpoint=_require_env("AZURE_SEARCH_ENDPOINT"),
        azure_search_key=_require_env("AZURE_SEARCH_KEY"),
        azure_storage_connection_string=_optional_env("AZURE_STORAGE_CONNECTION_STRING"),
    )


def get_azure_openai_deployment_name() -> str:
    """Return the configured Azure OpenAI deployment name."""

    return get_settings().azure_openai_deployment


def create_async_azure_openai_client() -> Any:
    """Create an async Azure OpenAI client (no requests are sent).

    Returns:
        An AsyncAzureOpenAI client instance.
    """

    settings = get_settings()

    from openai import AsyncAzureOpenAI  # type: ignore

    return AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=AZURE_OPENAI_API_VERSION,
    )


def create_cosmos_client() -> Any:
    """Create an async Azure Cosmos DB client (no requests are sent)."""

    settings = get_settings()
    from azure.cosmos.aio import CosmosClient  # type: ignore

    return CosmosClient(url=settings.cosmos_endpoint, credential=settings.cosmos_key)


def create_search_client(*, index_name: str) -> Any:
    """Create an async Azure AI Search client bound to an index.

    Args:
        index_name: Name of the Azure AI Search index.

    Returns:
        A SearchClient instance.
    """

    settings = get_settings()

    from azure.core.credentials import AzureKeyCredential  # type: ignore
    from azure.search.documents.aio import SearchClient as AsyncSearchClient  # type: ignore

    return AsyncSearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(settings.azure_search_key),
    )


def create_blob_service_client() -> Any:
    """Create an async Azure Blob Storage service client.

    Raises:
        RuntimeError: If AZURE_STORAGE_CONNECTION_STRING is not set.
    """

    settings = get_settings()
    if settings.azure_storage_connection_string is None:
        raise RuntimeError(
            "Missing required environment variable: AZURE_STORAGE_CONNECTION_STRING"
        )

    from azure.storage.blob.aio import BlobServiceClient  # type: ignore

    return BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)


def try_load_settings() -> Optional[AzureSettings]:
    """Best-effort settings loader.

    Useful for scripts that want a friendly "not configured" state.
    """

    try:
        return get_settings()
    except RuntimeError:
        return None
