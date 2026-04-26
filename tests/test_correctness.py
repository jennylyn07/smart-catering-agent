from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv


load_dotenv(override=False)

from agents.head_chef import run_head_chef
from memory.shared_memory import SharedMemory
from orchestrator.engine import run_orchestration
from utils.cosmos_store import read_order_document
from utils.json_schema import AgentMessage, ErrorMessage, EventSpecification, FinalPlan, MenuPlan


REPORT_PATH = Path(__file__).resolve().parent / "correctness_report.txt"


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | FAIL | SKIPPED
    details: str


class ReportWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        self.lines.append(text)
        print(text)

    def write_block(self, lines: list[str]) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


class LogCaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            payload = json.loads(msg)
            if isinstance(payload, dict):
                self.records.append(payload)
        except Exception:
            return


def _now_local_str() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _dish_names_from_menu_plan(menu_plan: MenuPlan) -> list[str]:
    return [str(i.name) for i in (menu_plan.menu_items or []) if getattr(i, "name", None)]


def _safe_lower_list(values: list[str]) -> list[str]:
    return [str(v).strip().lower() for v in values if str(v).strip()]


def _contains_any(text: str, needles: set[str]) -> bool:
    t = text.lower()
    return any(n in t for n in needles)


def _build_event_spec(
    *,
    scenario_id: str,
    guest_count: int,
    budget_php: float,
    cuisine_preferences: list[str],
    allergies: list[str],
    dietary_restrictions: list[str],
    notes: Optional[str] = None,
    event_date: str = "2026-06-01",
    location: str = "Manila",
) -> EventSpecification:
    payload = {
        "event_id": scenario_id,
        "event_name": scenario_id,
        "event_date": event_date,
        "location": location,
        "guest_count": guest_count,
        "budget_php": budget_php,
        "cuisine_preferences": cuisine_preferences,
        "dietary_restrictions": dietary_restrictions,
        "allergies": allergies,
        "notes": notes,
    }
    return EventSpecification.model_validate(payload)


async def _run_head_chef_with_log_capture(*, event_spec: EventSpecification, session_id: str) -> tuple[AgentMessage, list[dict[str, Any]]]:
    logger = logging.getLogger("smart_catering")
    handler = LogCaptureHandler()
    logger.addHandler(handler)
    try:
        msg = await run_head_chef(event_spec=event_spec, session_id=session_id)
        return msg, handler.records
    finally:
        logger.removeHandler(handler)


def _raw_customer_request_from_event_spec(event_spec: EventSpecification) -> str:
    return "\n".join(
        [
            f"Event name: {event_spec.event_name or ''}".strip(),
            f"Event date: {event_spec.event_date}",
            f"Location: {event_spec.location}",
            f"Guests: {event_spec.guest_count}",
            f"Budget PHP: {event_spec.budget_php if event_spec.budget_php is not None else ''}".strip(),
            f"Cuisine preferences: {', '.join(event_spec.cuisine_preferences)}".strip(),
            f"Dietary restrictions: {', '.join(event_spec.dietary_restrictions)}".strip(),
            f"Allergies: {', '.join(event_spec.allergies)}".strip(),
            f"Notes: {event_spec.notes or ''}".strip(),
        ]
    ).strip()


async def _run_full_pipeline(*, event_spec: EventSpecification) -> AgentMessage:
    # Note: This uses Concierge and may invoke Azure OpenAI.
    raw = _raw_customer_request_from_event_spec(event_spec)
    return await run_orchestration(raw_customer_request=raw)


def _backend_running(*, url: str = "http://localhost:8000/health") -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return 200 <= int(resp.status) < 300
    except Exception:
        return False


def _http_post_json(*, url: str, api_key: str, payload: dict[str, Any]) -> tuple[int, str]:
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")  # noqa: S310
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except Exception as exc:
        # urllib errors often wrap HTTP status; keep it simple.
        return 0, str(exc)


def _format_scenario_header(n: str, name: str) -> str:
    return f"SCENARIO {n} — {name}".strip()


def _menu_plan_parts(msg: AgentMessage) -> tuple[list[str], str, list[str]]:
    dishes: list[str] = []
    rationale = ""
    allergy_flags: list[str] = []

    if isinstance(msg.payload, MenuPlan):
        dishes = _dish_names_from_menu_plan(msg.payload)
        rationale = str(msg.payload.rationale or "")
        allergy_flags = list(msg.payload.allergy_flags or [])
    elif isinstance(msg.payload, ErrorMessage):
        rationale = f"ERROR: {msg.payload.error_code} — {msg.payload.message}"

    return dishes, rationale, allergy_flags


def _final_plan_parts(msg: AgentMessage) -> tuple[Optional[FinalPlan], str]:
    if isinstance(msg.payload, FinalPlan):
        return msg.payload, ""
    if isinstance(msg.payload, ErrorMessage):
        return None, f"ERROR: {msg.payload.error_code} — {msg.payload.message}"
    return None, f"Unexpected payload type: {type(msg.payload).__name__}"


async def _section_1_correctness_matrix(report: ReportWriter) -> list[CheckResult]:
    report.write("SECTION 1: CORRECTNESS MATRIX")

    results: list[CheckResult] = []

    async def run_scenario(
        *,
        n: int,
        name: str,
        event_spec: EventSpecification,
        session_id: str,
        check_fn,
        wants_rag_info: bool = False,
    ) -> None:
        header = _format_scenario_header(str(n), name)
        report.write("")
        report.write(f"{header}")

        try:
            msg, logs = await _run_head_chef_with_log_capture(event_spec=event_spec, session_id=session_id)
            dishes, rationale, allergy_flags = _menu_plan_parts(msg)

            rag_mode = "unknown"
            if wants_rag_info:
                rag_mode = "fallback"
                # Head Chef only logs rag_search_recipes on error; absence of error does not guarantee RAG.
                if any(
                    (r.get("action") == "rag_search_recipes" and r.get("status") == "error") for r in logs
                ):
                    rag_mode = "fallback"
                else:
                    rag_mode = "no_rag_error_logged"

            ok, fail_reason = check_fn(dishes=dishes, rationale=rationale, allergy_flags=allergy_flags, logs=logs)
            status = "PASS" if ok else "FAIL"

            report.write(f"- Result: {status}")
            report.write(f"- Dishes returned: {dishes}")
            report.write(f"- Rationale: {rationale}")
            report.write(f"- Allergy flags: {allergy_flags}")
            report.write(f"- Dietary restrictions applied: {event_spec.dietary_restrictions}")
            report.write(f"- Number of dishes: {len(dishes)}" + (" (fewer than 5)" if len(dishes) < 5 else ""))
            if wants_rag_info:
                report.write(f"- RAG vs fallback (best-effort): {rag_mode}")
            if status != "PASS":
                report.write(f"- Failure reason: {fail_reason}")

            results.append(CheckResult(name=header, status=status, details=fail_reason if fail_reason else ""))

        except Exception as exc:  # noqa: BLE001
            report.write(f"- Result: FAIL")
            report.write(f"- Failure reason: Exception: {type(exc).__name__}: {exc}")
            results.append(CheckResult(name=header, status="FAIL", details=f"Exception: {type(exc).__name__}: {exc}"))

    # Scenario 1 — Nut allergy
    s1 = _build_event_spec(
        scenario_id="test-s1",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=["nuts"],
        dietary_restrictions=[],
    )

    def check_s1(*, dishes: list[str], rationale: str, allergy_flags: list[str], logs: list[dict[str, Any]]):
        dish_text = " ".join(dishes).lower()
        if "kare" in dish_text or "peanut" in dish_text:
            return False, "dish name contains kare or peanut"
        flags = set(_safe_lower_list(allergy_flags))
        if not ("nuts" in flags or "peanut" in flags):
            return False, "allergy_flags missing nuts/peanut"
        return True, ""

    # Scenario 2 — Vegetarian
    s2 = _build_event_spec(
        scenario_id="test-s2",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=["vegetarian"],
    )

    vegetarian_block = {
        "chicken",
        "beef",
        "pork",
        "fish",
        "shrimp",
        "meat",
        "adobo",
        "sisig",
        "lechon",
        "liempo",
        "bangus",
        "tinola",
        "sinigang",
    }

    def check_s2(*, dishes: list[str], rationale: str, allergy_flags: list[str], logs: list[dict[str, Any]]):
        bad = [d for d in dishes if _contains_any(d, vegetarian_block)]
        if bad:
            return False, f"blocked terms found in dish names: {bad}"
        return True, ""

    # Scenario 3 — Vegan
    s3 = _build_event_spec(
        scenario_id="test-s3",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=["vegan"],
    )

    vegan_dish_block = set(vegetarian_block)
    vegan_extra_block = {"egg", "cheese", "butter", "cream"}

    def check_s3(*, dishes: list[str], rationale: str, allergy_flags: list[str], logs: list[dict[str, Any]]):
        bad1 = [d for d in dishes if _contains_any(d, vegan_dish_block)]
        if bad1:
            return False, f"meat terms found in dish names: {bad1}"
        bad2 = [d for d in dishes if _contains_any(d, vegan_extra_block)]
        if bad2:
            return False, f"non-vegan terms found in dish names: {bad2}"
        return True, ""

    # Scenario 4 — Halal
    s4 = _build_event_spec(
        scenario_id="test-s4",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=["halal"],
    )

    halal_block = {"pork", "bacon", "lechon", "bagnet", "liempo"}

    def check_s4(*, dishes: list[str], rationale: str, allergy_flags: list[str], logs: list[dict[str, Any]]):
        bad = [d for d in dishes if _contains_any(d, halal_block)]
        if bad:
            return False, f"pork-related terms found in dish names: {bad}"
        return True, ""

    # Scenario 5 — Western cuisine via RAG
    s5 = _build_event_spec(
        scenario_id="test-s5",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["western"],
        allergies=[],
        dietary_restrictions=[],
    )

    western_needles = {"caesar", "grilled", "pasta", "roasted", "chocolate", "salad"}

    def check_s5(*, dishes: list[str], rationale: str, allergy_flags: list[str], logs: list[dict[str, Any]]):
        if not any(_contains_any(d, western_needles) for d in dishes):
            return False, "no western dish keywords found in dish names"
        return True, ""

    # Scenario 6 — Heavy constraints
    s6 = _build_event_spec(
        scenario_id="test-s6",
        guest_count=40,
        budget_php=25000,
        cuisine_preferences=["international"],
        allergies=["nuts", "dairy", "gluten"],
        dietary_restrictions=["vegetarian", "vegan"],
    )

    def check_s6(*, dishes: list[str], rationale: str, allergy_flags: list[str], logs: list[dict[str, Any]]):
        bad = [d for d in dishes if _contains_any(d, vegetarian_block)]
        if bad:
            return False, f"meat terms found in dish names: {bad}"
        if not _contains_any(rationale, {"constraint", "limited"}):
            return False, "rationale missing 'constraint' or 'limited'"
        return True, ""

    # Run 1-6 concurrently.
    await asyncio.gather(
        run_scenario(n=1, name="Nut allergy", event_spec=s1, session_id="test-correctness-001", check_fn=check_s1),
        run_scenario(n=2, name="Vegetarian", event_spec=s2, session_id="test-correctness-002", check_fn=check_s2),
        run_scenario(n=3, name="Vegan", event_spec=s3, session_id="test-correctness-003", check_fn=check_s3),
        run_scenario(n=4, name="Halal", event_spec=s4, session_id="test-correctness-004", check_fn=check_s4),
        run_scenario(
            n=5,
            name="Western cuisine via RAG",
            event_spec=s5,
            session_id="test-correctness-005",
            check_fn=check_s5,
            wants_rag_info=True,
        ),
        run_scenario(n=6, name="Heavy constraints", event_spec=s6, session_id="test-correctness-006", check_fn=check_s6),
    )

    # Scenario 7 — Tight budget negotiation (full pipeline)
    report.write("")
    report.write(_format_scenario_header("7", "Tight budget negotiation (full pipeline)"))

    s7 = _build_event_spec(
        scenario_id="test-s7",
        guest_count=150,
        budget_php=5000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=[],
    )

    try:
        # This may require Azure OpenAI connectivity.
        msg = await _run_full_pipeline(event_spec=s7)
        plan, err = _final_plan_parts(msg)
        if plan is None:
            report.write("- Result: FAIL")
            report.write(f"- Failure reason: {err}")
            results.append(CheckResult(name="SCENARIO 7", status="FAIL", details=err))
        else:
            within_budget = bool(getattr(plan.cost_report, "within_budget", False))
            rounds = int(getattr(plan, "negotiation_rounds_used", 0))
            ok = rounds > 0 or within_budget is False
            status = "PASS" if ok else "FAIL"
            report.write(f"- Result: {status}")
            report.write(f"- negotiation_rounds_used: {rounds}")
            report.write(f"- within_budget: {within_budget}")
            report.write(f"- total_cost_php: {plan.cost_report.total_cost_php}")
            report.write(f"- flagged_items: {list(plan.cost_report.flagged_items or [])}")
            results.append(
                CheckResult(
                    name="SCENARIO 7",
                    status=status,
                    details="" if ok else "Negotiation did not run and within_budget was True",
                )
            )
    except Exception as exc:  # noqa: BLE001
        report.write("- Result: SKIPPED")
        report.write(f"- Reason: Pipeline call failed (may require Azure OpenAI). Exception: {type(exc).__name__}: {exc}")
        results.append(
            CheckResult(
                name="SCENARIO 7",
                status="SKIPPED",
                details=f"Exception: {type(exc).__name__}: {exc}",
            )
        )

    return results


async def _section_2_variety(report: ReportWriter) -> CheckResult:
    report.write("SECTION 2: MENU VARIETY / DETERMINISM CHECK")

    base = _build_event_spec(
        scenario_id="test-variety",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=[],
    )

    try:
        msgs = await asyncio.gather(
            run_head_chef(event_spec=base, session_id="test-variety-1"),
            run_head_chef(event_spec=base, session_id="test-variety-2"),
            run_head_chef(event_spec=base, session_id="test-variety-3"),
        )

        dish_sets: list[list[str]] = []
        for m in msgs:
            if isinstance(m.payload, MenuPlan):
                dish_sets.append(_dish_names_from_menu_plan(m.payload))
            else:
                dish_sets.append([])

        report.write(f"- Run 1: {dish_sets[0]}")
        report.write(f"- Run 2: {dish_sets[1]}")
        report.write(f"- Run 3: {dish_sets[2]}")

        unique = {tuple(x) for x in dish_sets}
        ok = len(unique) >= 2
        status = "PASS" if ok else "FAIL"
        reason = "" if ok else "all 3 runs returned identical menus"
        report.write(f"- Result: {status}")
        if reason:
            report.write(f"- Failure reason: {reason}")
        return CheckResult(name="SECTION 2", status=status, details=reason)

    except Exception as exc:  # noqa: BLE001
        report.write(f"- Result: FAIL")
        report.write(f"- Failure reason: Exception: {type(exc).__name__}: {exc}")
        return CheckResult(name="SECTION 2", status="FAIL", details=f"Exception: {type(exc).__name__}: {exc}")


async def _section_3_notes(report: ReportWriter) -> list[CheckResult]:
    report.write("SECTION 3: SPECIAL NOTES HANDLING CHECK")

    results: list[CheckResult] = []

    async def run_note_test(*, label: str, notes: str, guest_count: int, budget_php: float, needles: set[str]) -> None:
        report.write("")
        report.write(f"NOTE TEST {label}")

        spec = _build_event_spec(
            scenario_id=f"test-notes-{label.lower()}",
            guest_count=guest_count,
            budget_php=budget_php,
            cuisine_preferences=["filipino"],
            allergies=[],
            dietary_restrictions=[],
            notes=notes,
        )

        try:
            msg = await _run_full_pipeline(event_spec=spec)
            plan, err = _final_plan_parts(msg)
            if plan is None:
                report.write("- Result: FAIL")
                report.write(f"- Failure reason: {err}")
                results.append(CheckResult(name=f"NOTE {label}", status="FAIL", details=err))
                return

            logistics = plan.logistics_plan
            prep = str(getattr(logistics, "prep_start_time", ""))
            staffing = str(getattr(logistics, "staffing_notes", ""))
            timeline = getattr(logistics, "timeline", []) or []
            timeline_text = " ".join([str(getattr(t, "description", "")) for t in timeline])

            report.write(f"- prep_start_time: {prep}")
            report.write(f"- staffing_notes: {staffing}")
            report.write(f"- timeline_tasks: {[str(getattr(t, 'description', '')) for t in timeline]}")

            combined = " ".join([prep, staffing, timeline_text]).lower()
            ok = any(n in combined for n in {x.lower() for x in needles})

            # Special-case for early setup: allow prep_start_time < 06:00 check if ISO format parse works.
            if label == "A":
                try:
                    # Compare HH:MM portion if present.
                    time_part = prep.split("T")[1][:5] if "T" in prep else ""
                    if time_part and time_part < "06:00":
                        ok = True
                except Exception:
                    pass

            status = "PASS" if ok else "FAIL"
            reason = "" if ok else f"expected keywords not found: {sorted(needles)}"
            report.write(f"- Result: {status}")
            if reason:
                report.write(f"- Failure reason: {reason}")
            results.append(CheckResult(name=f"SECTION 3 NOTE {label}", status=status, details=reason))

        except Exception as exc:  # noqa: BLE001
            report.write("- Result: SKIPPED")
            report.write(f"- Reason: Pipeline call failed (may require Azure OpenAI). Exception: {type(exc).__name__}: {exc}")
            results.append(
                CheckResult(
                    name=f"SECTION 3 NOTE {label}",
                    status="SKIPPED",
                    details=f"Exception: {type(exc).__name__}: {exc}",
                )
            )

    await asyncio.gather(
        run_note_test(
            label="A",
            notes="Setup must begin by 5AM, doors open at 8AM",
            guest_count=100,
            budget_php=40000,
            needles={"5am", "early"},
        ),
        run_note_test(
            label="B",
            notes="Plated service, 3-course dinner, formal setup",
            guest_count=80,
            budget_php=50000,
            needles={"plated", "3-course", "formal"},
        ),
        run_note_test(
            label="C",
            notes="Buffet style, client is firm on the budget",
            guest_count=60,
            budget_php=35000,
            needles={"buffet"},
        ),
    )

    return results


async def _section_4_bonus(report: ReportWriter) -> list[CheckResult]:
    report.write("SECTION 4: BONUS FEATURES CHECK")

    results: list[CheckResult] = []

    # 4A — RAG is active
    report.write("")
    report.write("TEST 4A — RAG is active (not always falling back)")
    try:
        spec = _build_event_spec(
            scenario_id="test-4a",
            guest_count=50,
            budget_php=30000,
            cuisine_preferences=["western"],
            allergies=[],
            dietary_restrictions=[],
        )
        msg, logs = await _run_head_chef_with_log_capture(event_spec=spec, session_id="test-4a")
        dishes, rationale, allergy_flags = _menu_plan_parts(msg)

        western_needles = {"caesar", "grilled", "pasta", "roasted", "chocolate", "salad"}
        has_western = any(_contains_any(d, western_needles) for d in dishes)

        # Logs only include rag_search_recipes on error in current implementation.
        rag_error = any((r.get("action") == "rag_search_recipes" and r.get("status") == "error") for r in logs)

        status = "PASS" if has_western else "FAIL"
        report.write(f"- Dishes returned: {dishes}")
        report.write(f"- rag_search_recipes error logged: {rag_error}")
        report.write(f"- Result: {status}")
        results.append(
            CheckResult(
                name="TEST 4A",
                status=status,
                details="" if has_western else "no western dish keywords found",
            )
        )
    except Exception as exc:  # noqa: BLE001
        report.write(f"- Result: FAIL")
        report.write(f"- Failure reason: Exception: {type(exc).__name__}: {exc}")
        results.append(CheckResult(name="TEST 4A", status="FAIL", details=f"Exception: {type(exc).__name__}: {exc}"))

    # 4B — Shared memory immutability
    report.write("")
    report.write("TEST 4B — Shared memory immutability")
    try:
        sm = SharedMemory(session_id="test-4b", event_id="test-4b")
        sm.set(key="allergies", value={"nuts"}, writer_agent_id="test")
        second_ok = False
        second_details = ""
        try:
            sm.set(key="allergies", value=set(), writer_agent_id="test")
            second_details = "Second set did not raise; allergies were overwritten (unexpected)."
            second_ok = False
        except Exception as exc:  # noqa: BLE001
            second_details = f"Second set rejected: {type(exc).__name__}: {exc}"
            second_ok = True

        current = sm.get("allergies")
        status = "PASS" if second_ok and current == {"nuts"} else "FAIL"
        report.write(f"- Second set attempt: {second_details}")
        report.write(f"- Current allergies value: {current}")
        report.write(f"- Result: {status}")
        results.append(CheckResult(name="TEST 4B", status=status, details=second_details))
    except Exception as exc:  # noqa: BLE001
        report.write(f"- Result: FAIL")
        report.write(f"- Failure reason: Exception: {type(exc).__name__}: {exc}")
        results.append(CheckResult(name="TEST 4B", status="FAIL", details=f"Exception: {type(exc).__name__}: {exc}"))

    # 4C — Real-time adaptation endpoint
    report.write("")
    report.write("TEST 4C — Real-time adaptation endpoint")
    if not _backend_running():
        report.write("- Result: SKIPPED")
        report.write("- Reason: backend not running")
        results.append(CheckResult(name="TEST 4C", status="SKIPPED", details="backend not running"))
    else:
        api_key = os.getenv("API_KEY") or ""
        if not api_key.strip():
            report.write("- Result: SKIPPED")
            report.write("- Reason: API_KEY not set in environment")
            results.append(CheckResult(name="TEST 4C", status="SKIPPED", details="API_KEY not set"))
        else:
            try:
                spec = _build_event_spec(
                    scenario_id="test-4c",
                    guest_count=50,
                    budget_php=30000,
                    cuisine_preferences=["filipino"],
                    allergies=[],
                    dietary_restrictions=[],
                    notes="",
                )
                msg = await _run_full_pipeline(event_spec=spec)
                plan, err = _final_plan_parts(msg)
                if plan is None:
                    report.write("- Result: FAIL")
                    report.write(f"- Failure reason: pipeline did not return final_plan: {err}")
                    results.append(CheckResult(name="TEST 4C", status="FAIL", details=f"pipeline did not return final_plan: {err}"))
                else:
                    order_id = str(plan.event_id).strip()
                    report.write(f"- Using order_id from pipeline final_plan.event_id: {order_id}")

                    payload = {
                        "order_id": order_id,
                        "change_type": "guest_count_change",
                        "new_value": 100,
                    }
                    status_code, body = _http_post_json(
                        url="http://localhost:8000/api/v1/catering/adapt",
                        api_key=api_key,
                        payload=payload,
                    )

                    error_details = ""
                    has_error_code = False
                    try:
                        parsed = json.loads(body)
                        payload_obj = parsed.get("payload") if isinstance(parsed, dict) else None
                        if isinstance(payload_obj, dict) and payload_obj.get("error_code"):
                            has_error_code = True
                            error_details = f"error_code={payload_obj.get('error_code')}; message={payload_obj.get('message')}"
                    except Exception:
                        error_details = "response was not valid JSON"

                    ok = (status_code == 200) and (not has_error_code)
                    report.write(f"- HTTP status: {status_code}")
                    report.write(f"- Response: {body}")
                    if not ok and error_details:
                        report.write(f"- Failure reason: {error_details}")
                    results.append(
                        CheckResult(
                            name="TEST 4C",
                            status="PASS" if ok else "FAIL",
                            details="" if ok else (error_details or "non-200 response"),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                report.write("- Result: FAIL")
                report.write(f"- Failure reason: Exception: {type(exc).__name__}: {exc}")
                results.append(CheckResult(name="TEST 4C", status="FAIL", details=f"Exception: {type(exc).__name__}: {exc}"))

    # 4D — Multi-event optimization endpoint
    report.write("")
    report.write("TEST 4D — Multi-event optimization endpoint")
    if not _backend_running():
        report.write("- Result: SKIPPED")
        report.write("- Reason: backend not running")
        results.append(CheckResult(name="TEST 4D", status="SKIPPED", details="backend not running"))
    else:
        api_key = os.getenv("API_KEY") or ""
        if not api_key.strip():
            report.write("- Result: SKIPPED")
            report.write("- Reason: API_KEY not set in environment")
            results.append(CheckResult(name="TEST 4D", status="SKIPPED", details="API_KEY not set"))
        else:
            payload = {
                "orders": [
                    {
                        "event_name": "Event A",
                        "event_date": "2026-06-10",
                        "location": "Manila",
                        "guest_count": 50,
                        "budget_php": 25000,
                        "cuisine_preferences": ["filipino"],
                        "allergies": [],
                        "dietary_restrictions": [],
                        "notes": "",
                    },
                    {
                        "event_name": "Event B",
                        "event_date": "2026-06-11",
                        "location": "Quezon City",
                        "guest_count": 30,
                        "budget_php": 15000,
                        "cuisine_preferences": ["western"],
                        "allergies": [],
                        "dietary_restrictions": [],
                        "notes": "",
                    },
                ],
                "acknowledge_azure_openai": True,
            }
            status_code, body = _http_post_json(
                url="http://localhost:8000/api/v1/catering/multi-order",
                api_key=api_key,
                payload=payload,
            )
            ok = status_code == 200
            report.write(f"- HTTP status: {status_code}")
            report.write(f"- Response: {body}")
            results.append(
                CheckResult(
                    name="TEST 4D",
                    status="PASS" if ok else "FAIL",
                    details="" if ok else "non-200 response",
                )
            )

    # 4E — Cosmos DB persistence
    report.write("")
    report.write("TEST 4E — Cosmos DB persistence")
    try:
        # Run a normal order through pipeline, then attempt to read back from Cosmos by order_id.
        spec = _build_event_spec(
            scenario_id="test-4e",
            guest_count=60,
            budget_php=35000,
            cuisine_preferences=["filipino"],
            allergies=[],
            dietary_restrictions=[],
        )
        msg = await _run_full_pipeline(event_spec=spec)
        plan, err = _final_plan_parts(msg)
        if plan is None:
            report.write("- Result: SKIPPED")
            report.write(f"- Reason: pipeline did not return final_plan: {err}")
            results.append(CheckResult(name="TEST 4E", status="SKIPPED", details=err))
        else:
            order_id = str(plan.event_id)
            report.write(f"- Pipeline final_plan.event_id (order_id for Cosmos read): {order_id}")
            try:
                doc = await read_order_document(order_id=order_id)
                keys = sorted(list(doc.keys())) if isinstance(doc, dict) else []
                ok = isinstance(doc, dict) and (doc.get("order_id") == order_id or doc.get("id") == order_id)
                report.write(f"- Read document keys: {keys}")
                report.write(f"- Result: {'PASS' if ok else 'FAIL'}")
                results.append(CheckResult(name="TEST 4E", status="PASS" if ok else "FAIL", details=""))
            except Exception as exc:  # noqa: BLE001
                report.write("- Result: SKIPPED")
                report.write(f"- Reason: Cosmos read failed. Exception: {type(exc).__name__}: {exc}")
                results.append(
                    CheckResult(
                        name="TEST 4E",
                        status="SKIPPED",
                        details=f"Cosmos read failed: {type(exc).__name__}: {exc}",
                    )
                )
    except Exception as exc:  # noqa: BLE001
        report.write("- Result: SKIPPED")
        report.write(f"- Reason: Pipeline/Cosmos test failed. Exception: {type(exc).__name__}: {exc}")
        results.append(CheckResult(name="TEST 4E", status="SKIPPED", details=f"Exception: {type(exc).__name__}: {exc}"))

    return results


async def _section_5_cost_scaling(report: ReportWriter) -> CheckResult:
    report.write("SECTION 5: COST SCALING REALITY CHECK")

    async def run_cost(label: str, guest_count: int, budget_php: float) -> tuple[str, Optional[float], Optional[str]]:
        spec = _build_event_spec(
            scenario_id=f"test-cost-{label.lower()}",
            guest_count=guest_count,
            budget_php=budget_php,
            cuisine_preferences=["filipino"],
            allergies=[],
            dietary_restrictions=[],
        )
        try:
            msg = await _run_full_pipeline(event_spec=spec)
            plan, err = _final_plan_parts(msg)
            if plan is None:
                return label, None, err
            return label, float(plan.cost_report.total_cost_php), ""
        except Exception as exc:  # noqa: BLE001
            return label, None, f"Exception: {type(exc).__name__}: {exc}"

    a, b, c = await asyncio.gather(
        run_cost("A", 20, 50000),
        run_cost("B", 100, 50000),
        run_cost("C", 300, 200000),
    )

    report.write(f"- Run A (20 guests): total_cost_php={a[1]} error={a[2]}")
    report.write(f"- Run B (100 guests): total_cost_php={b[1]} error={b[2]}")
    report.write(f"- Run C (300 guests): total_cost_php={c[1]} error={c[2]}")

    if a[1] is None or b[1] is None or c[1] is None:
        report.write("- Result: SKIPPED")
        report.write("- Reason: one or more pipeline runs did not complete")
        return CheckResult(name="SECTION 5", status="SKIPPED", details="pipeline runs incomplete")

    a_per = a[1] / 20.0
    b_per = b[1] / 100.0
    c_per = c[1] / 300.0

    report.write(f"- Cost per guest A: {a_per:.2f}")
    report.write(f"- Cost per guest B: {b_per:.2f}")
    report.write(f"- Cost per guest C: {c_per:.2f}")

    # Detect non-linear scaling: per-guest should not be identical.
    identical = abs(a_per - b_per) < 1e-6 and abs(b_per - c_per) < 1e-6
    overhead_detectable = a_per > c_per
    ok = (not identical) and overhead_detectable

    status = "PASS" if ok else "FAIL"
    reason = ""
    if identical:
        reason += "cost_per_guest identical across all runs; "
    if not overhead_detectable:
        reason += "fixed overhead not detectable (20 guests not higher per-guest than 300); "

    report.write(f"- Fixed overhead detectable: {overhead_detectable}")
    report.write(f"- Result: {status}")
    if reason.strip():
        report.write(f"- Failure reason: {reason.strip()}")

    return CheckResult(name="SECTION 5", status=status, details=reason.strip())


async def _section_6_edge_cases(report: ReportWriter) -> list[CheckResult]:
    report.write("SECTION 6: EDGE CASES")

    results: list[CheckResult] = []

    async def edge_pipeline(*, n: int, name: str, spec: EventSpecification, check_fn) -> None:
        report.write("")
        header = f"EDGE CASE {n} — {name}"
        report.write(header)
        try:
            msg = await _run_full_pipeline(event_spec=spec)
            plan, err = _final_plan_parts(msg)
            ok, reason, extra = check_fn(plan, err)
            status = "PASS" if ok else "FAIL"
            if err and plan is None:
                # treat error messages as acceptable if check_fn allows
                pass
            report.write(f"- Result: {status}")
            report.write(f"- What returned: {('final_plan' if plan is not None else 'error/other')}")
            if plan is not None:
                report.write(f"- within_budget: {getattr(plan.cost_report, 'within_budget', None)}")
                report.write(f"- negotiation_rounds_used: {getattr(plan, 'negotiation_rounds_used', None)}")
            else:
                report.write(f"- Error: {err}")
            if extra:
                for k, v in extra.items():
                    report.write(f"- {k}: {v}")
            if reason:
                report.write(f"- Failure reason: {reason}")
            results.append(CheckResult(name=header, status=status, details=reason))
        except Exception as exc:  # noqa: BLE001
            report.write("- Result: SKIPPED")
            report.write(f"- Reason: Exception: {type(exc).__name__}: {exc}")
            results.append(CheckResult(name=header, status="SKIPPED", details=f"Exception: {type(exc).__name__}: {exc}"))

    async def edge_head_chef(*, n: int, name: str, spec: EventSpecification, check_fn) -> None:
        report.write("")
        header = f"EDGE CASE {n} — {name}"
        report.write(header)
        try:
            msg = await run_head_chef(event_spec=spec, session_id=f"test-e{n}")
            if isinstance(msg.payload, MenuPlan):
                dishes = _dish_names_from_menu_plan(msg.payload)
                ok, reason, extra = check_fn(dishes, msg)
                status = "PASS" if ok else "FAIL"
                report.write(f"- Result: {status}")
                report.write(f"- Dishes returned: {dishes}")
                report.write(f"- Allergy flags: {list(msg.payload.allergy_flags or [])}")
                report.write(f"- Rationale: {msg.payload.rationale}")
                if extra:
                    for k, v in extra.items():
                        report.write(f"- {k}: {v}")
                if reason:
                    report.write(f"- Failure reason: {reason}")
                results.append(CheckResult(name=header, status=status, details=reason))
            elif isinstance(msg.payload, ErrorMessage):
                ok, reason, extra = check_fn([], msg)
                status = "PASS" if ok else "FAIL"
                report.write(f"- Result: {status}")
                report.write(f"- Error: {msg.payload.error_code} — {msg.payload.message}")
                if reason:
                    report.write(f"- Failure reason: {reason}")
                results.append(CheckResult(name=header, status=status, details=reason))
            else:
                report.write("- Result: FAIL")
                report.write(f"- Failure reason: unexpected payload type {type(msg.payload).__name__}")
                results.append(CheckResult(name=header, status="FAIL", details="unexpected payload type"))
        except Exception as exc:  # noqa: BLE001
            report.write("- Result: FAIL")
            report.write(f"- Failure reason: Exception: {type(exc).__name__}: {exc}")
            results.append(CheckResult(name=header, status="FAIL", details=f"Exception: {type(exc).__name__}: {exc}"))

    # EDGE 1 — Impossibly low budget
    e1 = _build_event_spec(
        scenario_id="test-e1",
        guest_count=150,
        budget_php=1,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=[],
    )

    def check_e1(plan: Optional[FinalPlan], err: str):
        if plan is None:
            # Error is acceptable if it is clear.
            return True, "", {"error_message": err}
        within = bool(getattr(plan.cost_report, "within_budget", False))
        rounds = int(getattr(plan, "negotiation_rounds_used", 0))
        if within is False and rounds == 3:
            return True, "", {}
        return False, "expected within_budget False and negotiation_rounds_used=3 for budget=1", {}

    # EDGE 2 — Very large guest count
    e2 = _build_event_spec(
        scenario_id="test-e2",
        guest_count=500,
        budget_php=500000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=[],
    )

    def check_e2(plan: Optional[FinalPlan], err: str):
        if plan is None:
            return False, "pipeline returned error", {"error_message": err}
        total = float(plan.cost_report.total_cost_php)
        procurement_count = len(plan.procurement_list.items_to_purchase or [])
        if total <= 50000:
            return False, "total_cost_php not reasonable for 500 guests (<= 50,000)", {
                "total_cost_php": total,
                "procurement_items": procurement_count,
            }
        return True, "", {"total_cost_php": total, "procurement_items": procurement_count}

    # EDGE 3 — All allergies simultaneously (head_chef)
    e3 = _build_event_spec(
        scenario_id="test-e3",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=["nuts", "dairy", "gluten", "seafood"],
        dietary_restrictions=[],
    )

    def check_e3(dishes: list[str], msg: AgentMessage):
        # Best-effort keyword screening (dishes don't list ingredients).
        blocked = {"nuts", "peanut", "milk", "cream", "cheese", "wheat", "gluten", "shrimp", "fish"}
        bad = [d for d in dishes if _contains_any(d, blocked)]
        if bad:
            return False, f"blocked allergen keywords appear in dish names: {bad}", {}
        return True, "", {}

    # EDGE 4 — Past event date
    e4 = _build_event_spec(
        scenario_id="test-e4",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=[],
        event_date="2020-01-01",
    )

    def check_e4(plan: Optional[FinalPlan], err: str):
        # Either behavior is acceptable as long as no crash.
        if plan is not None:
            return True, "", {"message": "returned plan for past date"}
        if err:
            return True, "", {"message": "returned error for past date", "error": err}
        return False, "unexpected empty result", {}

    # EDGE 5 — No cuisine preferences selected (head_chef)
    e5 = _build_event_spec(
        scenario_id="test-e5",
        guest_count=50,
        budget_php=30000,
        cuisine_preferences=[],
        allergies=[],
        dietary_restrictions=[],
    )

    def check_e5(dishes: list[str], msg: AgentMessage):
        if not dishes:
            return False, "expected at least 1 dish when cuisine_preferences is empty", {}
        return True, "", {}

    # EDGE 6 — Very long special notes
    notes = (
        "This is a very important corporate gala event for our top clients. "
        "We need the finest Filipino cuisine with premium presentation. "
        "The venue has a strict 6AM setup window. Plated service only, no buffet. "
        "The CEO is vegetarian. Three courses minimum. Centerpieces on every table. "
        "Staff must wear formal attire. Contact the venue manager Maria Santos at extension 201 before arrival. "
        "Parking is available at basement level two only. "
    )
    if len(notes) < 500:
        notes = (notes + " " + notes)[:500]

    e6 = _build_event_spec(
        scenario_id="test-e6",
        guest_count=80,
        budget_php=45000,
        cuisine_preferences=["filipino"],
        allergies=[],
        dietary_restrictions=[],
        notes=notes,
    )

    def check_e6(plan: Optional[FinalPlan], err: str):
        if plan is None:
            return False, "pipeline returned error", {"error_message": err}
        timeline = plan.logistics_plan.timeline or []
        text = " ".join([str(getattr(t, "description", "")) for t in timeline]).lower()
        staffing = str(getattr(plan.logistics_plan, "staffing_notes", "")).lower()
        combined = " ".join([text, staffing])
        ok = any(k in combined for k in {"6am", "plated", "formal"})
        total_seconds = float(getattr(plan, "total_processing_time_seconds", 0.0))
        if total_seconds > 30.0:
            return False, "processing time exceeded 30 seconds", {"total_processing_time_seconds": total_seconds}
        if not ok:
            return False, "logistics plan did not reflect expected keywords (6AM/plated/formal)", {
                "total_processing_time_seconds": total_seconds
            }
        return True, "", {"total_processing_time_seconds": total_seconds}

    await edge_pipeline(n=1, name="Impossibly low budget", spec=e1, check_fn=check_e1)
    await edge_pipeline(n=2, name="Very large guest count", spec=e2, check_fn=check_e2)
    await edge_head_chef(n=3, name="All allergies simultaneously", spec=e3, check_fn=check_e3)
    await edge_pipeline(n=4, name="Past event date", spec=e4, check_fn=check_e4)
    await edge_head_chef(n=5, name="No cuisine preferences selected", spec=e5, check_fn=check_e5)
    await edge_pipeline(n=6, name="Very long special notes", spec=e6, check_fn=check_e6)

    return results

async def main() -> None:
    report = ReportWriter(REPORT_PATH)
    report.write("=============================================")
    report.write(f"SMART CATERING — CORRECTNESS TEST REPORT")
    report.write(f"Generated: {_now_local_str()}")
    report.write("=============================================")
    report.write("")

    all_checks: list[CheckResult] = []

    # ... (rest of the code remains the same)
    s1 = await _section_1_correctness_matrix(report)
    all_checks.extend(s1)

    report.write("")
    report.write("=============================================")
    s2 = await _section_2_variety(report)
    all_checks.append(s2)

    report.write("")
    report.write("=============================================")
    s3 = await _section_3_notes(report)
    all_checks.extend(s3)

    report.write("")
    report.write("=============================================")
    s4 = await _section_4_bonus(report)
    all_checks.extend(s4)

    report.write("")
    report.write("=============================================")
    s5 = await _section_5_cost_scaling(report)
    all_checks.append(s5)

    report.write("")
    report.write("=============================================")
    s6 = await _section_6_edge_cases(report)
    all_checks.extend(s6)

    # Final summary
    report.write("")
    report.write("=============================================")
    report.write("FINAL SUMMARY")
    report.write("=============================================")

    def count(prefix: str) -> tuple[int, int, int]:
        subset = [c for c in all_checks if c.name.startswith(prefix)]
        passed = len([c for c in subset if c.status == "PASS"])
        failed = len([c for c in subset if c.status == "FAIL"])
        skipped = len([c for c in subset if c.status == "SKIPPED"])
        return passed, failed, skipped

    # Section 1 is 7 checks.
    s1_pass = len([c for c in all_checks if c.name.startswith("SCENARIO") and c.status == "PASS"])
    s1_total = len([c for c in all_checks if c.name.startswith("SCENARIO")])

    notes_pass = len([c for c in all_checks if c.name.startswith("SECTION 3 NOTE") and c.status == "PASS"])
    notes_total = len([c for c in all_checks if c.name.startswith("SECTION 3 NOTE")])

    bonus_pass = len([c for c in all_checks if c.name.startswith("TEST 4") and c.status == "PASS"])
    bonus_total = len([c for c in all_checks if c.name.startswith("TEST 4")])

    edge_pass = len([c for c in all_checks if c.name.startswith("EDGE CASE") and c.status == "PASS"])
    edge_total = len([c for c in all_checks if c.name.startswith("EDGE CASE")])

    variety_status = next((c.status for c in all_checks if c.name == "SECTION 2"), "SKIPPED")
    cost_status = next((c.status for c in all_checks if c.name == "SECTION 5"), "SKIPPED")

    report.write(f"Section 1 (Correctness):  {s1_pass}/{s1_total} passed")
    report.write(f"Section 2 (Variety):      {variety_status}")
    report.write(f"Section 3 (Notes):        {notes_pass}/{notes_total} passed")
    report.write(f"Section 4 (Bonus):        {bonus_pass}/{bonus_total} passed")
    report.write(f"Section 5 (Cost scaling): {cost_status}")
    report.write(f"Section 6 (Edge cases):   {edge_pass}/{edge_total} passed")

    total_pass = len([c for c in all_checks if c.status == "PASS"])
    total_total = len(all_checks)
    report.write("")
    report.write(f"TOTAL: {total_pass}/{total_total} checks passed")

    failures = [c for c in all_checks if c.status == "FAIL"]
    report.write("")
    report.write("FAILURES REQUIRING FIXES:")
    if not failures:
        report.write("- None")
    else:
        for f in failures:
            report.write(f"- {f.name}: {f.details}")

    passes = [c for c in all_checks if c.status == "PASS"]
    report.write("")
    report.write("ITEMS WORKING CORRECTLY:")
    if not passes:
        report.write("- None")
    else:
        for p in passes:
            report.write(f"- {p.name}")

    report.flush()


if __name__ == "__main__":
    asyncio.run(main())
