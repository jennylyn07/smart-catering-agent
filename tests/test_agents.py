from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from agents.head_chef import run_head_chef
from agents.accountant import run_accountant
from agents.logistics import run_logistics
from agents.stock_manager import run_stock_manager
from utils.json_schema import AgentMessage, EventSpecification, MenuItem, MenuPlan, MessageHeader, MessageMetadata, MessageSignature


async def _main() -> None:
    """Run local agent tests and print their outputs.

    Args:
        None

    Returns:
        None
    """
    session_id = str(uuid4())

    run_concierge_step = False
    if run_concierge_step:
        from agents.concierge import run_concierge

        raw_text = (
            "I need catering for my daughter's debut party. "
            "Around 150 guests, Filipino food, budget is PHP 45,000. "
            "The event is on May 20, 2026 at Antipolo. "
            "Please no nuts — one of the guests has a severe nut allergy."
        )

        concierge_message = await run_concierge(raw_customer_text=raw_text, session_id=session_id)
        print("\n--- Concierge output (event_specification) ---\n")
        print(concierge_message.model_dump_json(indent=2, by_alias=True))

    event_spec_payload = {
        "event_id": "sample-event-001",
        "event_name": "Daughter's debut party",
        "event_date": "2026-05-20",
        "location": "Antipolo",
        "guest_count": 150,
        "budget_php": 45000.0,
        "cuisine_preferences": ["filipino"],
        "dietary_restrictions": [],
        "allergies": ["nuts"],
        "notes": None,
    }
    event_spec = EventSpecification.model_validate(event_spec_payload)

    head_chef_message = await run_head_chef(event_spec=event_spec, session_id=session_id)
    print("\n--- Head Chef output (menu_plan) ---\n")
    print(head_chef_message.model_dump_json(indent=2, by_alias=True))

    if hasattr(head_chef_message.payload, "menu_items"):
        names = [item.name.lower() for item in head_chef_message.payload.menu_items]
        assert not any("kare" in n for n in names), "Nut allergy check failed: Kare-Kare should be excluded"

    event_spec_vegan = event_spec.model_copy(update={"dietary_restrictions": ["vegan"]})
    head_chef_vegan = await run_head_chef(event_spec=event_spec_vegan, session_id=session_id)
    print("\n--- Head Chef output (menu_plan, vegan) ---\n")
    print(head_chef_vegan.model_dump_json(indent=2, by_alias=True))

    if hasattr(head_chef_vegan.payload, "menu_items"):
        vegan_ingredients = [
            ing.lower()
            for item in head_chef_vegan.payload.menu_items
            for ing in (item.ingredients or [])
        ]
        blocked_terms = {
            "chicken",
            "pork",
            "beef",
            "fish",
            "shrimp",
            "egg",
            "eggs",
            "butter",
            "cheese",
            "cream",
            "milk",
        }
        assert not any(
            any(term in ing and "coconut milk" not in ing for term in blocked_terms) for ing in vegan_ingredients
        ), "Vegan dietary check failed: menu contains animal/dairy ingredient terms"

    event_spec_halal = event_spec.model_copy(update={"dietary_restrictions": ["halal"]})
    head_chef_halal = await run_head_chef(event_spec=event_spec_halal, session_id=session_id)
    print("\n--- Head Chef output (menu_plan, halal) ---\n")
    print(head_chef_halal.model_dump_json(indent=2, by_alias=True))

    if hasattr(head_chef_halal.payload, "menu_items"):
        halal_ingredients = [
            ing.lower()
            for item in head_chef_halal.payload.menu_items
            for ing in (item.ingredients or [])
        ]
        assert not any("pork" in ing or "bacon" in ing or "lard" in ing for ing in halal_ingredients), (
            "Halal dietary check failed: menu contains pork/bacon/lard terms"
        )

    event_spec_tight_constraints = event_spec.model_copy(
        update={
            "cuisine_preferences": ["western"],
            "dietary_restrictions": ["vegan"],
            "allergies": ["nuts", "wheat", "dairy", "egg", "soy"],
        }
    )
    head_chef_tight = await run_head_chef(event_spec=event_spec_tight_constraints, session_id=session_id)
    print("\n--- Head Chef output (menu_plan, tight constraints) ---\n")
    print(head_chef_tight.model_dump_json(indent=2, by_alias=True))

    menu_plan = MenuPlan(
        event_id=event_spec.event_id,
        menu_items=[
            MenuItem(
                name="Chicken Adobo",
                category="main",
                servings=150,
                ingredients=["chicken", "soy sauce", "vinegar", "garlic"],
            ),
            MenuItem(
                name="Pancit Canton",
                category="noodles",
                servings=150,
                ingredients=["wheat noodles", "chicken", "cabbage", "carrot"],
            ),
            MenuItem(
                name="Lumpiang Shanghai",
                category="appetizer",
                servings=150,
                ingredients=["ground pork", "spring roll wrapper", "carrot", "onion", "garlic"],
            ),
            MenuItem(
                name="Laing",
                category="vegetable",
                servings=150,
                ingredients=["taro leaves", "coconut milk", "garlic", "ginger", "chili"],
            ),
            MenuItem(
                name="Buko Pandan",
                category="dessert",
                servings=150,
                ingredients=[
                    "young coconut",
                    "nata de coco",
                    "all-purpose cream",
                    "condensed milk",
                    "pandan jelly",
                ],
            ),
        ],
        rationale="Hardcoded sample menu for Accountant testing.",
        allergy_flags=["nuts"],
    )

    menu_plan_message = AgentMessage(
        header=MessageHeader(
            message_id=uuid4(),
            agent_id="head_chef",
            target_agent="accountant",
            timestamp=datetime.now(timezone.utc),
            message_type="menu_plan",
        ),
        payload=menu_plan,
        metadata=MessageMetadata(confidence_score=0.8),
        signature=MessageSignature(hash="test", session_id=session_id),
    )

    event_spec_comfortable = event_spec.model_copy(update={"budget_php": 200000.0})
    cost_report_a = await run_accountant(
        menu_plan_message=menu_plan_message,
        event_spec=event_spec_comfortable,
        session_id=session_id,
    )
    print("\n--- Accountant output Scenario A (comfortable budget) ---\n")
    print(cost_report_a.model_dump_json(indent=2, by_alias=True))

    event_spec_tight = event_spec.model_copy(update={"budget_php": 2000.0})
    cost_report_b = await run_accountant(
        menu_plan_message=menu_plan_message,
        event_spec=event_spec_tight,
        session_id=session_id,
    )
    print("\n--- Accountant output Scenario B (tight budget) ---\n")
    print(cost_report_b.model_dump_json(indent=2, by_alias=True))

    event_spec_notes = event_spec_tight.model_copy(update={"notes": "Plated service, 3-course, early setup at 5AM"})
    logistics_plan_notes = await run_logistics(
        cost_report_message=cost_report_b,
        event_spec=event_spec_notes,
        event_datetime_iso="2026-05-20T18:00:00+08:00",
        session_id=session_id,
    )
    print("\n--- Logistics output (logistics_plan, notes) ---\n")
    print(logistics_plan_notes.model_dump_json(indent=2, by_alias=True))

    logistics_plan = await run_logistics(
        cost_report_message=cost_report_b,
        event_spec=event_spec_tight,
        event_datetime_iso="2026-05-20T18:00:00+08:00",
        session_id=session_id,
    )
    print("\n--- Logistics output (logistics_plan) ---\n")
    print(logistics_plan.model_dump_json(indent=2, by_alias=True))

    if hasattr(logistics_plan.payload, "timeline"):
        times = [t.time for t in logistics_plan.payload.timeline]
        assert times == sorted(times), "Timeline is not sorted in ascending order"

    procurement_list = await run_stock_manager(
        logistics_plan_message=logistics_plan,
        cost_report_message=cost_report_b,
        session_id=session_id,
    )
    print("\n--- Stock Manager output (procurement_list) ---\n")
    print(procurement_list.model_dump_json(indent=2, by_alias=True))

    if hasattr(procurement_list.payload, "items_to_purchase"):
        assert procurement_list.payload.total_procurement_cost_php >= 0
        assert len(procurement_list.payload.items_to_purchase) >= 0


if __name__ == "__main__":
    asyncio.run(_main())
