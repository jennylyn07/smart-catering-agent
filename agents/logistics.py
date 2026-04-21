from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import ValidationError

from utils.json_schema import (
    AgentMessage,
    CostReport,
    DeliveryWindow,
    ErrorMessage,
    LogisticsPlan,
    MessageHeader,
    MessageMetadata,
    MessageSignature,
    TimelineTask,
)
from utils.logger import log_event

AGENT_ID = "logistics"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _wrap_message(*, payload: Any, message_type: str, target_agent: str, session_id: str) -> AgentMessage:
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
    payload = ErrorMessage(error_code=error_code, message=message, agent_id=AGENT_ID, details=details or {})
    return _wrap_message(
        payload=payload,
        message_type="error",
        target_agent="orchestrator",
        session_id=session_id,
    )


def _parse_event_datetime(value: str) -> datetime:
    text = value.strip()
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("event_datetime_iso must include timezone offset, e.g. 2026-05-20T18:00:00+08:00")
    return dt


def _fmt(dt: datetime) -> str:
    return dt.isoformat()


def _load_suppliers() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "knowledge_base" / "suppliers.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    suppliers = payload.get("suppliers")
    if not isinstance(suppliers, list):
        return []
    return suppliers


def _build_lead_time_index(suppliers: list[dict[str, Any]]) -> dict[str, int]:
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
    suppliers = _load_suppliers()
    lead_index = _build_lead_time_index(suppliers)

    long_lead: set[str] = set()
    for li in cost_report.line_items:
        lead_days = lead_index.get(li.item.strip().lower(), 0)
        if lead_days >= 2:
            long_lead.add(li.item)

    return sorted(long_lead)


def _identify_most_prep_dishes(cost_report: CostReport) -> list[str]:
    if not cost_report.cost_per_dish:
        return []

    sorted_dishes = sorted(cost_report.cost_per_dish, key=lambda d: d.cost_php, reverse=True)
    return [d.dish_name for d in sorted_dishes[:2]]


def _timeline_from_event(event_dt: datetime) -> list[TimelineTask]:
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


async def run_logistics(
    *,
    cost_report_message: AgentMessage,
    event_datetime_iso: str,
    session_id: str,
) -> AgentMessage:
    log_event(
        agent_id=AGENT_ID,
        action="build_logistics_plan",
        status="started",
        details={"event_datetime_iso": event_datetime_iso},
    )

    try:
        if not isinstance(cost_report_message.payload, CostReport):
            raise ValueError("cost_report_message payload must be a CostReport")

        cost_report: CostReport = cost_report_message.payload
        event_dt = _parse_event_datetime(event_datetime_iso)

        timeline = _timeline_from_event(event_dt)

        prep_start_time = _fmt(event_dt - timedelta(hours=12))
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

        plan = LogisticsPlan(
            event_id=cost_report.event_id,
            prep_start_time=prep_start_time,
            delivery_time=delivery_time,
            timeline=timeline,
            critical_path_items=critical_path,
            delivery_windows=[delivery_window],
            buffer_time_minutes=buffer_minutes,
            route=[],
            staffing_notes=None,
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
