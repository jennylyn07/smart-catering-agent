
# 🍽️ Smart Catering Agent
### AI-Powered Multi-Agent Pipeline for Intelligent Catering Operations
**Code Without Barriers Hackathon 2026 — ASEAN Edition**  
Problem Statement 1 — iNextLabs  
Participant: Jennylyn Magno | Solo | Philippines

---

## The Problem

Catering businesses manage complex, interconnected workflows — customer intake, menu planning, cost control, logistics, and inventory — often handled manually or across disconnected tools. The result: 30% food waste from poor planning, budget overruns from inconsistent pricing, delivery delays from logistics gaps, and miscommunication that compounds at every step.

A traditional app reacts after things go wrong. A multi-agent system prevents problems before they happen — each specialist focused on one job, all collaborating in real time.

---

## The Solution

Smart Catering Agent is a multi-agent AI system where five specialized agents operate as a coordinated pipeline to produce a complete, optimized catering plan from a single customer request — with no manual intervention required between agents.

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
│  Semantic Kernel (AzureChatCompletion + Plugin)      │
│  SharedMemory · Retry Logic · Audit Trail            │
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
68 individual recipe documents · Post-AI allergy safety check ·
Hardcoded `NUTRITION_LOOKUP` (68 dishes) → per-serving kcal/protein/carbs/fat on every `MenuItem`

---

### 💰 Agent 3 — The Accountant
**Role:** Cost calculation and budget compliance

Calculates ingredient costs from RAG pricing data, applies
a **7% cost buffer** (`ingredients_cost × 0.07`) as industry-standard
protection against price volatility, adds PHP 150/guest labor
and fixed overhead. When over budget, uses pre-computed variance
analysis before calling GPT-4o to reason about which dishes
to flag — minimum flagging, reformulation before removal.
Negotiates with Head Chef up to 3 rounds. Outputs a
**recommended selling price** (total cost ÷ 0.70) and
**estimated profit margin (30% target)** for profitability
forecasting alongside the budget compliance report.

**Technology:** GPT-4o (temp 0.0) · RAG pricing ·
Deterministic math in code · GPT reasoning for soft
judgment only · Profitability margin calculation in code

---

### 🚚 Agent 4 — The Logistics Lead
**Role:** Timeline planning and staffing calculation

Interprets event notes using GPT-4o with industry staffing
ratios (plated 1:10-12, buffet 1:20-25, full bar 1:35) and
T-minus Critical Path Method. Calculates exact staff numbers
for each specific event. Derives a **Gantt chart**
(`gantt_chart: List[GanttTask]`) directly from the CPM
timeline, providing machine-readable start/end/duration
segments for each preparation milestone. The `gantt_chart`
field is included in the API response JSON for every order
and is designed for integration with external project
management tools. The current frontend dashboard renders the
CPM timeline as a table; visual Gantt chart rendering is on
the production roadmap.

**Technology:** GPT-4o (temp 0.3) · Deterministic backward
time calculation · Industry ratios in prompt · Gantt
derivation in code (`_derive_gantt()`)

---

### 📦 Agent 5 — The Stock Manager
**Role:** Inventory check and procurement planning

Checks inventory levels against mock warehouse data,
generates procurement lists, identifies waste risk items
using FIFO/yield reasoning, and explains supplier selection
rationale. Both GPT calls run concurrently via
asyncio.gather() with 8s timeout and graceful degradation.
**Runs in parallel with the Logistics Lead** — both agents
receive the cost report and execute simultaneously via
`asyncio.gather()` in the orchestration engine, reducing
total pipeline latency.

Note: Inventory data is loaded from Azure Cosmos DB first
(container: catering-inventory). If Cosmos inventory is
unavailable or empty, the agent falls back to a local mock
inventory file (data/mock_inventory.json).

**Technology:** GPT-4o · asyncio.gather() concurrent calls ·
Deterministic math for quantities · Parallel orchestration
with Logistics Lead

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
agents act within established guardrails."*

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
| Azure OpenAI GPT-4o | foundry-jmagno-2026-resource | Powers all 5 agent reasoning calls |
| Azure AI Search | search-jmagno-2026 | RAG knowledge base — 70 documents (68 recipes + pricing + suppliers) |
| Azure Cosmos DB | cosmos-jmagno-2026 | Order persistence + historical order context queries |
| Azure Blob Storage | storagejmagno2026 | Provisioned — not in active pipeline (future document storage layer) |

---

## Microsoft Agent Framework

Agents are implemented as a **Semantic Kernel plugin** (`CateringAgentsPlugin`)
where each agent is a `@kernel_function`. The orchestration engine:
1. Builds a `Kernel` initialized with `AzureChatCompletion` at startup
2. Registers `CateringAgentsPlugin` on the kernel
3. Invokes every agent via `kernel.invoke(plugin_name, function_name, ...)` 
4. Falls back to direct async call if SK is unavailable

**Semantic Kernel:** `CateringAgentsPlugin` with `@kernel_function` decorators
invoked via `kernel.invoke()` for all 5 agents. Startup import takes ~20s on
Windows; all subsequent requests are unaffected.

**AutoGen GroupChat:** `Accountant` + `HeadChef` agents run in a live
`RoundRobinGroupChat` (≤3 rounds, `MaxMessageTermination`) via **autogen-ext 0.7.5** when the plan
exceeds budget. `AzureOpenAIChatCompletionClient` powers both agents.
Graceful fallback to manual negotiation loop on any AutoGen exception.

**Production roadmap:** SK Planner for adaptive pipeline sequencing,
SK Memory Plugins for persistent agent context


---

## Bonus Features Implemented

| Feature | Implementation |
|---|---|
| RAG Knowledge Base | 70 documents in Azure AI Search — 68 individual recipe docs + pricing + suppliers |
| Shared Memory | Immutable dietary/allergy flags across all agents — cannot be overwritten mid-pipeline |
| Historical Order Context | query_past_orders() retrieves past similar events from Cosmos DB, injects context into Head Chef and Accountant prompts |
| Order History UI | Full order history tab with expandable plan detail — persisted in Cosmos DB |
| Budget Suggestion | When plan exceeds budget, Accountant outputs suggested_budget_php — shown in UI Cost tab |
| Profitability Forecast | recommended_selling_price_php + estimated_margin_percent (30% target) in every CostReport |
| Nutritional Data | Per-serving kcal/protein/carbs/fat on every MenuItem via NUTRITION_LOOKUP (68 dishes) |
| Gantt Chart | GanttTask list derived from CPM timeline in every LogisticsPlan |
| Real-Time Adaptation | **"✏️ Modify This Plan" panel** (UI) — re-runs only impacted agents on guest count, dietary, or budget change; updated plan replaces current results in-place |
| Multi-Event Optimization | Multi-order endpoint with shared procurement across concurrent events |
| Parallel Agent Execution | Logistics Lead + Stock Manager run concurrently via asyncio.gather() |
| Retry Logic | _call_with_retry() wraps all 5 agent calls — up to 3 attempts on transient failures |

---

## Integration Test Suite

23/23 integration checks passing across 6 sections
(these are end-to-end smoke tests that validate pipeline 
behavior — dietary enforcement, cost scaling, edge case 
handling — not unit tests of individual computations):

| Section | Result |
|---|---|
| Section 1: Dietary and allergy enforcement | 7/7 ✅ |
| Section 2: Menu variety / non-determinism | 1/1 ✅ |
| Section 3: Special notes handling | 3/3 ✅ |
| Section 4: Bonus features | 5/5 ✅ |
| Section 5: Cost scaling reality check | 1/1 ✅ |
| Section 6: Edge cases | 6/6 ✅ |

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
- Python 3.12+
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

1. **Startup time** — Backend imports Semantic Kernel and AutoGen at
   startup, which takes ~20s on Windows. Once ready, the server
   handles all requests normally. No impact on per-request latency.
2. **Response time** — 60-180s under Azure free tier due
   to multiple sequential GPT-4o calls. Logistics and Stock Manager
   now run in parallel (asyncio.gather), reducing the
   final two stages. Production fix: provisioned throughput.
3. **Knowledge base dishes only** — dishes outside
   recipes.json are substituted with nearest match.
4. **Fixed labor rate** — PHP 150/guest flat rate.
   Production would vary by service style and duration.
5. **Inventory source** — Stock Manager queries Cosmos DB
   (`catering-inventory` container, 33 seeded items) first.
   Falls back to local `data/mock_inventory.json` if Cosmos
   is unavailable. Production would have live inventory writes
   after each procurement list is generated.
6. **Local execution** — App Service blocked by free
   subscription quota. Functionally identical to cloud
   deployment for demo purposes.
7. **Agent progress simulation** — The UI shows live
   elapsed time and time-based agent advancement during
   processing. True per-agent real-time status requires
   an async pipeline (production roadmap).
8. **Knowledge base constraint coverage** — The 68-recipe
   knowledge base covers Filipino, Western, Chinese, and
   International cuisine. Applying 3+ simultaneous hard
   constraints (e.g., Gluten-free + Western, or
   Vegetarian + Halal + Nuts + Seafood allergy) eliminates
   most candidates from the filter, potentially yielding
   fewer than 5 dishes. The UI surfaces this honestly as a
   warning banner. Expanding `knowledge_base/recipes.json`
   with more constraint-compatible recipes would improve
   coverage.
9. **Head Chef reasoning on highly constrained menus** —
   Per-dish GPT reasoning (temp 0.8) may return empty
   rationale fields when fewer than 5 recipes match the
   combined constraints. Per the architecture principle
   (*"Soft judgments belong to GPT"*), the system does
   **not** fabricate reasoning from code. It falls back
   to a plain honest acknowledgement: *"Menu curated
   from the knowledge base to satisfy the event's
   dietary and allergy constraints. Per-dish reasoning
   was not available for this selection."*
   Dish selection and constraint enforcement are always
   deterministic code — only the explanatory text is
   affected.

---

## Production Roadmap

| Feature | Description | Priority |
|---|---|---|
| SK Planner | Dynamic pipeline generation — agents register capabilities, Planner decides execution order | Medium |
| Real-Time SSE | FastAPI BackgroundTasks + asyncio.Queue per session — true per-agent progress streaming | Medium |
| Provisioned Throughput | Sub-5s per GPT-4o call — 8-20s total pipeline vs current 60-180s | High |
| Evals Framework | RAGAS/custom harness for prompt quality A/B testing | Low |
| Live Inventory Updates | Subtract purchased quantities from Cosmos inventory after each order | Low |
| Azure App Service | Container deployment when subscription quota allows | Medium |

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
│   ├── engine.py              ← Coordinates all agents, retry logic, AutoGen integration
│   └── autogen_negotiation.py ← AutoGen RoundRobinGroupChat budget negotiation
├── utils/
│   ├── azure_client.py     ← Azure SDK connections
│   ├── cosmos_store.py     ← Cosmos DB operations + historical order context
│   └── logger.py           ← Structured logging
├── knowledge_base/
│   ├── recipes.json        ← 68 recipes, 9 categories
│   ├── pricing.json        ← Ingredient pricing
│   └── suppliers.json      ← Supplier data
├── frontend/src/           ← React UI
├── tests/
│   └── test_correctness.py ← 23/23 integration checks
└── scripts/
    └── setup_search_index.py ← Azure AI Search index builder (70 docs)
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

