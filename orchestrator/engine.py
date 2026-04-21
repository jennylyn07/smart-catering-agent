from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import ValidationError

from agents.accountant import run_accountant
from agents.concierge import run_concierge
from agents.head_chef import revise_menu_plan, run_head_chef
from agents.logistics import run_logistics
from agents.stock_manager import run_stock_manager
from utils.json_schema import (
    AgentMessage,
    CostReport,
    ErrorMessage,
    EventSpecification,
    FinalPlan,
    LogisticsPlan,
    MenuPlan,
    MessageHeader,
    MessageMetadata,
    MessageSignature,
    ProcurementList,
)
from utils.logger import log_event

AGENT_ID = "orchestrator"


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
        target_agent: Downstream consumer identifier (API layer here).
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
    metadata = MessageMetadata(confidence_score=0.8)

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
    """Create an error AgentMessage for orchestration failures.

    Args:
        session_id: Correlation/session identifier for the request.
        error_code: Stable error code for the failure class.
        message: Human-readable error message.
        details: Optional structured error details.

    Returns:
        An AgentMessage whose payload is an ErrorMessage.
    """
    payload = ErrorMessage(error_code=error_code, message=message, agent_id=AGENT_ID, details=details or {})
    return _wrap_message(payload=payload, message_type="error", target_agent="api", session_id=session_id)


def _handoff(*, finished: str, next_agent: str, session_id: str, details: Optional[dict[str, Any]] = None) -> None:
    """Log an agent-to-agent handoff during orchestration.

    Args:
        finished: Agent that just completed.
        next_agent: Agent that will run next.
        session_id: Correlation/session identifier for the request.
        details: Optional structured details to include in the log entry.

    Returns:
        None
    """
    log_event(
        agent_id=AGENT_ID,
        action="agent_handoff",
        status="success",
        details={
            "finished": finished,
            "next": next_agent,
            "timestamp": _now_utc().isoformat(),
            "session_id": session_id,
            **(details or {}),
        },
    )


def _is_error(msg: AgentMessage) -> bool:
    """Return True if an AgentMessage represents an ErrorMessage.

    Args:
        msg: AgentMessage to inspect.

    Returns:
        True if msg is an error message; otherwise False.
    """
    return msg.header.message_type == "error" and isinstance(msg.payload, ErrorMessage)


def _stop_on_error(*, msg: AgentMessage, failed_agent: str, session_id: str) -> Optional[AgentMessage]:
    """Stop the pipeline early if an upstream agent returned an error.

    Args:
        msg: AgentMessage returned by an agent.
        failed_agent: Identifier of the agent that failed.
        session_id: Correlation/session identifier for the request.

    Returns:
        The same error AgentMessage if msg is an error; otherwise None.
    """
    if not _is_error(msg):
        return None

    log_event(
        agent_id=AGENT_ID,
        action="pipeline_stop",
        status="error",
        details={
            "failed_agent": failed_agent,
            "error_code": msg.payload.error_code,
            "message": msg.payload.message,
            "session_id": session_id,
        },
    )
    return msg


def _within_budget(cost_report: CostReport) -> bool:
    """Determine whether a CostReport is within budget using its compatibility fields.

    Args:
        cost_report: CostReport produced by the Accountant.

    Returns:
        True if within budget or budget is unspecified; otherwise False.
    """
    if cost_report.is_within_budget is not None:
        return bool(cost_report.is_within_budget)
    if cost_report.within_budget is not None:
        return bool(cost_report.within_budget)
    if cost_report.budget_php is None:
        return True
    return cost_report.total_cost_php <= cost_report.budget_php


@dataclass(frozen=True)
class SharedContext:
    session_id: str
    event_spec: EventSpecification
    dietary_restrictions: list[str]
    budget_php: Optional[float]
    negotiation_round: int = 0


async def run_orchestration(*, raw_customer_request: str) -> AgentMessage:
    """Run the full Concierge→Head Chef→Accountant→Logistics→Stock Manager pipeline.

    Args:
        raw_customer_request: Raw customer text used as input to Concierge.

    Returns:
        An AgentMessage containing a FinalPlan payload, or an ErrorMessage on failure.
    """
    start = time.perf_counter()
    session_id = str(uuid4())

    log_event(
        agent_id=AGENT_ID,
        action="pipeline_start",
        status="started",
        details={"text_length": len(raw_customer_request), "session_id": session_id},
    )

    try:
        concierge_message = await run_concierge(raw_customer_text=raw_customer_request, session_id=session_id)
        stopped = _stop_on_error(msg=concierge_message, failed_agent="concierge", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(concierge_message.payload, EventSpecification):
            raise ValueError("Concierge did not return EventSpecification")
        _handoff(finished="concierge", next_agent="head_chef", session_id=session_id)

        event_spec = concierge_message.payload
        ctx = SharedContext(
            session_id=session_id,
            event_spec=event_spec,
            dietary_restrictions=list(event_spec.dietary_restrictions),
            budget_php=event_spec.budget_php,
            negotiation_round=0,
        )

        menu_plan_message = await run_head_chef(event_spec=ctx.event_spec, session_id=ctx.session_id)
        stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(menu_plan_message.payload, MenuPlan):
            raise ValueError("Head Chef did not return MenuPlan")
        _handoff(finished="head_chef", next_agent="accountant", session_id=session_id)

        cost_report_message = await run_accountant(
            menu_plan_message=menu_plan_message,
            event_spec=ctx.event_spec,
            session_id=ctx.session_id,
        )
        stopped = _stop_on_error(msg=cost_report_message, failed_agent="accountant", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(cost_report_message.payload, CostReport):
            raise ValueError("Accountant did not return CostReport")

        negotiation_rounds_used = 0
        while not _within_budget(cost_report_message.payload) and negotiation_rounds_used < 3:
            negotiation_rounds_used += 1
            flagged = list(cost_report_message.payload.flagged_items)

            log_event(
                agent_id=AGENT_ID,
                action="negotiation_round",
                status="started",
                details={
                    "round": negotiation_rounds_used,
                    "flagged_items": flagged,
                    "budget_php": ctx.budget_php,
                },
            )

            menu_plan_message = await revise_menu_plan(
                event_spec=ctx.event_spec,
                previous_menu_plan_message=menu_plan_message,
                flagged_items=flagged,
                session_id=ctx.session_id,
            )
            stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
            if stopped is not None:
                return stopped
            if not isinstance(menu_plan_message.payload, MenuPlan):
                raise ValueError("Head Chef revision did not return MenuPlan")

            _handoff(finished="head_chef", next_agent="accountant", session_id=session_id, details={"round": negotiation_rounds_used})

            cost_report_message = await run_accountant(
                menu_plan_message=menu_plan_message,
                event_spec=ctx.event_spec,
                session_id=ctx.session_id,
            )
            stopped = _stop_on_error(msg=cost_report_message, failed_agent="accountant", session_id=session_id)
            if stopped is not None:
                return stopped
            if not isinstance(cost_report_message.payload, CostReport):
                raise ValueError("Accountant did not return CostReport")

            log_event(
                agent_id=AGENT_ID,
                action="negotiation_round",
                status="success",
                details={
                    "round": negotiation_rounds_used,
                    "within_budget": _within_budget(cost_report_message.payload),
                    "total_cost_php": cost_report_message.payload.total_cost_php,
                },
            )

        _handoff(finished="accountant", next_agent="logistics", session_id=session_id)

        event_datetime_iso = f"{ctx.event_spec.event_date}T18:00:00+08:00"
        logistics_plan_message = await run_logistics(
            cost_report_message=cost_report_message,
            event_datetime_iso=event_datetime_iso,
            session_id=ctx.session_id,
        )
        stopped = _stop_on_error(msg=logistics_plan_message, failed_agent="logistics", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(logistics_plan_message.payload, LogisticsPlan):
            raise ValueError("Logistics did not return LogisticsPlan")

        _handoff(finished="logistics", next_agent="stock_manager", session_id=session_id)

        procurement_list_message = await run_stock_manager(
            logistics_plan_message=logistics_plan_message,
            cost_report_message=cost_report_message,
            session_id=ctx.session_id,
        )
        stopped = _stop_on_error(msg=procurement_list_message, failed_agent="stock_manager", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(procurement_list_message.payload, ProcurementList):
            raise ValueError("Stock Manager did not return ProcurementList")

        total_seconds = round(time.perf_counter() - start, 3)
        final_payload = FinalPlan(
            event_id=ctx.event_spec.event_id,
            event_specification=ctx.event_spec,
            menu_plan=menu_plan_message.payload,
            cost_report=cost_report_message.payload,
            logistics_plan=logistics_plan_message.payload,
            procurement_list=procurement_list_message.payload,
            customer_summary="",
            total_processing_time_seconds=total_seconds,
            negotiation_rounds_used=negotiation_rounds_used,
        )

        log_event(
            agent_id=AGENT_ID,
            action="pipeline_finish",
            status="success",
            details={
                "event_id": final_payload.event_id,
                "total_processing_time_seconds": final_payload.total_processing_time_seconds,
                "negotiation_rounds_used": final_payload.negotiation_rounds_used,
                "within_budget": _within_budget(final_payload.cost_report),
            },
        )

        return _wrap_message(
            payload=final_payload,
            message_type="final_plan",
            target_agent="api",
            session_id=session_id,
        )

    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        log_event(
            agent_id=AGENT_ID,
            action="pipeline_finish",
            status="error",
            details={"error": str(exc), "session_id": session_id},
        )
        return _error_message(
            session_id=session_id,
            error_code="ORCHESTRATION_ERROR",
            message="Failed to orchestrate catering plan.",
            details={"error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        log_event(
            agent_id=AGENT_ID,
            action="pipeline_finish",
            status="error",
            details={"error": str(exc), "error_type": type(exc).__name__, "session_id": session_id},
        )
        return _error_message(
            session_id=session_id,
            error_code="ORCHESTRATION_UNEXPECTED_ERROR",
            message="Unexpected error while orchestrating catering plan.",
            details={"error": str(exc), "error_type": type(exc).__name__},
        )
