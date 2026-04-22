"""utils/json_schema.py

Defines the Pydantic schemas (data shape rules) used for all agent-to-agent
communication in the Smart Catering multi-agent system.

These schemas make agent messages consistent, validated, and safer to process.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


MessagePriority = Literal["high", "medium", "low"]


class MessageHeader(BaseModel):
    """Standard header used by every agent message."""

    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    agent_id: str
    target_agent: str
    timestamp: datetime
    message_type: str
    version: str = "1.0"


class MessageMetadata(BaseModel):
    """Metadata used for retries, dependencies, and confidence."""

    model_config = ConfigDict(extra="forbid")

    confidence_score: float = Field(ge=0.0, le=1.0)
    dependencies: List[str] = Field(default_factory=list)
    priority: MessagePriority = "medium"
    retry_count: int = Field(default=0, ge=0)


class MessageSignature(BaseModel):
    """Signature block for basic integrity/session tracking."""

    model_config = ConfigDict(extra="forbid")

    hash: str
    session_id: str


class EventSpecification(BaseModel):
    """Normalized customer request produced by the Concierge agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_name: Optional[str] = None
    event_date: str
    location: str
    guest_count: int = Field(ge=1)
    budget_php: Optional[float] = Field(default=None, ge=0)
    cuisine_preferences: List[str] = Field(default_factory=list)
    dietary_restrictions: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class MenuItem(BaseModel):
    """A single dish with portioning information."""

    model_config = ConfigDict(extra="forbid")

    name: str
    category: Optional[str] = None
    servings: int = Field(ge=1)
    ingredients: List[str] = Field(default_factory=list)


class MenuPlan(BaseModel):
    """Menu proposal produced by the Head Chef agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    menu_items: List[MenuItem]
    rationale: Optional[str] = None
    allergy_flags: List[str] = Field(default_factory=list)


class CostLineItem(BaseModel):
    """A single cost breakdown line."""

    model_config = ConfigDict(extra="forbid")

    item: str
    quantity: float = Field(ge=0)
    unit: str
    unit_price_php: float = Field(ge=0)
    subtotal_php: float = Field(ge=0)


class DishCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dish_name: str
    cost_php: float = Field(ge=0)


class AlternativeRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: str
    recommended_item: str
    reason: Optional[str] = None


class CostReport(BaseModel):
    """Cost calculation produced by the Accountant agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    cost_per_dish: List[DishCost] = Field(default_factory=list)
    total_cost_php: float = Field(ge=0)
    budget_php: Optional[float] = Field(default=None, ge=0)
    within_budget: Optional[bool] = None
    is_within_budget: Optional[bool] = None
    over_budget_by_php: float = Field(default=0, ge=0)
    flagged_items: List[str] = Field(default_factory=list)
    recommended_alternatives: List[AlternativeRecommendation] = Field(default_factory=list)
    line_items: List[CostLineItem] = Field(default_factory=list)
    notes: Optional[str] = None


class DeliveryStop(BaseModel):
    """A single logistics stop."""

    model_config = ConfigDict(extra="forbid")

    name: str
    address: str
    eta: Optional[str] = None


class TimelineTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str
    description: str
    owner: str


class DeliveryWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time: str
    end_time: str
    notes: Optional[str] = None


class LogisticsPlan(BaseModel):
    """Timeline and routing produced by the Logistics Lead agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    prep_start_time: str
    delivery_time: str
    timeline: List[TimelineTask] = Field(default_factory=list)
    critical_path_items: List[str] = Field(default_factory=list)
    delivery_windows: List[DeliveryWindow] = Field(default_factory=list)
    buffer_time_minutes: int = Field(default=30, ge=1)
    route: List[DeliveryStop] = Field(default_factory=list)
    staffing_notes: Optional[str] = None


class ProcurementItem(BaseModel):
    """An inventory/procurement line item."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str
    required_quantity: float = Field(ge=0)
    unit: str
    in_stock_quantity: float = Field(ge=0)
    to_buy_quantity: float = Field(ge=0)


class StockItem(BaseModel):
    """A simple stock record (what we already have on-hand)."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str
    quantity: float = Field(ge=0)
    unit: str


class PurchaseItem(BaseModel):
    """A procurement purchase recommendation line."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str
    quantity: float = Field(ge=0)
    unit: str
    estimated_cost_php: float = Field(ge=0)
    suggested_supplier: Optional[str] = None
    lead_time_days: Optional[int] = Field(default=None, ge=0)


class ProcurementList(BaseModel):
    """Procurement output produced by the Stock Manager agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    items_in_stock: List[StockItem] = Field(default_factory=list)
    items_to_purchase: List[PurchaseItem] = Field(default_factory=list)
    out_of_stock_alerts: List[str] = Field(default_factory=list)
    waste_risk_items: List[str] = Field(default_factory=list)
    total_procurement_cost_php: float = Field(default=0, ge=0)

    # Backward-compatible fields from earlier iterations
    items: List[ProcurementItem] = Field(default_factory=list)
    preferred_suppliers: List[str] = Field(default_factory=list)
    waste_minimization_notes: Optional[str] = None


class FinalPlan(BaseModel):
    """Final plan returned to the customer after orchestration."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_specification: EventSpecification
    menu_plan: MenuPlan
    cost_report: CostReport
    logistics_plan: LogisticsPlan
    procurement_list: ProcurementList
    customer_summary: str
    total_processing_time_seconds: float = Field(default=0, ge=0)
    negotiation_rounds_used: int = Field(default=0, ge=0)


class ProcurementOptimizationSummary(BaseModel):
    """Summary of bulk procurement optimization across multiple events."""

    model_config = ConfigDict(extra="forbid")

    shared_ingredients: List[str] = Field(default_factory=list)
    original_total_procurement_cost_php: float = Field(default=0, ge=0)
    optimized_total_procurement_cost_php: float = Field(default=0, ge=0)
    estimated_savings_php: float = Field(default=0, ge=0)
    notes: Optional[str] = None


class MultiEventPlan(BaseModel):
    """Multi-event output containing individual plans and shared procurement optimization."""

    model_config = ConfigDict(extra="forbid")

    plans: List[FinalPlan]
    optimized_shared_procurement: List[PurchaseItem] = Field(default_factory=list)
    procurement_optimization_summary: ProcurementOptimizationSummary


class ErrorMessage(BaseModel):
    """Standard error payload when a step fails but the system continues."""

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    agent_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


AgentPayload = Union[
    EventSpecification,
    MenuPlan,
    CostReport,
    LogisticsPlan,
    ProcurementList,
    FinalPlan,
    MultiEventPlan,
    ErrorMessage,
]


class AgentMessage(BaseModel):
    """Wrapper format used for all agent-to-agent messages."""

    model_config = ConfigDict(extra="forbid")

    header: MessageHeader
    payload: AgentPayload
    metadata: MessageMetadata
    signature: MessageSignature
