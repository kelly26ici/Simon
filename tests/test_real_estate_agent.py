# tests/test_real_estate_agent.py
"""
Tests for Samantha Real Estate Agent Tools and Workflows.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import src.tools  # noqa: F401
from src.tools.registry import registry
from src.tools.schedule_meeting import (
    ScheduleViewingSchema,
    GetMyViewingsSchema,
    CancelViewingSchema,
    schedule_property_viewing,
    get_my_scheduled_viewings,
    cancel_property_viewing,
)
from src.tools.finance import MortgageCalculatorSchema, calculate_mortgage
from src.tools.properties.schemas import GetPropertyDetailsSchema
from src.tools.properties.tools import get_property_details
from src.tools.memory.schemas import GetCustomerPreferencesSchema
from src.tools.memory.tools import get_customer_preferences
from src.messages.chats.text_handler import _build_customer_context_string
from src.services.llm import _build_openai_messages


from src.tools.support import ContactSupportSchema, get_support_contact


@pytest.mark.asyncio
async def test_tool_registry_contains_real_estate_tools():
    names = registry.get_registered_tool_names()
    assert "search_properties" in names
    assert "semantic_search_properties" in names
    assert "get_property_details" in names
    assert "compare_properties" in names
    assert "schedule_property_viewing" in names
    assert "get_my_scheduled_viewings" in names
    assert "cancel_property_viewing" in names
    assert "calculate_mortgage" in names
    assert "save_customer_fact" in names
    assert "get_customer_preferences" in names
    assert "get_support_contact" in names


@pytest.mark.asyncio
async def test_get_support_contact():
    # Test general executive contact
    res = await get_support_contact(ContactSupportSchema(inquiry_topic="general inquiry"))
    assert res["status"] == "success"
    assert res["company"] == "Realtors Round Tables"
    assert res["website"] == "https://realtorsroundtables.co.ke"
    assert res["customer_service_executive"]["name"] == "Simon"
    assert res["customer_service_executive"]["phone"] == "0701454854"
    assert "https://wa.me/254701454854" in res["customer_service_executive"]["whatsapp_link"]

    # Test with property id
    with patch("src.tools.support.db") as mock_db:
        mock_db.get_property_by_id = AsyncMock(return_value={
            "id": "prop-999",
            "title": "Riverside Green Duplex",
            "agent_name": "David Mwangi",
            "agent_phone": "0701234567",
            "agent_email": "david@realtorsroundtables.co.ke",
        })
        prop_res = await get_support_contact(ContactSupportSchema(property_id="prop-999"))
        assert prop_res["status"] == "success"
        assert "listing_agent" in prop_res
        assert prop_res["listing_agent"]["agent_name"] == "David Mwangi"
        assert "https://wa.me/254701234567" in prop_res["listing_agent"]["whatsapp_link"]


@pytest.mark.asyncio
async def test_calculate_mortgage():
    payload = MortgageCalculatorSchema(
        property_price=20000000.0,
        down_payment_percentage=20.0,
        interest_rate_annual=13.5,
        loan_term_years=20,
    )
    result = await calculate_mortgage(payload)
    assert result["currency"] == "KES"
    assert result["down_payment"]["amount"] == 4000000.0
    assert result["loan_details"]["principal_loan_amount"] == 16000000.0
    assert result["loan_details"]["estimated_monthly_payment"] > 0
    assert result["estimated_acquisition_costs"]["stamp_duty_4pct"] == 800000.0
    assert result["affordability"]["recommended_min_gross_monthly_income"] > 0


@pytest.mark.asyncio
async def test_schedule_and_get_viewing():
    with patch("src.tools.schedule_meeting.db") as mock_db:
        mock_db.get_property_by_id = AsyncMock(return_value={
            "id": "prop-123",
            "title": "Rhapta Heights Luxury Penthouse",
            "location": "Westlands",
            "agent_name": "Kevin Mutua",
            "agent_phone": "+254 722 890 123",
        })
        mock_db.create_scheduled_viewing = AsyncMock(return_value={
            "id": "viewing-uuid-1",
            "status": "confirmed",
        })
        mock_db.upsert_customer_profile = AsyncMock(return_value={})

        payload = ScheduleViewingSchema(
            property_id="prop-123",
            customer_phone="254706716616",
            customer_name="Rex Kelly",
            preferred_date_time="2026-08-22 14:00",
            duration_minutes=45,
            notes="Client is looking for immediate occupancy",
        )
        result = await schedule_property_viewing(payload)
        assert result["status"] == "confirmed"
        assert result["booking_id"] == "viewing-uuid-1"
        assert result["assigned_agent"]["name"] == "Kevin Mutua"
        assert result["location"] == "Westlands"

        mock_db.get_customer_viewings = AsyncMock(return_value=[
            {"id": "viewing-uuid-1", "status": "confirmed", "viewing_date": "2026-08-22 14:00"}
        ])
        get_res = await get_my_scheduled_viewings(GetMyViewingsSchema(customer_phone="254706716616"))
        assert get_res["total"] == 1
        assert len(get_res["viewings"]) == 1

        mock_db.cancel_scheduled_viewing = AsyncMock(return_value=True)
        cancel_res = await cancel_property_viewing(CancelViewingSchema(viewing_id="viewing-uuid-1", customer_phone="254706716616"))
        assert cancel_res["status"] == "success"


@pytest.mark.asyncio
async def test_get_property_details():
    with patch("src.tools.properties.tools.db") as mock_db:
        mock_db.get_property_by_id = AsyncMock(return_value={
            "id": "prop-456",
            "title": "Karen Brooks 5-Bedroom Luxury Villa",
            "description": "Spectacular 5-bedroom villa with pool",
            "price": 95000000,
            "currency": "KES",
            "bedrooms": 5,
            "bathrooms": 6,
            "location": "Karen",
            "city": "Nairobi",
            "amenities": ["swimming_pool", "garden"],
            "agent_name": "Grace Nyambura",
            "images": ["https://example.com/photo1.jpg"],
        })
        payload = GetPropertyDetailsSchema(property_id="prop-456")
        res = await get_property_details(payload)
        assert res["status"] == "success"
        assert res["property"]["title"] == "Karen Brooks 5-Bedroom Luxury Villa"
        assert res["property"]["price"] == 95000000.0
        assert res["property"]["agent_name"] == "Grace Nyambura"


@pytest.mark.asyncio
async def test_get_customer_preferences():
    with patch("src.tools.memory.tools.db") as mock_db:
        mock_db.get_customer_profile = AsyncMock(return_value={
            "whatsapp_id": "254706716616",
            "preferred_name": "Rex Kelly",
            "budget_range": "KES 20M - 40M",
            "preferred_area": "Westlands & Kilimani",
        })
        payload = GetCustomerPreferencesSchema(phone_number="254706716616")
        res = await get_customer_preferences(payload)
        assert res["status"] == "success"
        assert res["profile"]["preferred_name"] == "Rex Kelly"


@pytest.mark.asyncio
async def test_customer_context_building():
    with patch("src.messages.chats.text_handler.db") as mock_db:
        mock_db.get_customer_profile = AsyncMock(return_value={
            "whatsapp_id": "254706716616",
            "preferred_name": "Rex Kelly",
            "budget_range": "KES 20M - 40M",
            "preferred_area": "Westlands & Kilimani",
            "metadata": {"property_type": "Penthouse"},
        })
        mock_db.get_customer_viewings = AsyncMock(return_value=[
            {"id": "12345678-abcd", "viewing_date": "2026-08-22 14:00", "status": "confirmed"}
        ])

        ctx_str = await _build_customer_context_string("254706716616")
        assert "254706716616" in ctx_str
        assert "Rex Kelly" in ctx_str
        assert "KES 20M - 40M" in ctx_str
        assert "Westlands & Kilimani" in ctx_str
        assert "2026-08-22 14:00" in ctx_str

        msgs = _build_openai_messages([{"role": "user", "content": "Show me penthouses"}], customer_context=ctx_str)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert "CURRENT CONVERSATION CONTEXT" in msgs[0]["content"]
        assert "Rex Kelly" in msgs[0]["content"]
