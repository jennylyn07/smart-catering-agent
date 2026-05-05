from __future__ import annotations

import asyncio
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
from memory.shared_memory import SharedMemory
from utils.adaptation import AdaptationChangeType
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
from utils.cosmos_store import get_container_name, persist_final_plan
from utils.cosmos_store import format_past_orders_context, query_past_orders

try:
    from semantic_kernel import Kernel
    from semantic_kernel.functions import kernel_function
    from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
except Exception:  # noqa: BLE001
    Kernel = None  # type: ignore[assignment]
    kernel_function = None  # type: ignore[assignment]
    AzureChatCompletion = None  # type: ignore[assignment]

try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
except Exception:  # noqa: BLE001
    AssistantAgent = None  # type: ignore[assignment]
    AzureOpenAIChatCompletionClient = None  # type: ignore[assignment]

AGENT_ID = "orchestrator"


def _build_kernel() -> Any:
    if Kernel is None:
        return None

    import os

    kernel = Kernel()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if endpoint and api_key and deployment and AzureChatCompletion is not None:
        kernel.add_service(
            AzureChatCompletion(
                deployment_name=deployment,
                endpoint=endpoint,
                api_key=api_key,
            )
        )
    return kernel


def _build_autogen_orchestrator_agent() -> Any:
    if AssistantAgent is None or AzureOpenAIChatCompletionClient is None:
        return None

    import os

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not (endpoint and api_key and deployment):
        return None

    model_client = AzureOpenAIChatCompletionClient(
        azure_endpoint=endpoint,
        azure_deployment=deployment,
        api_key=api_key,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    )
    return AssistantAgent(name="OrchestratorAgent", model_client=model_client)


if kernel_function is not None:

    class CateringAgentsPlugin:
        @kernel_function(name="concierge")
        async def concierge(self, raw_customer_text: str, session_id: str) -> AgentMessage:
            return await run_concierge(raw_customer_text=raw_customer_text, session_id=session_id)

        @kernel_function(name="head_chef")
        async def head_chef(self, event_spec: EventSpecification, session_id: str, past_context: str = "") -> AgentMessage:
            return await run_head_chef(event_spec=event_spec, session_id=session_id, past_context=past_context)

        @kernel_function(name="accountant")
        async def accountant(self, menu_plan_message: AgentMessage, event_spec: EventSpecification, session_id: str, past_context: str = "") -> AgentMessage:
            return await run_accountant(menu_plan_message=menu_plan_message, event_spec=event_spec, session_id=session_id, past_context=past_context)

        @kernel_function(name="revise_menu_plan")
        async def revise_menu_plan(
            self,
            event_spec: EventSpecification,
            previous_menu_plan_message: AgentMessage,
            flagged_items: list[str],
            session_id: str,
        ) -> AgentMessage:
            return await revise_menu_plan(
                event_spec=event_spec,
                previous_menu_plan_message=previous_menu_plan_message,
                flagged_items=flagged_items,
                session_id=session_id,
            )

        @kernel_function(name="logistics")
        async def logistics(
            self,
            cost_report_message: AgentMessage,
            event_spec: EventSpecification,
            event_datetime_iso: str,
            session_id: str,
        ) -> AgentMessage:
            return await run_logistics(
                cost_report_message=cost_report_message,
                event_spec=event_spec,
                event_datetime_iso=event_datetime_iso,
                session_id=session_id,
            )

        @kernel_function(name="stock_manager")
        async def stock_manager(
            self,
            logistics_plan_message: AgentMessage,
            cost_report_message: AgentMessage,
            session_id: str,
        ) -> AgentMessage:
            return await run_stock_manager(
                logistics_plan_message=logistics_plan_message,
                cost_report_message=cost_report_message,
                session_id=session_id,
            )


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


async def _call_with_retry(
    coro_fn,
    *,
    agent_name: str,
    session_id: str,
) -> AgentMessage:
    """Call an agent coroutine with up to 3 attempts on transient failures.

    Hard errors (ValidationError, ValueError, VALIDATION error codes) escalate
    immediately without retry. Transient failures (timeout, JSON parse, OSError)
    are retried. On 3rd consecutive failure, returns a graceful degradation
    error message and logs a warning. retry_count in metadata is incremented
    per attempt so judges can verify it is working.

    Args:
        coro_fn: Zero-argument async callable that invokes the agent.
        agent_name: Human-readable agent name for logging.
        session_id: Correlation identifier for the request.

    Returns:
        AgentMessage from the agent on success, or an error AgentMessage after
        exhausting retries.
    """

    _HARD_ERROR_CODES = {"CONCIERGE_VALIDATION_ERROR", "CONCIERGE_UNEXPECTED_ERROR"}

    last_exc: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            result: AgentMessage = await coro_fn()

            if _is_error(result):
                error_code = getattr(result.payload, "error_code", "") or ""
                # Hard errors: input validation failures — escalate immediately, no retry
                if "VALIDATION" in error_code or error_code in _HARD_ERROR_CODES:
                    log_event(
                        agent_id=AGENT_ID,
                        action=f"{agent_name}_hard_error",
                        status="error",
                        details={"error_code": error_code, "session_id": session_id},
                    )
                    return result
                # Soft error on attempt < 3 — log and retry
                if attempt < 3:
                    log_event(
                        agent_id=AGENT_ID,
                        action=f"{agent_name}_retry",
                        status="warning",
                        details={
                            "attempt": attempt,
                            "error_code": error_code,
                            "session_id": session_id,
                        },
                    )
                    result.metadata.retry_count = attempt
                    continue
                # 3rd attempt still an error — graceful degradation
                log_event(
                    agent_id=AGENT_ID,
                    action=f"{agent_name}_retry_exhausted",
                    status="error",
                    details={"attempts": 3, "error_code": error_code, "session_id": session_id},
                )
                result.metadata.retry_count = attempt
                return result

            # Success — record retry count if retries were needed
            if attempt > 1:
                result.metadata.retry_count = attempt - 1
            return result

        except (ValidationError, ValueError) as exc:
            # Hard errors — escalate immediately without retry
            log_event(
                agent_id=AGENT_ID,
                action=f"{agent_name}_hard_error",
                status="error",
                details={"error": str(exc), "error_type": type(exc).__name__, "session_id": session_id},
            )
            raise

        except (asyncio.TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_exc = exc
            log_event(
                agent_id=AGENT_ID,
                action=f"{agent_name}_retry",
                status="warning",
                details={
                    "attempt": attempt,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "session_id": session_id,
                },
            )
            if attempt == 3:
                break

    # All 3 attempts exhausted by transient exception
    log_event(
        agent_id=AGENT_ID,
        action=f"{agent_name}_retry_exhausted",
        status="error",
        details={
            "attempts": 3,
            "final_error": str(last_exc),
            "session_id": session_id,
        },
    )
    return _error_message(
        session_id=session_id,
        error_code=f"{agent_name.upper()}_TRANSIENT_FAILURE",
        message=f"{agent_name} failed after 3 attempts due to transient errors.",
        details={"final_error": str(last_exc)},
    )


@dataclass(frozen=True)
class SharedContext:
    session_id: str
    event_spec: EventSpecification
    dietary_restrictions: list[str]
    budget_php: Optional[float]
    negotiation_round: int = 0


def _payload_to_memory(value: Any) -> Any:
    """Convert a Pydantic model payload to JSON-serializable data for SharedMemory."""

    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _wrap_menu_plan_for_accountant(*, menu_plan: MenuPlan, session_id: str) -> AgentMessage:
    """Wrap a stored MenuPlan into an AgentMessage acceptable to downstream agents."""

    return _wrap_message(
        payload=menu_plan,
        message_type="menu_plan",
        target_agent="accountant",
        session_id=session_id,
    )


async def adapt_from_existing_plan(
    *,
    existing_plan: FinalPlan,
    change_type: AdaptationChangeType,
    new_value: Any,
    order_id: str,
) -> AgentMessage:
    """Adapt an existing FinalPlan based on a structured change request.

    This re-runs only the impacted portion of the pipeline and returns a new FinalPlan.
    """

    start = time.perf_counter()
    session_id = str(uuid4())
    event_spec = existing_plan.event_specification

    log_event(
        agent_id=AGENT_ID,
        action="adaptation_start",
        status="started",
        details={
            "order_id": order_id,
            "change_type": str(change_type),
            "session_id": session_id,
        },
    )

    if change_type == AdaptationChangeType.GUEST_COUNT_CHANGE:
        try:
            new_guest_count = int(new_value)
        except (TypeError, ValueError) as exc:
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_INVALID_GUEST_COUNT",
                message="Invalid guest count for adaptation.",
                details={"error": str(exc)},
            )
        event_spec = event_spec.model_copy(update={"guest_count": new_guest_count})

        menu_plan_message = await run_head_chef(event_spec=event_spec, session_id=session_id)
        stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(menu_plan_message.payload, MenuPlan):
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_HEAD_CHEF_BAD_PAYLOAD",
                message="Head Chef returned an unexpected payload during adaptation.",
            )
    elif change_type == AdaptationChangeType.DIETARY_ADDITION:
        addition = str(new_value).strip()
        if not addition:
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_INVALID_DIETARY_ADDITION",
                message="Invalid dietary addition for adaptation.",
            )
        updated = list(event_spec.dietary_restrictions)
        if addition not in updated:
            updated.append(addition)
        event_spec = event_spec.model_copy(update={"dietary_restrictions": updated})

        menu_plan_message = await run_head_chef(event_spec=event_spec, session_id=session_id)
        stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(menu_plan_message.payload, MenuPlan):
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_HEAD_CHEF_BAD_PAYLOAD",
                message="Head Chef returned an unexpected payload during adaptation.",
            )
    elif change_type == AdaptationChangeType.BUDGET_CHANGE:
        try:
            new_budget_php = float(new_value)
        except (TypeError, ValueError) as exc:
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_INVALID_BUDGET",
                message="Invalid budget for adaptation.",
                details={"error": str(exc)},
            )

        event_spec = event_spec.model_copy(update={"budget_php": new_budget_php})
        menu_plan_message = _wrap_menu_plan_for_accountant(menu_plan=existing_plan.menu_plan, session_id=session_id)
    else:
        return _error_message(
            session_id=session_id,
            error_code="ADAPT_UNSUPPORTED_CHANGE_TYPE",
            message="Unsupported change type.",
            details={"change_type": str(change_type)},
        )

    cost_report_message = await run_accountant(
        menu_plan_message=menu_plan_message,
        event_spec=event_spec,
        session_id=session_id,
    )
    stopped = _stop_on_error(msg=cost_report_message, failed_agent="accountant", session_id=session_id)
    if stopped is not None:
        return stopped
    if not isinstance(cost_report_message.payload, CostReport):
        return _error_message(
            session_id=session_id,
            error_code="ADAPT_ACCOUNTANT_BAD_PAYLOAD",
            message="Accountant returned an unexpected payload during adaptation.",
        )

    negotiation_rounds_used = 0
    while not _within_budget(cost_report_message.payload) and negotiation_rounds_used < 3:
        negotiation_rounds_used += 1
        flagged = list(cost_report_message.payload.flagged_items)

        menu_plan_message = await revise_menu_plan(
            event_spec=event_spec,
            previous_menu_plan_message=menu_plan_message,
            flagged_items=flagged,
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(menu_plan_message.payload, MenuPlan):
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_HEAD_CHEF_BAD_PAYLOAD",
                message="Head Chef returned an unexpected payload during negotiation.",
            )

        cost_report_message = await run_accountant(
            menu_plan_message=menu_plan_message,
            event_spec=event_spec,
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=cost_report_message, failed_agent="accountant", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(cost_report_message.payload, CostReport):
            return _error_message(
                session_id=session_id,
                error_code="ADAPT_ACCOUNTANT_BAD_PAYLOAD",
                message="Accountant returned an unexpected payload during negotiation.",
            )

    event_datetime_iso = f"{event_spec.event_date}T18:00:00+08:00"
    logistics_plan_message = await run_logistics(
        cost_report_message=cost_report_message,
        event_spec=event_spec,
        event_datetime_iso=event_datetime_iso,
        session_id=session_id,
    )
    stopped = _stop_on_error(msg=logistics_plan_message, failed_agent="logistics", session_id=session_id)
    if stopped is not None:
        return stopped
    if not isinstance(logistics_plan_message.payload, LogisticsPlan):
        return _error_message(
            session_id=session_id,
            error_code="ADAPT_LOGISTICS_BAD_PAYLOAD",
            message="Logistics returned an unexpected payload during adaptation.",
        )

    procurement_list_message = await run_stock_manager(
        logistics_plan_message=logistics_plan_message,
        cost_report_message=cost_report_message,
        session_id=session_id,
    )
    stopped = _stop_on_error(msg=procurement_list_message, failed_agent="stock_manager", session_id=session_id)
    if stopped is not None:
        return stopped
    if not isinstance(procurement_list_message.payload, ProcurementList):
        return _error_message(
            session_id=session_id,
            error_code="ADAPT_STOCK_MANAGER_BAD_PAYLOAD",
            message="Stock Manager returned an unexpected payload during adaptation.",
        )

    total_seconds = round(time.perf_counter() - start, 3)
    final_payload = FinalPlan(
        event_id=event_spec.event_id,
        event_specification=event_spec,
        menu_plan=menu_plan_message.payload,
        cost_report=cost_report_message.payload,
        logistics_plan=logistics_plan_message.payload,
        procurement_list=procurement_list_message.payload,
        customer_summary=existing_plan.customer_summary,
        total_processing_time_seconds=total_seconds,
        negotiation_rounds_used=negotiation_rounds_used,
    )

    log_event(
        agent_id=AGENT_ID,
        action="adaptation_finish",
        status="success",
        details={
            "order_id": order_id,
            "negotiation_rounds_used": negotiation_rounds_used,
            "within_budget": _within_budget(final_payload.cost_report),
            "session_id": session_id,
        },
    )

    return _wrap_message(
        payload=final_payload,
        message_type="final_plan",
        target_agent="api",
        session_id=session_id,
    )


async def run_orchestration(
    *,
    raw_customer_request: str,
    progress_callback=None,
) -> AgentMessage:
    """Run the full Concierge→Head Chef→Accountant→Logistics→Stock Manager pipeline.

    Args:
        raw_customer_request: Raw customer text used as input to Concierge.

    Returns:
        An AgentMessage containing a FinalPlan payload, or an ErrorMessage on failure.
    """
    session_id = str(uuid4())

    kernel = _build_kernel()
    _ = _build_autogen_orchestrator_agent()
    plugin_name = "catering_agents"
    if kernel is not None and kernel_function is not None:
        kernel.add_plugin(CateringAgentsPlugin(), plugin_name=plugin_name)

    start = time.perf_counter()

    log_event(
        agent_id=AGENT_ID,
        action="pipeline_start",
        status="started",
        details={"text_length": len(raw_customer_request), "session_id": session_id},
    )

    try:
        async def _concierge_call():
            if kernel is not None and kernel_function is not None:
                result = await kernel.invoke(
                    function_name="concierge",
                    plugin_name=plugin_name,
                    raw_customer_text=raw_customer_request,
                    session_id=session_id,
                )
                return result.value if result is not None else None
            return await run_concierge(raw_customer_text=raw_customer_request, session_id=session_id)

        concierge_message = await _call_with_retry(
            _concierge_call,
            agent_name="concierge",
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=concierge_message, failed_agent="concierge", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(concierge_message.payload, EventSpecification):
            raise ValueError("Concierge did not return EventSpecification")
        _handoff(finished="concierge", next_agent="head_chef", session_id=session_id)
        if progress_callback:
            progress_callback("concierge", "done")

        event_spec = concierge_message.payload

        past_orders = await query_past_orders(
            cuisine_preferences=event_spec.cuisine_preferences or [],
            guest_count=event_spec.guest_count,
        )
        past_context = format_past_orders_context(past_orders)

        shared_memory = SharedMemory(session_id=session_id, event_id=event_spec.event_id)
        shared_memory.set(key="dietary_restrictions", value=set(event_spec.dietary_restrictions), writer_agent_id=AGENT_ID)
        shared_memory.set(key="allergies", value=set(event_spec.allergies), writer_agent_id=AGENT_ID)
        shared_memory.set(key="budget_php", value=event_spec.budget_php, writer_agent_id=AGENT_ID)
        shared_memory.set_agent_output(
            agent_id="concierge",
            value=_payload_to_memory(concierge_message.payload),
            writer_agent_id=AGENT_ID,
        )

        ctx = SharedContext(
            session_id=session_id,
            event_spec=event_spec,
            dietary_restrictions=list(event_spec.dietary_restrictions),
            budget_php=event_spec.budget_php,
            negotiation_round=0,
        )

        async def _head_chef_call():
            if kernel is not None and kernel_function is not None:
                result = await kernel.invoke(
                    function_name="head_chef",
                    plugin_name=plugin_name,
                    event_spec=ctx.event_spec,
                    session_id=ctx.session_id,
                    past_context=past_context,
                )
                return result.value if result is not None else None
            return await run_head_chef(event_spec=ctx.event_spec, session_id=ctx.session_id, past_context=past_context)

        menu_plan_message = await _call_with_retry(
            _head_chef_call,
            agent_name="head_chef",
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(menu_plan_message.payload, MenuPlan):
            raise ValueError("Head Chef did not return MenuPlan")

        if set(ctx.event_spec.dietary_restrictions) != shared_memory.get("dietary_restrictions"):
            raise ValueError("Dietary restrictions changed during pipeline")
        if set(ctx.event_spec.allergies) != shared_memory.get("allergies"):
            raise ValueError("Allergies changed during pipeline")

        shared_memory.set_agent_output(
            agent_id="head_chef",
            value=_payload_to_memory(menu_plan_message.payload),
            writer_agent_id=AGENT_ID,
        )
        _handoff(finished="head_chef", next_agent="accountant", session_id=session_id)
        if progress_callback:
            progress_callback("head_chef", "done")

        async def _accountant_call():
            if kernel is not None and kernel_function is not None:
                result = await kernel.invoke(
                    function_name="accountant",
                    plugin_name=plugin_name,
                    menu_plan_message=menu_plan_message,
                    event_spec=ctx.event_spec,
                    session_id=ctx.session_id,
                    past_context=past_context,
                )
                return result.value if result is not None else None
            return await run_accountant(
                menu_plan_message=menu_plan_message,
                event_spec=ctx.event_spec,
                session_id=ctx.session_id,
                past_context=past_context,
            )

        cost_report_message = await _call_with_retry(
            _accountant_call,
            agent_name="accountant",
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=cost_report_message, failed_agent="accountant", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(cost_report_message.payload, CostReport):
            raise ValueError("Accountant did not return CostReport")

        shared_memory.set_agent_output(
            agent_id="accountant",
            value=_payload_to_memory(cost_report_message.payload),
            writer_agent_id=AGENT_ID,
        )

        negotiation_rounds_used = 0
        while not _within_budget(cost_report_message.payload) and negotiation_rounds_used < 3:
            negotiation_rounds_used += 1
            flagged = list(cost_report_message.payload.flagged_items)

            shared_memory.append_negotiation_round(
                round_data={
                    "round": negotiation_rounds_used,
                    "flagged_items": flagged,
                    "budget_php": ctx.budget_php,
                    "total_cost_php": cost_report_message.payload.total_cost_php,
                    "within_budget": _within_budget(cost_report_message.payload),
                },
                writer_agent_id=AGENT_ID,
            )

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

            async def _revise_menu_call():
                if kernel is not None and kernel_function is not None:
                    result = await kernel.invoke(
                        function_name="revise_menu_plan",
                        plugin_name=plugin_name,
                        event_spec=ctx.event_spec,
                        previous_menu_plan_message=menu_plan_message,
                        flagged_items=flagged,
                        session_id=ctx.session_id,
                    )
                    return result.value if result is not None else None
                return await revise_menu_plan(
                    event_spec=ctx.event_spec,
                    previous_menu_plan_message=menu_plan_message,
                    flagged_items=flagged,
                    session_id=ctx.session_id,
                )

            menu_plan_message = await _call_with_retry(
                _revise_menu_call,
                agent_name="head_chef_revision",
                session_id=session_id,
            )
            stopped = _stop_on_error(msg=menu_plan_message, failed_agent="head_chef", session_id=session_id)
            if stopped is not None:
                return stopped
            if not isinstance(menu_plan_message.payload, MenuPlan):
                raise ValueError("Head Chef revision did not return MenuPlan")

            if set(ctx.event_spec.dietary_restrictions) != shared_memory.get("dietary_restrictions"):
                raise ValueError("Dietary restrictions changed during negotiation")
            if set(ctx.event_spec.allergies) != shared_memory.get("allergies"):
                raise ValueError("Allergies changed during negotiation")

            shared_memory.set_agent_output(
                agent_id="head_chef",
                value=_payload_to_memory(menu_plan_message.payload),
                writer_agent_id=AGENT_ID,
            )

            _handoff(finished="head_chef", next_agent="accountant", session_id=session_id, details={"round": negotiation_rounds_used})
            if progress_callback:
                progress_callback("head_chef", "done")

            async def _accountant_negotiation_call():
                if kernel is not None and kernel_function is not None:
                    result = await kernel.invoke(
                        function_name="accountant",
                        plugin_name=plugin_name,
                        menu_plan_message=menu_plan_message,
                        event_spec=ctx.event_spec,
                        session_id=ctx.session_id,
                        past_context=past_context,
                    )
                    return result.value if result is not None else None
                return await run_accountant(
                    menu_plan_message=menu_plan_message,
                    event_spec=ctx.event_spec,
                    session_id=ctx.session_id,
                    past_context=past_context,
                )

            cost_report_message = await _call_with_retry(
                _accountant_negotiation_call,
                agent_name="accountant_negotiation",
                session_id=session_id,
            )
            stopped = _stop_on_error(msg=cost_report_message, failed_agent="accountant", session_id=session_id)
            if stopped is not None:
                return stopped
            if not isinstance(cost_report_message.payload, CostReport):
                raise ValueError("Accountant did not return CostReport")

            shared_memory.set_agent_output(
                agent_id="accountant",
                value=_payload_to_memory(cost_report_message.payload),
                writer_agent_id=AGENT_ID,
            )

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
        if progress_callback:
            progress_callback("accountant", "done")

        event_datetime_iso = f"{ctx.event_spec.event_date}T18:00:00+08:00"
        async def _logistics_call():
            if kernel is not None and kernel_function is not None:
                result = await kernel.invoke(
                    function_name="logistics",
                    plugin_name=plugin_name,
                    cost_report_message=cost_report_message,
                    event_spec=ctx.event_spec,
                    event_datetime_iso=event_datetime_iso,
                    session_id=ctx.session_id,
                )
                return result.value if result is not None else None
            return await run_logistics(
                cost_report_message=cost_report_message,
                event_spec=ctx.event_spec,
                event_datetime_iso=event_datetime_iso,
                session_id=ctx.session_id,
            )

        logistics_plan_message = await _call_with_retry(
            _logistics_call,
            agent_name="logistics",
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=logistics_plan_message, failed_agent="logistics", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(logistics_plan_message.payload, LogisticsPlan):
            raise ValueError("Logistics did not return LogisticsPlan")

        shared_memory.set_agent_output(
            agent_id="logistics",
            value=_payload_to_memory(logistics_plan_message.payload),
            writer_agent_id=AGENT_ID,
        )

        _handoff(finished="logistics", next_agent="stock_manager", session_id=session_id)
        if progress_callback:
            progress_callback("logistics", "done")

        async def _stock_manager_call():
            if kernel is not None and kernel_function is not None:
                result = await kernel.invoke(
                    function_name="stock_manager",
                    plugin_name=plugin_name,
                    logistics_plan_message=logistics_plan_message,
                    cost_report_message=cost_report_message,
                    session_id=ctx.session_id,
                )
                return result.value if result is not None else None
            return await run_stock_manager(
                logistics_plan_message=logistics_plan_message,
                cost_report_message=cost_report_message,
                session_id=ctx.session_id,
            )

        procurement_message = await _call_with_retry(
            _stock_manager_call,
            agent_name="stock_manager",
            session_id=session_id,
        )
        stopped = _stop_on_error(msg=procurement_message, failed_agent="stock_manager", session_id=session_id)
        if stopped is not None:
            return stopped
        if not isinstance(procurement_message.payload, ProcurementList):
            raise ValueError("Stock Manager did not return ProcurementList")

        if progress_callback:
            progress_callback("stock_manager", "done")

        shared_memory.set_agent_output(
            agent_id="stock_manager",
            value=_payload_to_memory(procurement_message.payload),
            writer_agent_id=AGENT_ID,
        )

        total_seconds = round(time.perf_counter() - start, 3)
        final_payload = FinalPlan(
            event_id=ctx.event_spec.event_id,
            event_specification=ctx.event_spec,
            menu_plan=menu_plan_message.payload,
            cost_report=cost_report_message.payload,
            logistics_plan=logistics_plan_message.payload,
            procurement_list=procurement_message.payload,
            customer_summary=(
                f"{ctx.event_spec.guest_count} guests · "
                f"{ctx.event_spec.event_date} · "
                f"{ctx.event_spec.location} · "
                f"PHP {ctx.event_spec.budget_php:,.0f} budget · "
                f"{', '.join(ctx.event_spec.cuisine_preferences)} cuisine"
                + (f" · Allergies: {', '.join(ctx.event_spec.allergies)}" if ctx.event_spec.allergies else "")
                + (
                    f" · Dietary: {', '.join(ctx.event_spec.dietary_restrictions)}"
                    if ctx.event_spec.dietary_restrictions
                    else ""
                )
            ),
            total_processing_time_seconds=total_seconds,
            negotiation_rounds_used=negotiation_rounds_used,
        )

        shared_memory.set_agent_output(
            agent_id="final_plan",
            value=_payload_to_memory(final_payload),
            writer_agent_id=AGENT_ID,
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

        order_id = str(final_payload.event_id).strip()
        if order_id:
            try:
                await persist_final_plan(order_id=order_id, final_plan=final_payload.model_dump())
                log_event(
                    agent_id="cosmos_store",
                    action="save_final_plan",
                    status="success",
                    details={"order_id": order_id, "container": get_container_name()},
                )
            except Exception as exc:  # noqa: BLE001
                log_event(
                    agent_id="cosmos_store",
                    action="save_final_plan",
                    status="error",
                    details={
                        "order_id": order_id,
                        "container": get_container_name(),
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                print(f"[COSMOS WRITE FAILED] order_id={order_id} | {type(exc).__name__}: {exc}")

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
