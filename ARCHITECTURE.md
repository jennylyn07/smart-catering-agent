# Smart Catering Agent — Architecture

> **Principle:** Hard constraints live in code, always. Soft judgments belong to GPT. Math belongs to code. Every GPT call degrades gracefully.

---

## Full Pipeline

```mermaid
flowchart TD
    Customer["📝 Customer Request\nraw_customer_text"]

    subgraph API["🌐 FastAPI — port 8001"]
        Auth["X-API-Key Auth"]
        Val["Pydantic Validation\nRate Limit 10/min"]
        Endpoints["POST /api/v1/catering/order\nPOST /api/v1/catering/adapt\nPOST /api/v1/catering/multi-order\nGET  /api/v1/health/agents"]
    end

    subgraph Orchestrator["⚙️ Orchestration Engine — engine.py"]
        Session["session_id + SharedMemory\nAudit Trail + SHA-256 Hashes"]
        Memory["query_past_orders()\nCosmos LTM — asyncio.wait_for(5s)"]
        Retry["_call_with_retry() — max 3 attempts\nTimeoutError · JSONDecodeError · OSError"]
    end

    subgraph Agents["🤖 Five Specialized Agents"]
        direction LR
        C["🧑‍💼 Concierge\nGPT-4o temp 0.0\nHard/soft restriction split\n_coerce_event_spec() enforces\nIMMUTABLE: allergies, dietary"]
        HC["👨‍🍳 Head Chef\nGPT-4o temp 0.8\nRAG: 68 recipes\nMenu Engineering quadrant\nPost-AI allergy check"]
        A["💰 Accountant\nGPT-4o temp 0.0\nRAG: pricing data\n7% cost buffer (code)\nProfitability forecast"]
        LL["🚚 Logistics Lead\nGPT-4o temp 0.3\nStaffing ratios table\nT-minus CPM\nGantt derivation (code)"]
        SM["📦 Stock Manager\nGPT-4o temp 0.7\nInventory check\nWaste risk (FIFO)\nasyncio.gather()"]
    end

    subgraph Negotiation["💬 Budget Negotiation — AutoGen GroupChat"]
        direction TB
        AG_A["AccountantAgent\nFlags over-budget dishes\nJSON: flagged_dishes"]
        AG_HC["HeadChefAgent\nProposes cheaper alternatives\nJSON: reformulated_dishes"]
        Loop["RoundRobinGroupChat\nmax 3 rounds\nreformulation_exhausted → early exit"]
        Fallback["Manual fallback loop\n(on AutoGen exception)"]
        AG_A <-->|"conversation"| AG_HC
        Loop --> Fallback
    end

    subgraph AzureServices["☁️ Azure Services"]
        AOI["Azure OpenAI\nGPT-4o gpt-4o 2024-11-20\nfoundry-jmagno-2026\nPowers all 5 agents"]
        AIS["Azure AI Search\nsearch-jmagno-2026\ncatering-knowledge-base\n70 docs: 68 recipes + pricing + suppliers"]
        CDB["Azure Cosmos DB\ncosmos-jmagno-2026\ncatering-orders (NoSQL Serverless)\nOrder persistence + LTM queries"]
        Blob["Azure Blob Storage\nstoragejmagno2026\nDocument storage layer"]
    end

    subgraph Framework["🛠️ Microsoft Agent Framework"]
        SK["Semantic Kernel\nCateringAgentsPlugin\n@kernel_function × 5 agents\nkernel.invoke() orchestration"]
        AutoGen["AutoGen 0.7.5\nRoundRobinGroupChat\nAccountantAgent + HeadChefAgent\nAzureOpenAIChatCompletionClient"]
    end

    subgraph UI["🖥️ React Frontend — port 3000"]
        Form["Order Form\nraw customer text input"]
        Pipeline["Agent Pipeline Strip\nLive elapsed timer"]
        Dashboard["Results Dashboard\nMenu · Cost · Timeline · Procurement\nNutrition · Profitability"]
        History["Order History\nCosmos-persisted"]
    end

    Customer --> API
    API --> Orchestrator
    Orchestrator --> C
    C -->|"EventSpecification"| Memory
    Memory -->|"past_context"| HC
    Memory -->|"past_context"| A
    HC -->|"MenuPlan"| A
    A -->|"over budget?"| Negotiation
    Negotiation -->|"flagged_items"| HC
    A -->|"CostReport"| LL
    A -->|"CostReport"| SM
    LL -->|"LogisticsPlan"| FP["📋 FinalPlan"]
    SM -->|"StockReport"| FP
    FP --> CDB
    FP --> UI

    Agents <-->|"GPT reasoning"| AOI
    HC <-->|"recipe RAG"| AIS
    A <-->|"pricing RAG"| AIS
    Memory <-->|"order history"| CDB
    FP -.->|"persist"| Blob

    Framework -.->|"wraps"| Agents
    Framework -.->|"drives"| Negotiation
```

---

## Negotiation Detail

```mermaid
sequenceDiagram
    participant Orch as Orchestrator
    participant AC as AccountantAgent (AutoGen)
    participant HC as HeadChefAgent (AutoGen)
    participant Chef as Head Chef (SK)
    participant Acct as Accountant (SK)

    Orch->>AC: Start negotiation — budget exceeded by ₱X
    loop RoundRobinGroupChat (max 3 rounds)
        AC->>HC: {"flagged_dishes": ["Beef Kare-Kare"], "reasoning": "..."}
        HC->>AC: {"reformulated_dishes": ["Chicken Adobo"], "rationale": "..."}
        Note over AC: reformulation_exhausted=True → break early
    end
    AC->>Orch: flagged_items list
    Orch->>Chef: revise_menu_plan(flagged_items)
    Chef->>Orch: Updated MenuPlan
    Orch->>Acct: run_accountant(updated menu)
    Acct->>Orch: Final CostReport
```

---

## Agent Communication Protocol

```mermaid
classDiagram
    class AgentMessage {
        +MessageHeader header
        +Any payload
        +MessageMetadata metadata
        +MessageSignature signature
    }
    class MessageHeader {
        +UUID message_id
        +str agent_id
        +str target_agent
        +datetime timestamp
        +str message_type
        +str version
    }
    class MessageMetadata {
        +float confidence_score
        +str priority
        +int retry_count
        +List~str~ dependencies
    }
    class MessageSignature {
        +str hash
        +str session_id
    }
    AgentMessage --> MessageHeader
    AgentMessage --> MessageMetadata
    AgentMessage --> MessageSignature
```

---

## Azure Services Map

| Service | Resource | Role | Status |
|---|---|---|---|
| Azure OpenAI GPT-4o | foundry-jmagno-2026 | All 5 agent reasoning calls | ✅ Active |
| Azure AI Search | search-jmagno-2026 · catering-knowledge-base | RAG — 70 documents (68 recipes + pricing + suppliers) | ✅ Active |
| Azure Cosmos DB | cosmos-jmagno-2026 · catering-orders | Order persistence + long-term memory queries | ✅ Active |
| Azure Blob Storage | storagejmagno2026 | Document storage layer | ✅ Active |

---

## Key Architecture Invariants

| Rule | Enforcement |
|---|---|
| Allergies never violated | `_IMMUTABLE_KEYS` in SharedMemory + post-AI code check |
| Budget status never manipulated | Deterministic math only — GPT never touches cost calc |
| Every GPT call degrades gracefully | `_call_with_retry()` + static fallback on all 5 agents |
| AutoGen never breaks the pipeline | `try/except` fallback to manual negotiation loop |
| Dietary flags immutable mid-pipeline | SharedMemory rejects writes to protected keys |
