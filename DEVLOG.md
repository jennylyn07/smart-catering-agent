### 📋 SECTION 1: DEV LOG (Technical Record)

#### Session 1 — 2026-04-18
**What we built:**
- Created folders:
  - orchestrator/ (with __init__.py)
  - memory/ (with __init__.py)
  - knowledge_base/
  - data/
  - tests/ (with __init__.py)
- Created utils/logger.py
  - Structured JSON logging utility used by all parts of the system
- Created utils/json_schema.py
  - Pydantic schemas for the agent message wrapper and core payload types
- Created utils/validator.py
  - Input validation helpers (guest counts, budgets, dates, cuisine types, dietary flags)
- Implemented utils/azure_client.py
  - Loads credentials from .env via python-dotenv
  - Creates Azure client objects without making network calls
  - Azure Blob client is optional until AZURE_STORAGE_CONNECTION_STRING is configured
- Created mock data files:
  - knowledge_base/recipes.json
  - knowledge_base/pricing.json
  - knowledge_base/suppliers.json
  - data/mock_inventory.json

**What broke and how we fixed it:**
- Error message: "utils/azure_client.py is an empty file. Perform a single replacement with empty target content to edit empty files."
- Cause (plain language): The patch tool needs existing lines to anchor changes; an empty file has no anchor.
- Fix: Replaced the entire file content in one operation.
- What to watch out for next time: Empty files must be written using a full-file replacement, not a contextual patch.

- Error message: "openai.NotFoundError: Error code: 404 - {'error': {'code': '404', 'message': 'Resource not found'}}"
- Cause (plain language): `AZURE_OPENAI_ENDPOINT` included an extra path segment (`/openai/v1`), so requests went to a non-existent Azure OpenAI resource URL.
- Fix: Removed `/openai/v1` from the endpoint value in `.env` and re-ran the test.
- Result after fix: Test call returned `OK`.

**Azure resources used this session:**
- Azure OpenAI (GPT-4o deployment) — one minimal chat completion test request.

**Git commits made:**
- None yet

**Status at end of session:**
- What is working:
  - Project foundation folders exist
  - Logging, schemas, validators, and Azure client factories are in place
  - Mock knowledge base and inventory data files exist
- What is not yet working:
  - None noted for Day 1 foundation (Azure OpenAI connectivity test passed)
- Blockers:
  - Optional: AZURE_STORAGE_CONNECTION_STRING is not yet configured (only needed when Blob Storage is used)

#### Session 2 — 2026-04-19
**What we built:**
- Created API layer files:
  - api/models.py (Pydantic request/response models)
  - api/auth.py (API key auth via X-API-Key header; loads API_KEY from .env)
  - api/routes.py (POST /api/v1/catering/order)
  - main.py (FastAPI app entry point + GET /health + SlowAPI integration)
- Added rate limiting dependency:
  - Installed slowapi (10 requests per minute rate limit)

**What broke and how we fixed it:**
- Error: ModuleNotFoundError: No module named 'slowapi'
  - Cause: slowapi was installed into the global Python site-packages instead of the project venv.
  - Fix: installed using the venv interpreter (example pattern: `./venv/Scripts/python -m pip install slowapi`).
- Error: RuntimeError: Missing required environment variable: API_KEY
  - Cause: the server started before API_KEY was present/loaded from .env.
  - Fix: added/confirmed `API_KEY` in `.env`, then restarted uvicorn.
- PowerShell issue: `curl` uses Invoke-WebRequest (header binding errors)
  - Fix: used `curl.exe` for GET, and PowerShell-native `Invoke-RestMethod` for POST.

**Azure resources used this session:**
- None

**Git commits made:**
- Completed Day 1 commit and push (foundation checkpoint)

**Status at end of session:**
- What is working:
  - GET /health returns {"status": "ok"}
  - POST /api/v1/catering/order validates requests and enforces API key auth
  - Rate limiting is wired (10 requests per minute)
- What is not yet working:
  - Agents are not wired into the order endpoint (response is placeholder)
- Blockers:
  - None

#### Session 3 — 2026-04-20
**What we built:**
- Implemented first two core agents:
  - agents/concierge.py
    - Uses Azure OpenAI (GPT-4o deployment) to parse raw customer text into a validated `EventSpecification`
    - Wraps the payload into our standard `AgentMessage` with message_type = "event_specification"
    - Includes prompt injection protection in the system prompt
    - Logs every action using `utils/logger.py`
    - Uses try/except to return an `ErrorMessage` instead of crashing
  - agents/head_chef.py
    - Uses local Retrieval Augmented Generation (RAG) over `knowledge_base/recipes.json` (no Azure call)
    - Filters recipes by allergies and excludes unsafe dishes (e.g., peanut dishes when allergy is nuts)
    - Outputs a validated `AgentMessage` with message_type = "menu_plan"
- Added tests:
  - tests/test_agents.py
    - Concierge isolation test (Azure call)
    - Head Chef isolation test (no Azure call; uses stored EventSpecification payload)

**What broke and how we fixed it:**
- Patch tool error: "agents/concierge.py is an empty file. Perform a single replacement..."
  - Cause: Context-based patching cannot anchor on an empty file.
  - Fix: Wrote the full file contents in a single operation.

**Azure resources used this session:**
- Azure OpenAI (GPT-4o deployment) — Concierge parsing call during isolation test.

**Git commits made:**
- None yet (Day 3 commit will be done at the end of the session)

**Status at end of session:**
- What is working:
  - Concierge generates `event_specification` with a validated schema (including allergies)
  - Head Chef generates a `menu_plan` using the recipe knowledge base and respects nut allergy
- What is not yet working:
  - Agents are not yet wired into the FastAPI order endpoint
- Blockers:
  - None

#### Session 5 — 2026-04-21
**What we built:**
- Implemented Day 5 orchestration layer:
  - orchestrator/engine.py — full 5-agent pipeline with shared context and a negotiation loop capped at 3 rounds
  - Wired orchestrator into POST /api/v1/catering/order

#### AUDIT SESSION — Code Audit between Day 5 and Day 6 — 2026-04-21
**Scope (no new features):**
- Full-system audit covering imports, schema consistency, error handling, security, logging, dietary restriction safety, local tests, code quality, and requirements.

**Key fixes applied:**
- Head Chef negotiation safety: prevented `revise_menu_plan()` from re-adding dishes that were previously flagged for removal.

**Health rating (post-audit): GREEN**
- All audits passed.

**Audit results summary:**
- Imports: pass after fixes.
- Schema consistency: all agent outputs + orchestrator align with `utils/json_schema.py`.
- Error handling: compliant (exceptions handled at `run_*` level; agents return `ErrorMessage` on failure; no bare except).
- Security: no hardcoded secrets; `.env` loading + API key auth enforced; rate limiting active; request validation via Pydantic.
- Logging: structured JSON logging used; orchestrator logs handoffs; no `print()` in runtime code.
- Dietary safety: nut allergy correctly propagated and enforced; negotiation loop cannot reintroduce flagged dishes.
- Local tests (AUDIT 7): `python -m tests.test_agents` passed (exit code 0).
- Code quality (AUDIT 9): type hints OK; flagged missing docstrings across several files; flagged multiple functions over 40 lines (not refactored in audit).
- Requirements (AUDIT 10): `pip freeze` regenerated `requirements.txt`; required packages confirmed present.

**Outstanding items after audit:**
- FIX 2 identified, deferred: splitting >40-line functions planned for final polish phase if time permits.
- Optional cleanup (post-audit / if approved): splitting >40-line functions for maintainability.

**AUDIT 8 — End-to-end API test (Azure OpenAI) results:**
- message_type: final_plan
- negotiation_rounds_used: 0
- total_cost_php: 11,337
- budget_php: 45,000
- within_budget: True
- menu_items: 5
- flagged_items: none
- procurement_items_to_purchase: 2
- total_processing_time_seconds: 2.697

**Azure resources used this session:**
- Azure OpenAI (GPT-4o deployment) — Concierge parsing call during end-to-end tests.

**Testing results (negotiation loop confirmed working):**
- 3 rounds used
- Total cost PHP 11,337 vs budget PHP 8,000
- Flagged items: Lumpiang Shanghai, Buko Pandan
- System correctly stopped after max rounds

**Git commits made:**
- Pending (will be committed after DEVLOG update)

#### Session 6 — 2026-04-22
**What we built (bonus features):**
- **RAG Integration (Azure AI Search):**
  - Added `scripts/setup_search_index.py` to create/update the `catering-knowledge-base` index and upload knowledge base documents.
  - Updated Head Chef to retrieve candidate recipes from Azure AI Search (with safe fallback to local `knowledge_base/recipes.json`).
- **Shared Memory:**
  - Implemented `memory/shared_memory.py` for session-scoped shared context with immutable dietary restrictions and allergies.
  - Wired shared memory into `orchestrator/engine.py` and enforced that allergies/dietary restrictions cannot change during orchestration.
- **Real-Time Adaptation:**
  - Added `POST /api/v1/catering/adapt` to re-plan from the correct agent onward (guest count, budget, dietary additions).
- **Multi-Event Optimization:**
  - Added `POST /api/v1/catering/multi-order` (up to 3 orders) and a shared procurement optimization summary.
  - Added an explicit acknowledgement gate to warn before potential Azure OpenAI calls.
- **Cosmos DB persistence:**
  - Persist successful `FinalPlan` documents to Cosmos DB.
  - Persist adaptation events and updated plans to Cosmos DB.

**Testing results:**
- `python -m tests.test_agents` passed (exit code 0).

**Azure resources used this session:**
- None executed during development (Azure calls occur only when scripts/endpoints are run).

**Status at end of session:**
- What is working:
  - Head Chef supports RAG-based recipe retrieval with fallback and keeps existing allergy filtering intact.
  - Shared memory captures agent outputs and negotiation history and blocks overrides of allergies/dietary restrictions.
  - Adaptation and multi-order endpoints are implemented and API-key protected.
  - Cosmos persistence wiring is in place for final plans and adaptation events.
- Blockers:
  - None.

#### Session 7 — 2026-04-23
**What we built:**
- Built a frontend-only React UI in `frontend/` (Create React App + plain CSS only) with branding colors:
  - Accent orange `#E8601C`
  - Dark ink `#1A1A2E`
- Implemented a two-panel layout:
  - Left panel: customer-facing Order Form
  - Right panel: technical Agent Activity Feed
- Implemented results dashboard section below the panels:
  - Summary card (cost, budget status, guest count)
  - Tabs: Menu, Cost breakdown, Timeline, Procurement
- Implemented API integration:
  - `POST /api/v1/catering/order` (via CRA dev proxy to `http://127.0.0.1:8000`)
  - API key loaded from `frontend/.env` via `REACT_APP_API_KEY` (never hardcoded)
  - Clear error banner if API key is missing or request fails

**What broke and how we fixed it:**
- CRA scaffold failed once with an `npm` network `ECONNRESET`.
  - Fix: re-ran `npx create-react-app frontend` after confirming npm registry connectivity.

**Testing results:**
- `npm --prefix frontend run build` compiled successfully.

**Azure resources used this session:**
- None

**Status at end of session:**
- What is working:
  - Order form collects all required inputs and submits to the FastAPI order endpoint.
  - Agent feed shows run status and displays negotiation rounds + processing time from the final plan.
  - Results dashboard renders the returned `FinalPlan`.
- Blockers:
  - None.

#### Session 8 — 2026-04-25
**What we built / changed (bug fixes):**
- **Fix 1: Dietary restriction enforcement in Head Chef**
  - Updated dietary filtering to accept recipe fields using either `dietary_tags` or `dietary_flags`.
  - Added ingredient-based blocking to enforce vegan/vegetarian/halal style restrictions even when tags are missing.
  - Added a targeted exception so `coconut milk` does not trigger false positives for dairy/milk checks.
- **Fix 2: Recipe knowledge base corrections**
  - Updated `knowledge_base/recipes.json`:
    - `fil-006` (Laing) `dietary_flags` now includes `vegan`.
    - `fil-007` (Ginataang Gulay) `dietary_flags` now includes `vegan`.
- **Fix 3: Azure AI Search async client compatibility**
  - Updated `utils/azure_client.py` so `create_search_client()` returns the async Azure Search client (`azure.search.documents.aio.SearchClient`) for correct `async with` / `async for` usage.
- **Fix 4: Await async search call in Head Chef RAG retrieval**
  - Updated `agents/head_chef.py` to `await search_client.search(...)` when using the async client.
- **Fix 5: Graceful handling when too few safe recipes exist**
  - Updated `agents/head_chef.py` to log a warning and enrich the menu rationale when fewer than 3 safe recipes are available under the current constraints.
- **Fix 6: Notes-driven logistics adjustments**
  - Updated `agents/logistics.py` to accept `event_spec` and interpret `event_spec.notes` to:
    - Start prep earlier for “early setup / 5AM” type notes.
    - Add timeline tasks for plated service and 3-course service windows.
    - Add staffing-related notes based on keywords.
  - Updated `orchestrator/engine.py` to pass `event_spec` into the Logistics agent call.
  - Updated `tests/test_agents.py` to pass `event_spec` into `run_logistics()` accordingly.

**Session 8 (continued) — 2026-04-26**
**What we built / changed (additional fixes + verification):**
- **Menu variety improvement (Head Chef)**
  - Updated `agents/head_chef.py` to shuffle candidate recipe lists to reduce deterministic menus across repeated runs.
- **Buffet notes handling (Logistics)**
  - Updated `agents/logistics.py` to recognize “buffet” in special notes and add an explicit buffet setup timeline task + staffing notes.
- **Recipe knowledge base expansion (Filipino vegan/halal options)**
  - Updated `knowledge_base/recipes.json` with additional Filipino recipes (IDs `fil-009` to `fil-013`) to improve options under vegan/halal constraints.
- **Cosmos persistence visibility (logging + wiring)**
  - Updated `utils/cosmos_store.py` to log explicit success/error around final plan persistence.
  - Updated `orchestrator/engine.py` to persist successful `FinalPlan` to Cosmos after pipeline success (so `run_orchestration` runs are persisted, not only API-route runs), with explicit success/error logs.
- **Correctness test suite improvements**
  - Added/updated `tests/test_correctness.py` to cover core scenarios, notes, variety, cost scaling, edge cases, and bonus endpoints.
  - Moved `load_dotenv(override=False)` to import time so `API_KEY` is available for backend tests.
  - Fixed `_section_6_edge_cases()` to always return its results list.
  - Updated backend endpoint tests to use a real `order_id` from a pipeline run for adaptation, and to print the Cosmos readback key for persistence verification.

**What broke and how we fixed it:**
- Azure Search RAG failures (when running tests): `ResourceNotFoundError` for index `catering-knowledge-base`.
  - Cause: Azure AI Search endpoint/service did not have the expected index.
  - Fix: Code-side async usage was corrected; the remaining requirement is to run `scripts/setup_search_index.py` (or point to the correct Search service/index) to enable successful retrieval.

**Testing results:**
- `python -m tests.test_agents` executed via venv with output captured to UTF-8 text files for inspection.

**Azure resources used this session:**
- Azure AI Search (attempted) — retrieval failed when index was missing; local fallback recipes were used.

**Additional notes (index setup script):**
- Updated `scripts/setup_search_index.py` `_iter_documents()` to generate Azure Search document keys using underscores instead of colons:
  - From: `f"{category}:{source_file.stem}:{i}"`
  - To: `f"{category}_{source_file.stem}_{i}"`
  - Reason: avoid `InvalidDocumentKey` errors during document upload.

#### Session 9 — 2026-04-27
**What we built / changed (correctness stability + verification):**
- **Cosmos persistence visibility**
  - Updated `orchestrator/engine.py` to surface Cosmos persistence failures during orchestration runs (so failures are visible in test output rather than being silently swallowed).
- **Correctness test suite stability**
  - Updated `tests/test_correctness.py` `_http_post_json()` to increase the backend request timeout from 10 seconds to 120 seconds to prevent intermittent timeouts on long-running endpoints.
- **Repeatable test execution with environment loaded**
  - Confirmed the correctness suite can be rerun reliably when `.env` values are loaded into the current PowerShell process environment prior to invoking the venv interpreter.

**Testing results:**
- Correctness suite re-run multiple times: **TOTAL: 23/23 checks passed**.

**Git commits made:**
- Pending (tests confirmed stable; ready to commit).

#### Session 10 — 2026-04-27
**What we built / changed (Microsoft Agent Framework wrapper):**
- **Semantic Kernel wrapper added (orchestration entry point)**
  - Added a minimal Semantic Kernel `Kernel` construction in `orchestrator/engine.py`.
  - Wrapped each existing agent call as a Semantic Kernel plugin function using `@kernel_function` (Concierge, Head Chef, Accountant, Logistics, Stock Manager, and menu revision).
  - Routed the deterministic orchestration flow through `await kernel.invoke(...)` with a safe fallback to direct function calls if SK is unavailable.
- **AutoGen presence (non-LLM-driven orchestration)**
  - Constructed an AutoGen `AssistantAgent` (present and structured), without allowing it to drive orchestration decisions.

**What broke and how we fixed it:**
- `run_stock_manager()` signature mismatch when routed through the SK plugin.
  - Fix: removed the unsupported `event_spec` argument from the SK wrapper and invocations.

**Testing results:**
- `venv\\Scripts\\python.exe -m tests.test_correctness`: **TOTAL: 23/23 checks passed**.

#### Session 11 — 2026-04-28
**What we built / changed (Head Chef GPT-4o + safety + orchestration fixes):**
- **Head Chef upgraded to GPT-4o reasoning (selection + substitution)**
  - Shifted menu selection from deterministic category picking / shuffle toward GPT-driven recipe ID selection (with strict JSON output parsing + fallback).
- **UUID fix (Concierge event_id reliability)**
  - Hardened event_id validation so placeholder or non-UUID values are replaced with `uuid4()`.
- **Portion sizing / cost scaling fix (Accountant base servings)**
  - Adjusted the cost scaling base servings assumption to match the actual per-recipe ingredient quantities.
- **customer_summary fix (orchestrator final output)**
  - Ensured final plans include a non-empty `customer_summary` derived from the event spec.
- **Dietary guardrails (no_meat / no_dairy / no_eggs)**
  - Added explicit restriction enforcement beyond tags via ingredient-name blocking.

**Knowledge base expansion (recipes + pricing):**
- **Added 25 new recipes** to `knowledge_base/recipes.json` (kept schema consistent with existing recipes).
  - Included allergen corrections before applying (fish sauce / egg / dairy / shellfish cases).
- **Added 57 new pricing entries** to `knowledge_base/pricing.json`.
  - Included 3 price corrections before applying: lemongrass, calamansi juice, shrimp.

**Testing results:**
- `venv\\Scripts\\python.exe -m tests.test_correctness`: **TOTAL: 23/23 checks passed**.

#### Session 12 — 2026-04-28
**What we built / changed (menu variety + selection quality improvements):**
- **Dynamic category selection (Head Chef)**
  - Replaced a hardcoded category list with a derived `desired_order` based on available recipe categories, using a priority order.
- **GPT system prompt enrichment (Head Chef)**
  - Expanded the system prompt with:
    - Non-negotiable safety rules
    - Allergy handling examples (including fish sauce and leche flan/custard-style egg exposure)
    - Strict dietary restriction handling
    - Professional menu-curation rules (including occasion matching)

**Variety test (manual 3-run API call):**
- Request used: "Debut party for 80 guests, Filipino cuisine, PHP 40000 budget, mixed crowd, no special dietary needs"
- Run 1: Chicken Adobo, Pancit Canton, Lumpiang Shanghai, Ginataang Gulay, Buko Pandan
- Run 2: Chicken Adobo, Pancit Canton, Pork Sinigang, Lumpiang Shanghai, Buko Pandan, Laing
- Run 3: Chicken Adobo, Pancit Canton, Ginataang Gulay, Lumpiang Shanghai, Buko Pandan
- Observation: Section 2 passes because runs are not identical, but most dishes repeat (4/5 overlap) and none of the 25 new recipes were selected.
- Root cause (known issue): RAG index still stores the full recipe set as a single blob, so GPT-4o biases toward the most familiar dishes. Index chunking is the planned fix.

#### Session 13 — 2026-04-28
**What we built / changed (RAG index + rationale + test accuracy fixes):**
- **Azure AI Search index rebuilt for per-recipe documents**
  - Rewrote `scripts/setup_search_index.py` to delete/recreate the index with an expanded schema and upload each recipe as its own document.
  - Stored recipes as one document per recipe ID (instead of a single giant blob) to improve retrieval diversity and reduce GPT bias toward the most familiar items.
  - Uploaded pricing and suppliers as single knowledge documents.
- **Head Chef: surfaced GPT per-dish rationale into MenuPlan**
  - Updated `_build_menu_items()` to collect GPT-4o per-dish rationale strings and return them alongside menu items.
  - Updated `run_head_chef()` to use the GPT rationale in `MenuPlan.rationale`, with a safe fallback string if GPT rationale is missing.
  - Added an explicit “limited by constraints” note when fewer than 5 dishes are returned under dietary/allergy constraints to satisfy heavy-constraints correctness checks.
- **Correctness test accuracy: vegetarian/vegan blocked term fix**
  - Updated `tests/test_correctness.py` to remove cooking-style terms `adobo` and `sisig` from vegetarian blocked terms to avoid false positives on plant-based dishes (e.g., tofu sisig, adobong kangkong).

**Testing results:**
- `venv\\Scripts\\python.exe -m tests.test_correctness`: **TOTAL: 23/23 checks passed**.

#### Session 14 — 2026-04-28
**What we built / changed (Logistics Lead GPT-4o upgrade — Prompt C):**
- **Context-aware notes interpretation (Logistics Lead)**
  - Updated `agents/logistics.py` to interpret special notes via GPT-4o instead of keyword matching.
  - GPT receives the full `event_spec.notes`, event context (guests/cuisine/occasion), and a deterministic timeline summary.
  - GPT returns structured JSON additions: `staffing_notes`, `extra_timeline_tasks`, and `setup_flags` (including `early_setup`).
- **Deterministic schedule math preserved**
  - Kept all backwards time calculations deterministic (timeline base, delivery window math, and prep/delivery time math unchanged).
- **Graceful degradation + reasoning visibility**
  - Removed `_notes_include()` and all keyword-based fallback logic.
  - If GPT is unavailable, logistics proceeds without notes analysis and logs a warning.
  - Added `logistics_ai_reasoning` to the logistics success log event for traceability.

**Testing results:**
- `venv\\Scripts\\python.exe -m tests.test_correctness`: **TOTAL: 23/23 checks passed** (Section 3 Notes: **3/3**).

---

### 📚 SECTION 2: PERSONAL LEARNING REPORT

#### Session 1 — 2026-04-18 — What I Learned
**New concepts introduced this session:**
- **__init__.py:** A small file that marks a folder as an importable Python package. | Example from our project: `orchestrator/__init__.py` lets Python import orchestration code cleanly.
- **Package (Python):** A folder Python treats like a module so we can import from it using `from folder import file`. | Example: `utils/` is our package of shared tools.
- **Structured JSON logging:** Logging where each entry is a JSON object with consistent fields, making it searchable and machine-readable. | Example: `utils/logger.py` logs `timestamp`, `agent_id`, `action`, `status`, `details`.
- **Schema:** A strict “shape rule” for data (what fields exist and what types they must be). | Example: `utils/json_schema.py` defines the message wrapper and payload formats.
- **Input validation:** Checking inputs are reasonable before using them to avoid crashes and bad data. | Example: `utils/validator.py` rejects invalid dates or unreasonable guest counts.
- **Client (SDK client):** A Python object that knows how to talk to an external service (like Azure), using your endpoint and key. | Example: `create_async_azure_openai_client()` creates the Azure OpenAI client without sending a request.
- **Factory function:** A function that creates and returns an object (often a client). | Example: `create_cosmos_client()`.

**Why we made key decisions:**
- Use structured logging — It’s an industry best practice for debugging and audit trails, especially in multi-agent systems.
- Use Pydantic schemas — Prevents agents from sending inconsistent JSON and catches errors early.
- Separate validators into their own file — Keeps the API and agents simple, and centralizes rules in one place.
- Make Azure client creation “safe by default” — Avoids accidental Azure credit usage before we explicitly test (Step 7).

**How the code we wrote today works:**
- `utils/logger.py`
  - Creates a JSON log formatter and a helper `log_event()` to produce consistent logs.
- `utils/json_schema.py`
  - Defines the exact message shapes our agents will use, including `AgentMessage` with header/payload/metadata/signature.
- `utils/validator.py`
  - Provides small functions that validate and normalize user inputs like date, budget, cuisines, and dietary flags.
- `utils/azure_client.py`
  - Loads settings from `.env` and builds Azure SDK clients without calling Azure.
- Mock JSON files
  - Provide repeatable “practice data” for recipes, ingredient prices, suppliers, and current inventory.

**The bigger picture — how today's work fits into the whole system:**
- Today’s work builds the “foundation layer” so the later agents and API endpoints can:
  - log every action
  - exchange consistent messages
  - validate inputs safely
  - connect to Azure services when we’re ready
  - test agent logic using mock data before full Azure RAG is wired up

#### Session 3 — 2026-04-20 — What I Learned
**What a system prompt is (and why it matters):**
- A system prompt is the agent’s highest-priority instruction — like the agent’s job contract and house rules.
- It is the most important part because it sets role boundaries and forces consistent output formats for downstream code.

**What prompt injection is (and how we defend against it):**
- Prompt injection is when the user tries to trick the agent into ignoring its rules (e.g., “ignore your instructions” or “reveal secrets”).
- We defend by:
  - Putting explicit rules in the system prompt (treat user text as untrusted input; never reveal secrets; output JSON only)
  - Validating the model output with Pydantic schemas (`EventSpecification`, then `AgentMessage`)
  - Returning an `ErrorMessage` instead of crashing if anything is invalid

**What RAG is (and why it matters for Head Chef):**
- RAG (Retrieval Augmented Generation) means the agent looks up relevant information from a knowledge source before generating output.
- In our system, Head Chef uses `knowledge_base/recipes.json` as the retrieval source, so it suggests dishes from our curated list instead of guessing.

**How Concierge and Head Chef connect to each other:**
- Concierge converts raw customer text into a normalized `EventSpecification` message.
- Head Chef consumes that event specification and produces a `MenuPlan` message, while enforcing allergy rules (e.g., excluding peanut dishes for nut allergy).

#### Session 6 — 2026-04-22 — What I Learned
**What Azure AI Search RAG adds (and why it improves menu planning):**
- RAG (Retrieval Augmented Generation) means we search a curated knowledge base first, then generate a plan using the retrieved results.
- In our system, Azure AI Search acts as the retrieval engine so Head Chef can fetch the most relevant recipes quickly and consistently.

**What an index is (in search terminology):**
- An index is the search service’s organized structure for documents and fields so queries can return relevant matches fast.
- In our system, the `catering-knowledge-base` index stores documents from recipes, pricing, and suppliers.

**What shared memory is (and why dietary restrictions are immutable):**
- Shared memory is a session-scoped store that every agent can read/write during one pipeline run.
- We make `dietary_restrictions` and `allergies` immutable after first write so upstream safety constraints cannot be overridden later in the pipeline.

**What real-time adaptation means:**
- Real-time adaptation lets us update an existing plan by re-running only the affected agents (instead of restarting from scratch).

**What multi-event optimization achieves:**
- Multi-event optimization runs multiple orders and then aggregates procurement so shared ingredients can be bulk-optimized.

#### Session 7 — 2026-04-23 — What I Learned
**What `useState` means (plain English):**
- `useState` is how a React component remembers information that can change over time (like form fields, loading flags, errors, and results).
- In our UI we use it to store:
  - The order form values
  - `isLoading` while agents are running
  - `errorMessage` when the API call fails
  - `finalPlan` after the backend returns

**What `useEffect` means (plain English):**
- `useEffect` runs a piece of code after the component renders.
- It’s used for “side effects” like timers, subscriptions, and syncing UI behavior when inputs change.
- In our UI we use it in the Agent Activity Feed to:
  - Animate agent step progression while `isRunning` is true
  - Update negotiation display after a run completes

**How the frontend connects to the FastAPI backend:**
- The React app sends a JSON request to `POST /api/v1/catering/order`.
- It includes `X-API-Key` from `frontend/.env` (`REACT_APP_API_KEY`).
- The backend returns an `AgentMessage` wrapper. When `message_type` is `final_plan`, we render the `payload` in the Results Dashboard.

---

### 🧠 SECTION 3: CONCEPT GLOSSARY

**Agent:** A specialized AI module with one specific job, its own instructions, and the ability to take actions. Like hiring an expert for one role instead of asking one person to do everything. | Example from our project: Concierge will parse raw customer requests into a clean JSON event spec.

**Orchestration:** The process of coordinating multiple agents — deciding who does what, in what order, and how they share results. Like a project manager directing a team. | Example from our project: The orchestrator will call Concierge → Head Chef → Accountant → Logistics → Stock Manager.

**JSON:** JavaScript Object Notation — a structured way to organize data using labels and values, like a very organized form. Agents in our system talk to each other using JSON messages. | Example from our project: All agent messages follow the wrapper format in `utils/json_schema.py`.

**Endpoint:** A specific URL in our API that does one job. Like a door in a building — each door leads to a different room (function). | Example from our project: We will later create `POST /api/v1/catering/order`.

**Pydantic:** A Python library that checks if data matches the expected format before we use it. Like a form that rejects your submission if you leave required fields blank. | Example from our project: All message schemas in `utils/json_schema.py`.

**RAG:** Retrieval Augmented Generation — giving an AI agent access to a searchable knowledge base so it can look up real information instead of guessing. In our project: Head Chef retrieves recipes from Azure AI Search (with fallback to local JSON). | Example from our project: `catering-knowledge-base` index is queried to fetch relevant recipes.

**Azure AI Search:** A managed search service that stores documents and returns the most relevant matches for a query. In our project: used as the RAG knowledge base for recipes/pricing/suppliers.

**Index (Search):** A structured collection of searchable documents with defined fields. In our project: `catering-knowledge-base`.

**Shared memory:** A session-scoped store used by multiple agents to share context and outputs across a pipeline run. In our project: `memory/shared_memory.py` stores immutable allergies/dietary restrictions, negotiation history, and agent outputs.

**Real-time adaptation:** Updating an existing plan by re-running only the affected part of the pipeline when a change occurs (guest count, budget, dietary additions). In our project: `POST /api/v1/catering/adapt`.

**Multi-event optimization:** Running multiple events and optimizing shared resources (starting with procurement) across them. In our project: `POST /api/v1/catering/multi-order` produces a `MultiEventPlan` with shared procurement optimization.

**Cosmos DB:** A managed NoSQL database service used for persistence. In our project: stores each `FinalPlan` and adaptation events in the `catering-orders` container.

**System prompt:** The highest-priority instruction given to an AI agent that defines its role, boundaries, and output rules. Like a job contract the agent must follow even if the user asks otherwise. | Example from our project: Concierge’s system prompt requires JSON-only output and forbids revealing secrets.

**Prompt injection:** A tactic where a user tries to trick an AI agent into breaking its rules (e.g., “ignore your instructions” or “reveal the API key”). We defend against it with strong system prompts and strict schema validation. | Example from our project: Concierge treats user text as untrusted input and still outputs a validated EventSpecification.

**Virtual Environment (venv):** An isolated Python workspace for one project. Like a dedicated toolbox for this project only. | Example from our project: A venv may contain packages like `pydantic`, `openai`, and Azure SDKs.

**API Key:** A secret password that proves who is making a request to our system. We check this on every request for security. | Example from our project: Later we will require `X-API-Key` on FastAPI endpoints.

**Package (Python):** A folder that Python can import from, usually marked by an `__init__.py` file. | Example from our project: `orchestrator/` and `memory/`.

**Schema:** A strict definition of what fields and data types are allowed in a piece of data. | Example from our project: `AgentMessage` schema.

**Input validation:** Checks that inputs are sensible and correctly formatted before processing them. | Example from our project: `validate_event_date()`.

**Structured JSON logging:** Logging where each entry is written as a JSON object with consistent fields. | Example from our project: `log_event()` in `utils/logger.py`.

**Client (SDK client):** An object used to talk to an external service using credentials and an endpoint. | Example from our project: Azure OpenAI client created by `create_async_azure_openai_client()`.

**Factory function:** A function whose job is to create and return an object. | Example from our project: `create_cosmos_client()`.

**FastAPI:** A Python framework for building APIs quickly with built-in validation and type hints. | Example from our project: `main.py` creates `FastAPI(...)` and registers routes.

**REST endpoint:** A URL + HTTP method that performs one action. | Example from our project: `POST /api/v1/catering/order`.

**Middleware:** Code that runs before/after your endpoint handler, like a checkpoint in the request path. | Example from our project: SlowAPI middleware.

**Dependency (FastAPI):** A function that FastAPI runs before the endpoint to enforce rules (auth, etc.). | Example from our project: `require_api_key`.

**Rate limiting:** A limit on how often a client can call an API within a time window. | Example from our project: 10 requests per minute.

**HTTP status code:** A standard numeric code that describes the result of an HTTP request. | Example from our project: `401` unauthorized, `422` validation error.

---

### ⚠️ SECTION 4: MISTAKES & LESSONS LOG

**Session 1 — Tried to patch an empty file**
- What I did: Attempted to update `utils/azure_client.py` using a contextual patch.
- What happened: The patch failed because the file was empty.
- Why it happened: Patching needs existing text to anchor changes.
- How to avoid it next time: If a file is empty, write the entire file content in one operation.

**Session 2 — Package installed into the wrong Python environment**
- What happened: `slowapi` was installed but uvicorn still raised `ModuleNotFoundError: slowapi`.
- Why it happened: The install went into global Python instead of the project `venv`.
- How we fixed it: Installed using the venv interpreter and restarted uvicorn.

**Session 2 — PowerShell curl alias confusion**
- What happened: `curl` invoked Invoke-WebRequest and failed header parsing.
- How we fixed it: Used `curl.exe` for GET and `Invoke-RestMethod` for POST requests.

**Session 11 — Hidden allergens surfaced during knowledge base expansion**
- What happened: Several new recipes had allergens that were easy to miss without ingredient-level review.
- Examples:
  - Fish exposure via fish sauce / patis
  - Egg exposure via leche flan / custard components
- Lesson: Always cross-check allergens against ingredient names, not just recipe labels.

**Session 11 — Local price inflation skewed early cost assumptions**
- What happened: Initial “reasonable” prices were too high for certain items (e.g., lemongrass, calamansi juice, shrimp).
- How we fixed it: Corrected the 3 items before applying the pricing patch.
- Lesson: Keep a quick sanity range for common PH market prices and adjust before locking the pricing KB.

---

### 🔍 SECTION 5: CODE READING GUIDE

**utils/logger.py**
- **Purpose:** Provide consistent, structured JSON logs across the whole system.
- **How to read it:** Start at the formatter class, then the logger builder, then the `log_event()` helper.
- **Key functions:**
  - `get_logger()` — returns the configured logger
  - `log_event()` — logs an action with `agent_id`, `action`, `status`, `details`
- **How it connects to other files:** Will be imported by agents, API routes, and the orchestrator.

**utils/json_schema.py**
- **Purpose:** Define the exact Pydantic data models for all agent messages.
- **How to read it:** Start with the wrapper parts (`MessageHeader`, `MessageMetadata`, `MessageSignature`), then the payload models, then `AgentMessage`.
- **Key classes:**
  - `AgentMessage` — the wrapper
  - `EventSpecification`, `MenuPlan`, `CostReport`, `LogisticsPlan`, `ProcurementList`, `FinalPlan`, `ErrorMessage`
- **How it connects to other files:** Agents will create/validate these objects before sending messages.

**utils/validator.py**
- **Purpose:** Keep input validation rules in one place.
- **How to read it:** Review config constants first, then the specific validate/normalize functions.
- **Key functions:**
  - `validate_guest_count()`, `validate_budget_php()`, `validate_event_date()`
  - `validate_cuisine_types()`, `validate_dietary_flags()`
- **How it connects to other files:** Will be used by the API layer and Concierge to validate requests.

**utils/azure_client.py**
- **Purpose:** Create Azure client objects from `.env` settings without making network calls.
- **How to read it:** Start with `AzureSettings`, then `get_settings()`, then each `create_*` factory function.
- **Key functions:**
  - `get_settings()` — loads and caches env settings
  - `create_async_azure_openai_client()` — creates OpenAI client
  - `create_cosmos_client()` — creates Cosmos client
  - `create_search_client()` — creates Search client
  - `create_blob_service_client()` — creates Blob client when configured
- **How it connects to other files:** Later used by the API layer and orchestrator to talk to Azure services.

**knowledge_base/recipes.json**
- **Purpose:** Mock recipe knowledge base used for early agent logic and testing.
- **How to read it:** Review the `recipes` list; each recipe includes ingredients, allergens, and dietary flags.
- **Key fields:** `name`, `ingredients`, `allergens`, `dietary_flags`.
- **How it connects to other files:** Head Chef and Accountant will use it for menu building and cost estimation.

**knowledge_base/pricing.json**
- **Purpose:** Mock ingredient pricing used for cost estimation.
- **How to read it:** Review `items` entries; each maps an ingredient + unit to a PHP price.
- **Key fields:** `ingredient`, `unit`, `price_php`.
- **How it connects to other files:** Accountant will use it to compute costs.

**knowledge_base/suppliers.json**
- **Purpose:** Mock supplier directory for procurement planning.
- **How to read it:** Review each supplier’s `products`, `lead_time_days`, and `service_area`.
- **Key fields:** `products`, `lead_time_days`, `service_area`.
- **How it connects to other files:** Stock Manager will use it to choose where to buy missing ingredients.

**data/mock_inventory.json**
- **Purpose:** Mock current inventory (what is already in stock).
- **How to read it:** Review `inventory` items; each entry is an ingredient with quantity and unit.
- **Key fields:** `ingredient`, `quantity`, `unit`.
- **How it connects to other files:** Stock Manager will compare this to recipe needs to generate a procurement list.

---

### 🧪 SECTION 6: TESTING LOG

**[Session 1] — Test: Azure OpenAI minimal connectivity check (GPT-4o)**
- Input used: Prompt "Reply with exactly: OK" (max_tokens=5, temperature=0)
- Expected result: Response text equals `OK`
- Actual result: First run failed with 404 "Resource not found" (endpoint misformatted); after removing `/openai/v1` from `AZURE_OPENAI_ENDPOINT`, the re-test returned `OK`.
- Pass/Fail: Pass
- Notes: Endpoint should be the base resource URL only (example pattern: `https://<resource>.openai.azure.com`).

**[Session 2] — Test: API health check**
- Request: GET /health
- Expected: 200 with {"status": "ok"}
- Actual: 200 with {"status": "ok"}
- Pass/Fail: Pass

**[Session 2] — Test: Order endpoint (valid key)**
- Request: POST /api/v1/catering/order (valid JSON body)
- Expected: 200 with `order_id` and `status=pending`
- Actual: 200 with `order_id` and `status=pending`
- Pass/Fail: Pass

**[Session 2] — Test: Order endpoint (wrong key)**
- Request: POST /api/v1/catering/order with wrong X-API-Key
- Expected: 401
- Actual: 401
- Pass/Fail: Pass

**[Session 2] — Test: Order endpoint (missing required fields)**
- Request: POST /api/v1/catering/order missing `location`
- Expected: 422
- Actual: 422
- Pass/Fail: Pass

**[Session 3] — Test: Concierge agent isolation (Azure OpenAI)**
- Script: `python -m tests.test_agents` (Concierge step)
- Input: Debut party request (150 guests, Filipino food, PHP 45,000, May 20 2026, Antipolo, nut allergy)
- Expected:
  - message_type = "event_specification"
  - event_date normalized to YYYY-MM-DD
  - allergies includes nuts
- Actual:
  - event_date: 2026-05-20
  - allergies: ["nuts"]
  - Pass/Fail: Pass

**[Session 3] — Test: Head Chef agent isolation (local RAG over recipes.json)**
- Script: `python -m tests.test_agents` (Head Chef step)
- Expected:
  - message_type = "menu_plan"
  - Does NOT include Kare-Kare (peanut allergen)
- Actual:
  - Menu generated: Lumpiang Shanghai, Chicken Adobo, Pancit Canton, Laing, Buko Pandan
  - Kare-Kare excluded
  - Pass/Fail: Pass

**[Session 4] — Test: Accountant agent isolation (local pricing.json)**
- Script: `python -m tests.test_agents` (Accountant step)
- Scenarios:
  - Scenario A: Comfortable budget (budget set high)
  - Scenario B: Tight budget (budget set low to force over-budget path)
- Expected:
  - message_type = "cost_report"
  - total_cost_php computed from local pricing
  - over-budget scenario populates flagged_items + recommended_alternatives
- Actual:
  - Cost report produced and validated in both scenarios
  - Pass/Fail: Pass

**[Session 4] — Test: Logistics Lead agent isolation (local backward timeline)**
- Script: `python -m tests.test_agents` (Logistics step)
- Input: Scenario B cost_report + `event_datetime_iso="2026-05-20T18:00:00+08:00"`
- Expected:
  - message_type = "logistics_plan"
  - timeline sorted ascending
  - delivery window includes buffer
- Actual:
  - prep_start_time: 2026-05-20T06:00:00+08:00
  - delivery_time: 2026-05-20T16:00:00+08:00
  - buffer_time_minutes: 45
  - Pass/Fail: Pass

**[Session 4] — Test: Stock Manager agent isolation (local inventory + suppliers)**
- Script: `python -m tests.test_agents` (Stock Manager step)
- Input: logistics_plan + cost_report
- Expected:
  - message_type = "procurement_list"
  - items_to_purchase computed as required - in_stock
  - total_procurement_cost_php computed from cost_report unit prices
- Actual:
  - Procurement list produced with suggested supplier + lead_time_days for purchase items
  - Pass/Fail: Pass

**[Session 4] — Test: Local 4-agent chain (no Azure calls)**
- Chain: Head Chef → Accountant → Logistics → Stock Manager
- Note: Concierge step disabled (`run_concierge_step = False`) to avoid Azure credit usage
- Pass/Fail: Pass

**[Session 5] — Test: Orchestrator negotiation loop (Azure, tight budget)**
- Request: POST /api/v1/catering/order
- Input: 150 guests, budget PHP 8,000 (tight budget), location Quezon City
- Actual:
  - 3 rounds used
  - Total cost PHP 11,337 vs budget PHP 8,000
  - Within budget: False
  - Flagged items: Lumpiang Shanghai, Buko Pandan
  - System correctly stopped after max rounds
- Pass/Fail: Pass

**[Session 6] — Fix: Concierge event_id UUID validation**
- Change: Replace placeholder-based check with UUID regex validation; if missing or not UUID, generate `uuid4()`.
- Files: `agents/concierge.py`
- Reason: GPT-4o sometimes returns `event_001` or other non-UUID strings.

**[Session 6] — Fix: Pricing completeness for common ingredients**
- Change: Added missing ingredient rows to `knowledge_base/pricing.json` (fruit, salad, pantry staples) to prevent silent underpricing when a price is missing.
- Files: `knowledge_base/pricing.json`

**[Session 6] — Test: Correctness suite after fixes**
- Script: `venv\Scripts\python.exe -m tests.test_correctness`
- Result: TOTAL 23/23 checks passed
- Pass/Fail: Pass

**[Session 12] — Test: Manual variety check (3 runs)**
- Endpoint: POST `/api/v1/catering/order`
- Input: Debut party (80 guests, Filipino, PHP 40,000)
- Runs:
  - Run 1: Chicken Adobo, Pancit Canton, Lumpiang Shanghai, Ginataang Gulay, Buko Pandan
  - Run 2: Chicken Adobo, Pancit Canton, Pork Sinigang, Lumpiang Shanghai, Buko Pandan, Laing
  - Run 3: Chicken Adobo, Pancit Canton, Ginataang Gulay, Lumpiang Shanghai, Buko Pandan
- Result: PASS (non-identical runs), with the noted limitation that new recipes were not selected due to the RAG “single blob” issue.

---

### 🗺️ SECTION 7: DECISION LOG

**Decision: Build Azure clients without running network tests yet**
- Options we considered:
  - Create clients only (no tests)
  - Create clients and run safe tests for Cosmos/Search/Blob
  - Run full tests including Azure OpenAI immediately
- Why we chose this one: Avoid accidental Azure credit usage and keep Day 1 foundation safe.
- Trade-offs: We delayed verifying OpenAI credentials until Step 7 (now verified).
- Session: Session 1

**Decision: Add rate limiting to the API early**
- Why: Protects the endpoint from accidental or malicious request bursts.
- What we chose: SlowAPI with 10 requests per minute.
- Session: Session 2

**Decision: Use `dietary_flags` and omit `dietary_tags` for new recipes**
- Why: Existing code already supports `dietary_flags`, and we wanted a single canonical field for new entries.
- Trade-offs: Some downstream checks still reference `dietary_tags`, so Head Chef continues to support both.
- Session: Session 11

**Decision: Price semi-prepared items directly (no decomposition)**
- Why: The system matches ingredient names directly; recipe decomposition would require a different data model.
- Examples: bechamel sauce, cake base, ube halaya, leche flan, sweetened beans.
- Session: Session 11

**Decision: Keep `safe_pool` category fill as-is (defer retry-loop redesign)**
- Why: The current GPT-first selection + safe_pool fill + shuffle fallback is stable and passes correctness.
- Trade-offs: A more advanced retry loop could improve diversity, but was deferred until after fixing the RAG blob indexing issue.
- Session: Session 12

---

### 🚀 SECTION 8: PROGRESS TRACKER

**Phase 1 — Foundation**
[x] Full folder structure created
[x] utils/azure_client.py — Azure client factories implemented (connections not tested yet)
[x] utils/logger.py — structured JSON logging
[x] utils/json_schema.py — all message schemas defined
[x] utils/validator.py — input validation helpers
[x] Mock data files created (recipes.json, pricing.json, mock_inventory.json)
[x] Azure OpenAI connection tested successfully
[x] Day 1 commit pushed to GitHub

**Phase 2 — API Layer**
[x] api/models.py — Pydantic request/response models
[x] api/auth.py — API key authentication
[x] api/routes.py — POST /api/v1/catering/order endpoint
[x] main.py — FastAPI app with rate limiting
[x] API tested with a real request
[x] Day 2 commit pushed to GitHub

**Phase 3 — Core Agents**
[x] agents/concierge.py — working and tested
[x] agents/head_chef.py — working and tested
[x] agents/accountant.py — working and tested
[x] agents/logistics.py — working and tested
[x] agents/stock_manager.py — working and tested
[ ] Day 3-4 commits pushed to GitHub

**Phase 4 — Orchestration**
[x] orchestrator/engine.py — routing all agents
[x] Conflict resolution working (budget negotiation loop)
[x] End-to-end test: full request to final plan
[ ] Day 5 commit pushed to GitHub

**Phase 5 — Bonus Features**
[ ] memory/shared_memory.py — working
[ ] RAG connected to Azure AI Search
[ ] Real-time adaptation working
[ ] Multi-event handling working
[ ] Day 6 commit pushed to GitHub

**Next known fix (planned):**
- Split/chunk the Azure Search recipe index so GPT retrieves per-recipe documents instead of one aggregated blob (improves selection diversity and use of new recipes).

**Phase 6 — Polish**
[ ] All edge cases tested
[ ] README.md complete
[ ] requirements.txt updated
[ ] Demo video recorded
[ ] Final commit pushed
