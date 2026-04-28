from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import ValidationError

from utils.azure_client import create_async_azure_openai_client, get_azure_openai_deployment_name
from utils.json_schema import (
    AgentMessage,
    CostReport,
    DeliveryWindow,
    ErrorMessage,
    EventSpecification,
    LogisticsPlan,
    MessageHeader,
    MessageMetadata,
    MessageSignature,
    TimelineTask,
)
from utils.logger import log_event

AGENT_ID = "logistics"


def _now_utc() -> datetime:
    """Return the current UTC time.

    Args:
        None

    Returns:
        A timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


def _stable_hash(value: Any) -> str:
    """Compute a stable SHA-256 hash for a JSON-serializable value.

    Args:
        value: Value to hash (Pydantic models should be converted before calling).

    Returns:
        Hex-encoded SHA-256 digest.
    """
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wrap_message(*, payload: Any, message_type: str, target_agent: str, session_id: str) -> AgentMessage:
    """Wrap a payload in the standard AgentMessage envelope.

    Args:
        payload: The message payload model or JSON-serializable object.
        message_type: The message type string for the header.
        target_agent: Downstream consumer agent identifier.
        session_id: Correlation/session identifier for the request.

    Returns:
        A fully populated AgentMessage containing header, payload, metadata, and signature.
    """
    header = MessageHeader(
        message_id=uuid4(),
        agent_id=AGENT_ID,
        target_agent=target_agent,
        timestamp=_now_utc(),
        message_type=message_type,
    )
    metadata = MessageMetadata(confidence_score=0.75)

    signature_payload: Any
    if hasattr(payload, "model_dump"):
        signature_payload = payload.model_dump()
    else:
        signature_payload = payload

    signature = MessageSignature(hash=_stable_hash(signature_payload), session_id=session_id)
    return AgentMessage(header=header, payload=payload, metadata=metadata, signature=signature)


def _error_message(
    *,
    session_id: str,
    error_code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> AgentMessage:
    """Create an error AgentMessage for failures within this agent.

    Args:
        session_id: Correlation/session identifier for the request.
        error_code: Stable error code for the failure class.
        message: Human-readable error message.
        details: Optional structured error details.

    Returns:
        An AgentMessage whose payload is an ErrorMessage.
    """
    payload = ErrorMessage(error_code=error_code, message=message, agent_id=AGENT_ID, details=details or {})
    return _wrap_message(
        payload=payload,
        message_type="error",
        target_agent="orchestrator",
        session_id=session_id,
    )


def _parse_event_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime string that includes a timezone offset.

    Args:
        value: ISO datetime string (must include timezone offset).

    Returns:
        A timezone-aware datetime.
    """
    text = value.strip()
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("event_datetime_iso must include timezone offset, e.g. 2026-05-20T18:00:00+08:00")
    return dt


def _fmt(dt: datetime) -> str:
    """Format a datetime as an ISO-8601 string.

    Args:
        dt: Datetime value.

    Returns:
        ISO formatted datetime string.
    """
    return dt.isoformat()


def _load_suppliers() -> list[dict[str, Any]]:
    """Load supplier data from the suppliers knowledge base.

    Args:
        None

    Returns:
        A list of supplier dicts from `knowledge_base/suppliers.json`.
    """
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "suppliers.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    suppliers = payload.get("suppliers")
    if not isinstance(suppliers, list):
        return []
    return suppliers


def _build_lead_time_index(suppliers: list[dict[str, Any]]) -> dict[str, int]:
    """Build a map of product name to maximum lead time across suppliers.

    Args:
        suppliers: Supplier dicts with `products` and `lead_time_days`.

    Returns:
        Mapping of product name (lowercase) to lead time in days.
    """
    index: dict[str, int] = {}
    for s in suppliers:
        lead = int(s.get("lead_time_days") or 0)
        products = s.get("products") or []
        for p in products:
            name = str(p).strip().lower()
            if not name:
                continue
            index[name] = max(index.get(name, 0), lead)
    return index


def _identify_long_lead_items(cost_report: CostReport) -> list[str]:
    """Identify line items that require long lead-time procurement.

    Args:
        cost_report: CostReport whose line_items drive procurement needs.

    Returns:
        Sorted list of ingredient names that have lead time >= 2 days.
    """
    suppliers = _load_suppliers()
    lead_index = _build_lead_time_index(suppliers)

    long_lead: set[str] = set()
    for li in cost_report.line_items:
        lead_days = lead_index.get(li.item.strip().lower(), 0)
        if lead_days >= 2:
            long_lead.add(li.item)

    return sorted(long_lead)


def _identify_most_prep_dishes(cost_report: CostReport) -> list[str]:
    """Pick the most prep-intensive dishes using dish cost as a simple heuristic.

    Args:
        cost_report: CostReport containing per-dish costs.

    Returns:
        A list of dish names representing the top prep-intensive candidates.
    """
    if not cost_report.cost_per_dish:
        return []

    sorted_dishes = sorted(cost_report.cost_per_dish, key=lambda d: d.cost_php, reverse=True)
    return [d.dish_name for d in sorted_dishes[:2]]


def _timeline_from_event(event_dt: datetime) -> list[TimelineTask]:
    """Create a backwards-planned timeline of tasks leading up to the event.

    Args:
        event_dt: Event datetime.

    Returns:
        A list of TimelineTask entries sorted ascending by time.
    """
    checkpoints = [
        (timedelta(hours=48), "Confirm final guest count", "concierge"),
        (timedelta(hours=24), "All ingredients procured", "stock_manager"),
        (timedelta(hours=12), "Prep begins", "logistics"),
        (timedelta(hours=6), "Cooking begins", "head_chef"),
        (timedelta(hours=2), "Setup at venue", "logistics"),
        (timedelta(hours=0), "Service starts", "logistics"),
    ]

    tasks: list[TimelineTask] = []
    for offset, desc, owner in checkpoints:
        when = event_dt - offset
        tasks.append(TimelineTask(time=_fmt(when), description=desc, owner=owner))

    tasks.sort(key=lambda t: t.time)
    return tasks


async def _gpt_interpret_notes(
    notes: Optional[str],
    event_spec: "EventSpecification",
    timeline_summary: str,
) -> Optional[dict]:
    """Use GPT-4o to interpret event notes for logistics planning.
    Returns a dict with staffing_notes, extra_timeline_tasks, setup_flags
    or None if GPT fails or notes are empty.
    """
    if not notes or not notes.strip():
        return None

    try:
        client = create_async_azure_openai_client()
        deployment = get_azure_openai_deployment_name()

        system_prompt = (
            "You are a senior catering logistics expert with 15 years of operational experience. "
            "Your role is to read event notes and extract every logistics implication — "
            "staffing needs, service style requirements, setup tasks, and timing adjustments.\n\n"
            "Think like a real operations expert who has run hundreds of events. "
            "Consider what the notes mean for the team on the ground: "
            "how many staff are needed, how should the venue be set up, "
            "what tasks need to be added to the timeline, does prep need to start earlier than usual?\n\n"
            "Be specific and actionable. A note that mentions a service style, venue condition, "
            "guest requirement, or timing constraint always has real logistics consequences — "
            "your job is to surface them clearly.\n\n"
            "Return ONLY a valid JSON object with exactly these three keys:\n"
            '- "staffing_notes": a clear string describing all staffing and service implications '
            "(null only if the notes contain absolutely no logistics relevance)\n"
            '- "extra_timeline_tasks": a list of specific actionable task strings to add to the '
            "schedule implied by the notes (empty list if none)\n"
            '- "setup_flags": a list of setup requirement strings; include "early_setup" if the '
            "notes imply prep should start earlier than the standard 12-hour window (empty list if none)\n\n"
            "No markdown. No preamble. No explanation. Output the JSON object only."
        )

        user_prompt = (
            f"Event notes: {notes}\n\n"
            f"Event context: {event_spec.guest_count} guests, "
            f"cuisine: {event_spec.cuisine_preferences}, "
            f"occasion: {event_spec.event_name}\n\n"
            f"Already scheduled timeline tasks:\n{timeline_summary}\n\n"
            "Return the JSON object only."
        )

        response = await client.chat.completions.create(
            model=deployment,
            temperature=0.3,
            max_tokens=300,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = (response.choices[0].message.content or "").strip()
        result = json.loads(content)
        if not isinstance(result, dict):
            return None
        return result

    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id=AGENT_ID,
            action="gpt_interpret_notes",
            status="error",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
        return None


async def run_logistics(
    *,
    cost_report_message: AgentMessage,
    event_spec: EventSpecification,
    event_datetime_iso: str,
    session_id: str,
) -> AgentMessage:
    """Generate a LogisticsPlan from a CostReport and an event datetime.

    Args:
        cost_report_message: AgentMessage containing a CostReport payload.
        event_datetime_iso: ISO datetime string including timezone offset.
        session_id: Correlation/session identifier for the request.

    Returns:
        An AgentMessage containing a LogisticsPlan payload, or an ErrorMessage on failure.
    """
    log_event(
        agent_id=AGENT_ID,
        action="build_logistics_plan",
        status="started",
        details={
            "event_datetime_iso": event_datetime_iso,
            "event_id": getattr(event_spec, "event_id", None),
        },
    )

    try:
        if not isinstance(cost_report_message.payload, CostReport):
            raise ValueError("cost_report_message payload must be a CostReport")

        cost_report: CostReport = cost_report_message.payload
        event_dt = _parse_event_datetime(event_datetime_iso)

        notes = event_spec.notes

        timeline = _timeline_from_event(event_dt)

        prep_start_dt = event_dt - timedelta(hours=12)

        timeline_summary = "\n".join(f"- {t.description} at {t.time}" for t in timeline)
        gpt_result = await _gpt_interpret_notes(notes, event_spec, timeline_summary)

        if gpt_result is not None:
            ai_reasoning = json.dumps(gpt_result)
            staffing_notes = gpt_result.get("staffing_notes") or None
            for task_desc in gpt_result.get("extra_timeline_tasks", []):
                if task_desc and str(task_desc).strip():
                    timeline.append(
                        TimelineTask(
                            time=_fmt(event_dt),
                            description=str(task_desc).strip(),
                            owner="logistics",
                        )
                    )
            if "early_setup" in gpt_result.get("setup_flags", []):
                prep_start_dt = min(prep_start_dt, event_dt - timedelta(hours=14))
                prep_start_time = _fmt(prep_start_dt)

        else:
            staffing_notes = None
            ai_reasoning = "graceful_degradation: gpt_unavailable"
            log_event(
                agent_id=AGENT_ID,
                action="gpt_interpret_notes",
                status="warning",
                details={
                    "warning": "GPT unavailable for notes interpretation; proceeding without notes analysis",
                    "notes_provided": bool(notes and notes.strip()),
                },
            )

        prep_start_time = _fmt(prep_start_dt)
        delivery_time = _fmt(event_dt - timedelta(hours=2))

        buffer_minutes = 45
        delivery_window = DeliveryWindow(
            start_time=_fmt(event_dt - timedelta(hours=2, minutes=buffer_minutes)),
            end_time=_fmt(event_dt - timedelta(hours=2)),
            notes="Arrive early to allow buffer for traffic and venue access.",
        )

        long_lead_items = _identify_long_lead_items(cost_report)
        most_prep_dishes = _identify_most_prep_dishes(cost_report)

        critical_path: list[str] = []
        if long_lead_items:
            critical_path.append("Long lead-time procurement: " + ", ".join(long_lead_items))
        if most_prep_dishes:
            critical_path.append("Most prep-intensive dishes: " + ", ".join(most_prep_dishes))
        critical_path.append("Venue access and setup")

        timeline.sort(key=lambda t: t.time)

        plan = LogisticsPlan(
            event_id=cost_report.event_id,
            prep_start_time=prep_start_time,
            delivery_time=delivery_time,
            timeline=timeline,
            critical_path_items=critical_path,
            delivery_windows=[delivery_window],
            buffer_time_minutes=buffer_minutes,
            route=[],
            staffing_notes=staffing_notes,
        )

        msg = _wrap_message(
            payload=plan,
            message_type="logistics_plan",
            target_agent="stock_manager",
            session_id=session_id,
        )

        log_event(
            agent_id=AGENT_ID,
            action="build_logistics_plan",
            status="success",
            details={
                "event_id": plan.event_id,
                "prep_start_time": plan.prep_start_time,
                "delivery_time": plan.delivery_time,
                "buffer_time_minutes": plan.buffer_time_minutes,
                "critical_path_count": len(plan.critical_path_items),
                "logistics_ai_reasoning": ai_reasoning,
            },
        )

        return msg

    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        log_event(
            agent_id=AGENT_ID,
            action="build_logistics_plan",
            status="error",
            details={"error": str(exc)},
        )
        return _error_message(
            session_id=session_id,
            error_code="LOGISTICS_PLAN_ERROR",
            message="Failed to generate logistics plan.",
            details={"error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id=AGENT_ID,
            action="build_logistics_plan",
            status="error",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
        return _error_message(
            session_id=session_id,
            error_code="LOGISTICS_UNEXPECTED_ERROR",
            message="Unexpected error while generating logistics plan.",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
