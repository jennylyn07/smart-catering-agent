from __future__ import annotations

import asyncio
from uuid import uuid4

from agents.head_chef import run_head_chef
from utils.json_schema import EventSpecification


async def _main() -> None:
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


if __name__ == "__main__":
    asyncio.run(_main())
