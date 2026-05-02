
# 🍽️ Smart Catering Agent
### AI-Powered Multi-Agent System for Autonomous Catering Operations
**Code Without Barriers Hackathon 2026 — ASEAN Edition**  
Problem Statement 1 — iNextLabs  
Participant: Jennylyn Magno | Solo | Philippines

---

## The Problem

Catering businesses manage complex, interconnected workflows — customer intake, menu planning, cost control, logistics, and inventory — often handled manually or across disconnected tools. The result: 30% food waste from poor planning, budget overruns from inconsistent pricing, delivery delays from logistics gaps, and miscommunication that compounds at every step.

A traditional app reacts after things go wrong. A multi-agent system prevents problems before they happen — each specialist focused on one job, all collaborating in real time.

---

## The Solution

Smart Catering Agent is a fully autonomous multi-agent AI system where five specialized agents collaborate to produce a complete, optimized catering plan from a single customer request — with no manual intervention between agents.

> *"The Head Chef proposes Beef Kaldereta. The Accountant flags it as a cost driver. They negotiate. The Head Chef reformulates. The Logistics Lead calculates staffing. The Stock Manager plans procurement. All automatically."*

---

## Architecture

```
Customer Request (raw text)
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI REST API                        │
│         POST /api/v1/catering/order                  │
│    [X-API-Key auth] [Pydantic validation]            │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│           Orchestration Engine                       │
│     Semantic Kernel + AutoGen coordination           │
│     SharedMemory · Retry Logic · Audit Trail         │
└──┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Con-  │ │Head    │ │Accoun- │ │Logis-  │ │Stock   │
│cierge│→│Chef    │→│tant    │→│tics    │→│Manager │
└──────┘ └────────┘ └────────┘ └────────┘ └────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         Cosmos DB   AI Search   Azure OpenAI
```

---

## The Five Agents

### 🧑‍💼 Agent 1 — The Concierge
**Role:** Customer intake and intent parsing

Receives raw customer text and extracts a fully validated 
event specification. Distinguishes hard dietary constraints 
(applied to entire menu) from soft preferences (noted for 
consideration). Applies deterministic code fallbacks for all 
required fields. Prompt injection protected.

**Technology:** GPT-4o (temp 0.0) · Pydantic validation · 
Hard constraint enforcement in code

---

### 👨‍🍳 Agent 2 — The Head Chef
**Role:** Menu design and recipe selection

Queries the RAG knowledge base for cuisine-appropriate 
candidates, then uses GPT-4o to select dishes that balance 
variety, dietary compliance, and occasion appropriateness. 
Applies Menu Engineering quadrant thinking 
(Stars/Plow Horses/Puzzles/Dogs). During budget negotiation, 
follows a reformulation priority order: Protein Down-Tiering 
→ Portion Re-balancing → Service Style adjustment → Dish 
removal as last resort only.

**Technology:** GPT-4o (temp 0.8) · Azure AI Search RAG · 
49 individual recipe documents · Post-AI allergy safety check

---

### 💰 Agent 3 — The Accountant
**Role:** Cost calculation and budget compliance

Calculates ingredient costs from RAG pricing data, applies 
a 7% industry-standard cost buffer, adds fixed labor and 
overhead. When over budget, uses pre-computed variance 
analysis before calling GPT-4o to reason about which dishes 
to flag — minimum flagging, reformulation before removal. 
Negotiates with Head Chef up to 3 rounds.

**Technology:** GPT-4o (temp 0.0) · RAG pricing · 
Deterministic math in code · GPT reasoning for soft 
judgment only

---

### 🚚 Agent 4 — The Logistics Lead
**Role:** Timeline planning and staffing calculation

Interprets event notes using GPT-4o with industry staffing 
ratios (plated 1:10-12, buffet 1:20-25, full bar 1:35) and 
T-minus Critical Path Method. Calculates exact staff numbers 
for each specific event.

**Technology:** GPT-4o (temp 0.3) · Deterministic backward 
time calculation · Industry ratios in prompt

---

### 📦 Agent 5 — The Stock Manager
**Role:** Inventory check and procurement planning

Checks inventory levels against mock warehouse data, 
generates procurement lists, identifies waste risk items 
using FIFO/yield reasoning, and explains supplier selection 
rationale. Both GPT calls run concurrently via 
asyncio.gather() with 8s timeout and graceful degradation.

Note: Inventory data is currently loaded from a local mock 
inventory file (data/mock_inventory.json) simulating 
warehouse stock levels. In production, this would be 
replaced by real-time Cosmos DB inventory queries — the 
Cosmos connection is already in place for order persistence 
and long-term memory.

**Technology:** GPT-4o · asyncio.gather() concurrent calls · 
Deterministic math for quantities

---

## Architecture Principle

> **Hard constraints live in code, always. Soft judgments 
> belong to GPT. Math belongs to code. Every GPT call 
> degrades gracefully.**

- Dietary restrictions and allergies: enforced in code 
  after every AI call
- Budget status: accurately reported, never manipulated 
  by AI
- Cost calculation: deterministic math, never delegated 
  to GPT
- Staffing numbers: calculated by code from GPT-interpreted 
  service style
- All GPT calls: graceful fallback to deterministic results 
  on any failure

This aligns directly with iNextLabs Key Success Factor: 
*"Rules-based logic guides decisions with AI insights; 
agents act autonomously within established guardrails."*

---

## Agent Communication Protocol

Every agent-to-agent message follows the structured 
JSON protocol:

```json
{
  "header": {
    "message_id": "uuid-...",
    "agent_id": "head_chef",
    "target_agent": "accountant",
    "timestamp": "2026-05-01T10:00:00Z",
    "message_type": "menu_plan",
    "version": "1.0"
  },
  "payload": { ... },
  "metadata": {
    "confidence_score": 0.95,
    "priority": "high",
    "retry_count": 0
  },
  "signature": {
    "hash": "sha256-...",
    "session_id": "session-..."
  }
}
```

SHA-256 audit hash on every message. Every agent action 
logged with agent_id, action, status, and timestamp.

---

## Azure Services

| Service | Resource | Role in System |
|---|---|---|
| Azure OpenAI GPT-4o | foundry-jmagno-2026 | Powers all 5 agent reasoning calls |
| Azure AI Search | search-jmagno-2026 | RAG knowledge base — 51 documents (49 recipes + pricing + suppliers) |
| Azure Cosmos DB | cosmos-jmagno-2026 | Order persistence + long-term memory queries |
| Azure Blob Storage | storagejmagno2026 | Document storage layer |

---

## Microsoft Agent Framework

Agents are registered as a Semantic Kernel plugin and 
invoked via `kernel.invoke()`. AutoGen's AssistantAgent 
is used for orchestrator coordination. Core negotiation 
and pipeline sequencing logic is implemented in the 
orchestration engine, aligned with Microsoft Agent 
Framework patterns.

**Present:** `CateringAgentsPlugin` with `@kernel_function` 
decorators, AutoGen `AssistantAgent` 

**Production roadmap:** AutoGen GroupChat for dynamic agent 
routing, SK Planner for adaptive pipeline sequencing, 
SK Memory Plugins for persistent agent context

---

## Bonus Features Implemented

| Feature | Implementation |
|---|---|
| RAG Knowledge Base | 51 documents in Azure AI Search — 49 individual recipe docs + pricing + suppliers |
| Shared Memory | Immutable dietary/allergy flags across all agents — cannot be overwritten mid-pipeline |
| Long-Term Memory | query_past_orders() queries Cosmos for past similar events, injects context into Head Chef and Accountant prompts |
| Real-Time Adaptation | /adapt endpoint re-runs impacted pipeline on guest count, dietary, or budget change |
| Multi-Event Optimization | Multi-order endpoint with shared procurement across concurrent events |
| Retry Logic | _call_with_retry() wraps all 5 agent calls — up to 3 attempts on transient failures |

---

## Correctness Test Suite

22/23 automated correctness tests passing across 6 sections:

| Section | Result |
|---|---|
| Section 1: Dietary and allergy enforcement | 7/7 ✅ |
| Section 2: Menu variety | 1/1 ✅ |
| Section 3: Special notes handling | 3/3 ✅ |
| Section 4: Bonus features | 5/5 ✅ |
| Section 5: Cost scaling | 1/1 ✅ |
| Section 6: Edge cases | 5/6 ⚠️ |

Edge Case 6 (very long special notes) passes functionally 
and produces correct output. Timing is marginal under Azure 
free tier latency — the pipeline includes a Cosmos 
long-term memory query which adds latency depending on 
Azure response time. Production fix: provisioned throughput.

---

## Environment Variables

Create `.env` in project root (never commit this file):

```
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
COSMOS_ENDPOINT=your_cosmos_endpoint
COSMOS_KEY=your_cosmos_key
COSMOS_DATABASE=smart-catering
COSMOS_CONTAINER=catering-orders
AZURE_SEARCH_ENDPOINT=your_search_endpoint
AZURE_SEARCH_KEY=your_search_key
API_KEY=your_api_key_for_callers
REACT_APP_API_KEY=your_api_key_for_callers
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection_string
```

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- Azure services configured (see Environment Variables)

### Backend
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt

venv\Scripts\python.exe -m uvicorn main:app \
  --host 127.0.0.1 --port 8001
```

### Frontend
```bash
cd frontend
npm install
npm start
```

### Run Correctness Suite
```bash
venv\Scripts\python.exe -m tests.test_correctness
```

### Deployment Note
System runs locally connecting to Azure backend services 
(OpenAI, Cosmos DB, AI Search). App Service deployment 
blocked by free subscription quota — current setup 
demonstrates full Azure integration with local compute. 
Production deployment target: Azure App Service or 
Azure Container Apps.

---

## Known Limitations

1. **Response time** — 20-120s under Azure free tier due 
   to multiple sequential GPT calls. Production fix: 
   provisioned throughput.
2. **Knowledge base dishes only** — dishes outside 
   recipes.json are substituted with nearest match.
3. **Fixed labor rate** — PHP 150/guest flat rate. 
   Production would vary by service style and duration.
4. **Mock inventory** — Stock Manager uses local mock 
   data. Production path: real-time Cosmos DB inventory.
5. **Local execution** — App Service blocked by free 
   subscription quota. Functionally identical to cloud 
   deployment for demo purposes.

---

## Project Structure

```
smart-catering-agent/
├── agents/
│   ├── concierge.py        ← Agent 1: Customer intake
│   ├── head_chef.py        ← Agent 2: Menu design
│   ├── accountant.py       ← Agent 3: Cost and budget
│   ├── logistics.py        ← Agent 4: Timeline and delivery
│   └── stock_manager.py    ← Agent 5: Inventory and procurement
├── orchestrator/
│   └── engine.py           ← Coordinates all agents, retry logic
├── utils/
│   ├── azure_client.py     ← Azure SDK connections
│   ├── cosmos_store.py     ← Cosmos DB operations + long-term memory
│   └── logger.py           ← Structured logging
├── knowledge_base/
│   ├── recipes.json        ← 49 recipes, 9 categories
│   ├── pricing.json        ← Ingredient pricing
│   └── suppliers.json      ← Supplier data
├── frontend/src/           ← React UI
├── tests/
│   └── test_correctness.py ← 22/23 automated tests
└── scripts/
    └── setup_search_index.py ← Azure AI Search index builder
```

---

## AI Tools Disclosure

This project was built with assistance from **Claude 
(Anthropic)** for architecture reasoning, prompt 
engineering, code review, and implementation guidance. 
All code was executed, tested, and verified by the 
participant. Windsurf (Codeium) was used for code 
execution and file editing. As required by hackathon 
rules, all code was developed during the hackathon 
period (April 2 – May 3, 2026).

---

*Built for Code Without Barriers Hackathon 2026 — 
ASEAN Edition*  
*Participant: Jennylyn Magno · Philippines · Solo submission*

---

After creating the file, paste the first 20 lines 
back so I can verify. Do not commit yet.
