from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from utils.json_schema import EventSpecification, MenuPlan, CostReport

logger = logging.getLogger(__name__)

def _extract_json_block(text: str, key: str) -> list:
    """Extract a JSON array from a text message by key.

    Args:
        text: The raw agent message text to parse.
        key: The JSON object key whose value should be a list.

    Returns:
        Parsed list, or empty list if not found/parseable.
    """
    # Try fenced code block first
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            if key in data and isinstance(data[key], list):
                return data[key]
        except json.JSONDecodeError:
            continue

    # Try inline JSON object
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            if key in data and isinstance(data[key], list):
                return data[key]
    except json.JSONDecodeError:
        pass

    return []


async def run_autogen_negotiation(
    menu_plan: MenuPlan,
    cost_report: CostReport,
    event_spec: EventSpecification,
    max_rounds: int = 3,
) -> tuple[list[str], list[str], int]:
    """Run a RoundRobinGroupChat negotiation between Accountant and Head Chef.

    On success: returns (updated_menu_items, updated_flagged_items, rounds_used).
    On failure: raises exception → engine.py caller falls back to manual loop.
    """
    model_client = AzureOpenAIChatCompletionClient(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-12-01-preview",
        model="gpt-4o-2024-11-20",
    )

    budget = event_spec.budget_php or 0
    total_cost = cost_report.total_cost_php
    over_by = max(0.0, total_cost - budget)
    flagged = cost_report.flagged_items or []

    menu_summary = "\n".join(
        f"- {item.name}: ₱{getattr(item, 'cost_php', 'unknown')}"
        for item in (menu_plan.menu_items or [])
    )

    # ── System prompts ──────────────────────────────────────────────────────
    accountant_system = f"""You are the Accountant agent in a multi-agent catering system.

Current situation:
- Budget: ₱{budget:,.0f}
- Total cost: ₱{total_cost:,.0f}
- Over budget by: ₱{over_by:,.0f}
- Currently flagged dishes: {', '.join(flagged) or 'none yet'}

Menu items:
{menu_summary}

Dietary restrictions to enforce: {', '.join(event_spec.dietary_restrictions or [])}
Allergies (hard constraint): {', '.join(event_spec.allergies or [])}

Your job: Identify which dish(es) are driving the cost overrun and flag them
for the Head Chef to reformulate. Be specific — name the dish and explain why.
Prefer reformulation over removal. If the Head Chef proposes a cheaper
alternative, evaluate whether it brings the plan within budget.

Always respond with a JSON block containing:
{{"flagged_dishes": ["dish name"], "reasoning": "brief explanation"}}"""

    chef_system = f"""You are the Head Chef agent in a multi-agent catering system.

Current menu:
{menu_summary}

Budget: ₱{budget:,.0f} | Current cost: ₱{total_cost:,.0f}

Dietary restrictions: {', '.join(event_spec.dietary_restrictions or [])}
Allergies (HARD CONSTRAINT — never violate): {', '.join(event_spec.allergies or [])}

The Accountant will flag expensive dishes. Your job: propose cheaper alternatives
that maintain quality and satisfy all dietary restrictions. Use down-tiering
(e.g., beef → chicken), portion adjustment, or service style changes.

Always respond with a JSON block containing:
{{"reformulated_dishes": ["new dish name 1", "new dish name 2"], "rationale": "brief explanation"}}

If the menu is already as lean as possible, say so and set reformulated_dishes to []."""

    accountant_agent = AssistantAgent(
        name="Accountant",
        model_client=model_client,
        system_message=accountant_system,
        description="Reviews menu costs and flags over-budget dishes for reformulation.",
    )

    chef_agent = AssistantAgent(
        name="HeadChef",
        model_client=model_client,
        system_message=chef_system,
        description="Proposes cheaper dish alternatives when flagged by the Accountant.",
    )

    termination = MaxMessageTermination(max_messages=max_rounds * 2)
    team = RoundRobinGroupChat(
        participants=[accountant_agent, chef_agent],
        termination_condition=termination,
    )

    initial_message = (
        f"Budget negotiation required. Total cost ₱{total_cost:,.0f} exceeds "
        f"budget ₱{budget:,.0f} by ₱{over_by:,.0f}. "
        f"Accountant: please identify which dishes to flag for reformulation."
    )

    logger.info(
        "AutoGen negotiation starting — budget ₱%.0f, cost ₱%.0f, over ₱%.0f",
        budget, total_cost, over_by,
    )

    result = await team.run(task=initial_message)

    # ── Parse conversation output ───────────────────────────────────────────
    final_flagged: list[str] = list(flagged)  # start from current flagged
    final_reformulated: list[str] = []
    rounds_used = 0

    for msg in result.messages:
        # Count each Accountant message as one round
        if hasattr(msg, "source") and msg.source == "Accountant":
            rounds_used += 1
            extracted = _extract_json_block(msg.content, "flagged_dishes")
            if extracted:
                final_flagged = extracted

        if hasattr(msg, "source") and msg.source == "HeadChef":
            extracted = _extract_json_block(msg.content, "reformulated_dishes")
            if extracted:
                final_reformulated = extracted

    logger.info(
        "AutoGen negotiation complete — %d rounds, flagged=%s, reformulated=%s",
        rounds_used, final_flagged, final_reformulated,
    )

    return final_reformulated, final_flagged, rounds_used
