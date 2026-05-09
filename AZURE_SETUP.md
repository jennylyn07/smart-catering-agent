# ☁️ Azure Services Setup Guide
### Smart Catering Agent — Code Without Barriers Hackathon 2026

This guide walks you through provisioning all Azure services required to run the Smart Catering Agent from scratch, populating the knowledge base, and verifying connectivity.

---

## Overview of Required Services

| Service | Resource Name (example) | Purpose |
|---|---|---|
| Azure OpenAI | `foundry-jmagno-2026-resource` | Powers all 5 agent GPT-4o reasoning calls |
| Azure AI Search | `search-jmagno-2026` | RAG knowledge base — 70 documents (68 recipes + pricing + suppliers) |
| Azure Cosmos DB | `cosmos-jmagno-2026` | Order persistence + inventory + historical order context |
| Azure Blob Storage | `storagejmagno2026` | Document storage layer (optional for local dev) |

---

## Prerequisites

- An active [Azure subscription](https://portal.azure.com)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed (`az --version`) — optional but useful for scripting
- Python 3.12+ with `venv` activated and `requirements.txt` installed
- Node.js 18+ (for the frontend)
- A `.env` file at the project root (see [Environment Variables](#environment-variables))

---

## Step 1 — Azure OpenAI

### 1.1 Create the Resource

1. Go to [portal.azure.com](https://portal.azure.com) → **Create a resource** → search **Azure OpenAI**
2. Fill in:
   - **Subscription:** your subscription
   - **Resource Group:** create new or use existing (e.g., `rg-smart-catering`)
   - **Region:** pick any region where GPT-4o is available — check the [Azure OpenAI model availability matrix](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models) for your subscription type
   - **Name:** e.g., `foundry-jmagno-2026-resource`
   - **Pricing tier:** `Standard S0`
3. Click **Review + Create → Create**

### 1.2 Deploy GPT-4o

1. Once the resource is created, look for the **Go to Azure AI Foundry** button in the resource overview (you may see it labelled **Azure OpenAI Studio** depending on your portal version — both lead to the same place)
2. Navigate to **Deployments → + Deploy model** (or **+ Create new deployment** in older portal versions)
3. Select:
   - **Model:** `gpt-4o`
   - **Deployment name:** `gpt-4o` ← this exact name is used in the `.env`
   - **Deployment type:** `Standard`
4. Click **Deploy** (or **Create**)

### 1.3 Get Your Keys

In the Azure portal, open your OpenAI resource → **Keys and Endpoint**:

- Copy **Endpoint** → `AZURE_OPENAI_ENDPOINT`
- Copy **Key 1** → `AZURE_OPENAI_API_KEY`

> **Note:** The API version used is `2024-12-01-preview` (hardcoded in `utils/azure_client.py`). No `.env` entry needed for this.

---

## Step 2 — Azure AI Search

### 2.1 Create the Resource

1. Portal → **Create a resource** → search **Azure AI Search**
2. Fill in:
   - **Resource Group:** same as above
   - **Service name:** e.g., `search-jmagno-2026`
   - **Location:** same region as OpenAI
   - **Pricing tier:** `Free` (for dev/hackathon) or `Basic`
3. Click **Review + Create → Create**

### 2.2 Get Your Keys

Open your Search resource → **Keys**:

- Copy **URL** from the Overview page → `AZURE_SEARCH_ENDPOINT`
- Copy **Primary admin key** → `AZURE_SEARCH_KEY`

### 2.3 Create and Populate the Index

The project ships with a setup script that creates the index schema and uploads all 70 knowledge base documents (68 recipes + pricing + suppliers).

**Make sure your `.env` is filled in first**, then run:

```powershell
# From the project root, with venv activated
venv\Scripts\python.exe scripts/setup_search_index.py
```

Expected output:
```
WARNING: This script will connect to Azure AI Search and make network calls...
Uploading recipe [r001] Kare-Kare
Uploading recipe [r002] Lechon Kawali
...
Done. 68 recipe documents + 2 knowledge documents uploaded.
Index 'catering-knowledge-base' document count: 70
```

The index name is hardcoded as `catering-knowledge-base`. The agents query this index name directly.

---

## Step 3 — Azure Cosmos DB

### 3.1 Create the Account

1. Portal → **Create a resource** → search **Azure Cosmos DB**
2. Select **Azure Cosmos DB for NoSQL** (the default SQL API)
3. Fill in:
   - **Resource Group:** same as above
   - **Account Name:** e.g., `cosmos-jmagno-2026`
   - **Location:** same region
   - **Capacity mode:** `Serverless` (recommended for hackathon — no minimum charge)
4. Click **Review + Create → Create**

### 3.2 Create the Database and Containers

Once provisioned, go to **Data Explorer** in the portal:

**Create Database:**
- Database id: `smart-catering`
- ☑ Share throughput across containers: **leave unchecked** (Serverless mode)

**Create Container — Orders:**
- Database: `smart-catering`
- Container id: `catering-orders`
- Partition key: `/order_id`


**Create Container — Inventory:**
- Database: `smart-catering`
- Container id: `catering-inventory`
- Partition key: `/ingredient`


### 3.3 Get Your Keys

Open your Cosmos DB account → **Keys**:

- Copy **URI** → `COSMOS_ENDPOINT`
- Copy **PRIMARY KEY** → `COSMOS_KEY`

### 3.4 Seed the Inventory

The Stock Manager agent queries `catering-inventory` first before falling back to the local mock file. Seed it with the 33 mock inventory items:

```powershell
# From the project root, with venv activated
venv\Scripts\python.exe scripts/seed_inventory.py
```

Expected output:
```
Seeding 33 inventory items to catering-inventory...
Created container: catering-inventory
  Uploaded: chicken — 5.0 kg
  Uploaded: pork — 3.0 kg
  Uploaded: ground pork — 2.0 kg
  ...
Done. 33 inventory items uploaded to Cosmos DB.
```

> If the container already exists (e.g., you re-run the script), it will print "already exists" and continue normally.

---

## Step 4 — Azure Blob Storage (Optional)

Blob Storage is the document storage layer. It is **optional for local development** — the agents do not require it to function. Only provision this if you plan to add document storage features in production.

### 4.1 Create the Storage Account

1. Portal → **Create a resource** → **Storage account**
2. Fill in:
   - **Resource Group:** same as above
   - **Storage account name:** e.g., `storagejmagno2026` (must be globally unique, lowercase, no hyphens)
   - **Region:** same region
   - **Redundancy:** `LRS` (Locally Redundant — cheapest)
3. Click **Review + Create → Create**

### 4.2 Get the Connection String

Open your Storage account → **Access keys** → **Show**:

- Copy **Connection string** for Key 1 → `AZURE_STORAGE_CONNECTION_STRING`

---

## Environment Variables

### Root `.env` (backend)

Create a `.env` file in the **project root**. **Never commit this file** (it is already in `.gitignore`).

```dotenv
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-resource-name>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-api-key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# Azure Cosmos DB
COSMOS_ENDPOINT=https://<your-account>.documents.azure.com:443/
COSMOS_KEY=<your-primary-key>
COSMOS_DATABASE=smart-catering
COSMOS_CONTAINER=catering-orders

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net
AZURE_SEARCH_KEY=<your-admin-key>

# Azure Blob Storage (optional for local dev)
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...

# API authentication key for callers
API_KEY=my-secret-catering-key-2026
```

> `COSMOS_INVENTORY_CONTAINER` defaults to `catering-inventory` in code — no `.env` entry needed unless you rename it.

### `frontend/.env` (React frontend)

Create a **separate** `.env` file inside the `frontend/` directory. The React app reads `REACT_APP_API_KEY` at every API call — it will hard-fail with `"Missing REACT_APP_API_KEY."` if this file is absent.

```dotenv
# Must match the API_KEY value in the root .env
REACT_APP_API_KEY=my-secret-catering-key-2026
```

> This file is separate from the root `.env`. `npm start` / Create React App only picks up `REACT_APP_*` variables from `frontend/.env`.

---

## Verification

### Verify OpenAI connectivity

```powershell
venv\Scripts\python.exe -c "
import asyncio
from utils.azure_client import create_async_azure_openai_client, get_settings

async def test():
    settings = get_settings()
    client = create_async_azure_openai_client()
    result = await client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=[{'role': 'user', 'content': 'Say hello'}]
    )
    print('OpenAI OK:', result.choices[0].message.content)

asyncio.run(test())
"
```

### Verify Cosmos DB connectivity

```powershell
venv\Scripts\python.exe -c "
import asyncio
from utils.azure_client import create_cosmos_client
from utils.cosmos_store import get_database_name

async def test():
    client = create_cosmos_client()
    try:
        db = client.get_database_client(get_database_name())
        props = await db.read()
        print('Cosmos OK. Database:', props['id'])
    finally:
        await client.close()

asyncio.run(test())
"
```


### Verify AI Search connectivity

```powershell
venv\Scripts\python.exe -c "
import asyncio
from utils.azure_client import create_search_client

async def test():
    async with create_search_client(index_name='catering-knowledge-base') as client:
        count = await client.get_document_count()
        print(f'Search OK: {count} documents in catering-knowledge-base')

asyncio.run(test())
"
```

### Run the full integration suite

```powershell
# All 23 checks should pass
venv\Scripts\python.exe -m tests.test_correctness
```

---

## Post-Setup Checklist

| Step | Command / Action | Expected Result |
|---|---|---|
| ✅ Root `.env` created | — | 10 vars present (3 OpenAI + 4 Cosmos + 2 Search + API_KEY) |
| ✅ `frontend/.env` created | — | `REACT_APP_API_KEY` matches `API_KEY` |
| ✅ Search index populated | `python scripts/setup_search_index.py` | 70 documents in `catering-knowledge-base` |
| ✅ Inventory seeded | `python scripts/seed_inventory.py` | 33 items in `catering-inventory` |
| ✅ OpenAI ping | See verification snippet above | Returns "hello" response |
| ✅ Cosmos ping | See verification snippet above | 0+ orders returned without exception |
| ✅ Integration tests | `python -m tests.test_correctness` | 23/23 ✅ |

---

## Troubleshooting

### `RuntimeError: Missing required environment variable: AZURE_OPENAI_ENDPOINT`
Your `.env` file is missing or not in the project root. Make sure the file exists at `smart-catering-agent/.env` and contains all required variables.

### `ResourceNotFoundError` when running `setup_search_index.py`
Your AI Search resource may not be fully provisioned yet — wait 1-2 minutes after creation and retry.

### Cosmos DB `OperationExecutionException` — `Request rate too large`
Serverless Cosmos DB has rate limits. Retry after a few seconds. If persistent, switch to a Provisioned Throughput container with at least 400 RU/s.

### OpenAI `AuthenticationError` / 401
Verify the `AZURE_OPENAI_API_KEY` matches **Key 1** or **Key 2** in the portal under **Keys and Endpoint**. The endpoint URL must not have a trailing path (e.g., just `https://xxx.openai.azure.com`, not `https://xxx.openai.azure.com/openai`).

### OpenAI returns 404 for deployment
The deployment name in `AZURE_OPENAI_DEPLOYMENT` must exactly match the name you set in Azure AI Foundry / Azure OpenAI Studio (e.g., `gpt-4o`). It is case-sensitive.

### Backend startup takes ~20 seconds
This is expected. Semantic Kernel and AutoGen import at startup on Windows. Once the server is ready, per-request latency is unaffected.

---

## Architecture Reference

```
.env (local only, never committed)
  ├── AZURE_OPENAI_*   → utils/azure_client.py → all 5 agents
  ├── COSMOS_*         → utils/cosmos_store.py → orders + inventory
  ├── AZURE_SEARCH_*   → utils/azure_client.py → Head Chef + Accountant RAG
  └── AZURE_STORAGE_*  → utils/azure_client.py → blob storage (optional)

scripts/
  ├── setup_search_index.py   ← run once to populate AI Search (70 docs)
  └── seed_inventory.py       ← run once to seed Cosmos inventory (33 items)
```

---

*Smart Catering Agent — Code Without Barriers Hackathon 2026*  
*Participant: Jennylyn Magno · Philippines · Solo submission*
