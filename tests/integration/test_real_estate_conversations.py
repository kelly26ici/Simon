"""
tests/test_real_estate_conversations.py

Conversation flow and agent decision tests for Simon Real Estate Agent.
Simulates real customer conversations regarding Nairobi and Kangundo Road properties.
"""

import pytest
from src.tools.properties.schemas import SearchPropertiesSchema, SemanticSearchSchema, ComparePropertiesSchema, GetPropertyDetailsSchema
from src.tools.properties.tools import search_properties, semantic_search_properties, compare_properties, get_property_details
from src.tools.finance import MortgageCalculatorSchema, calculate_mortgage
from src.tools.schedule_meeting import ScheduleViewingSchema, schedule_property_viewing
from src.tools.memory.schemas import SaveCustomerFactSchema, GetCustomerPreferencesSchema
from src.tools.memory.tools import save_customer_fact, get_customer_preferences


@pytest.mark.asyncio
async def test_customer_asks_for_kangundo_plots():
    """Customer asks: 'Do you have 50x100 plots along Kangundo Road under 2 Million?'"""
    res = await search_properties(SearchPropertiesSchema(
        location="Kangundo",
        property_type="land",
        max_price=2_000_000.0,
        sort_by="price",
        sort_order="asc",
        limit=5,
    ))
    assert res["total"] > 0
    for p in res["results"]:
        assert p["price"] <= 2_000_000.0
        assert "kangundo" in p["location"].lower() or "joska" in p["location"].lower() or "malaa" in p["location"].lower() or "kamulu" in p["location"].lower()


@pytest.mark.asyncio
async def test_customer_asks_for_kilimani_rentals():
    """Customer asks: 'Show me 2 bedroom apartments for rent in Kilimani under 100k'"""
    res = await search_properties(SearchPropertiesSchema(
        location="Kilimani",
        property_type="apartment",
        listing_type="rent",
        bedrooms=2,
        max_price=100_000.0,
        limit=5,
    ))
    assert isinstance(res["results"], list)
    if res["results"]:
        for p in res["results"]:
            assert p["listing_type"] == "rent"
            assert p["price"] <= 100_000.0


@pytest.mark.asyncio
async def test_customer_calculates_mortgage_and_affordability():
    """Customer asks: 'What are the monthly repayments for a 12M bungalow with 10% down?'"""
    mortgage = await calculate_mortgage(MortgageCalculatorSchema(
        property_price=12_000_000.0,
        down_payment_percentage=10.0,
        interest_rate_annual=13.0,
        loan_term_years=15,
    ))
    assert mortgage["currency"] == "KES"
    assert mortgage["down_payment"]["amount"] == 1_200_000.0
    assert mortgage["loan_details"]["principal_loan_amount"] == 10_800_000.0
    assert mortgage["loan_details"]["estimated_monthly_payment"] > 0
    assert "repayment_summary" in mortgage


@pytest.mark.asyncio
async def test_customer_profile_learning_in_conversation():
    """Customer shares name and preferences during chat."""
    phone = "254711998877"

    # Samantha saves learned fact
    save_res = await save_customer_fact(SaveCustomerFactSchema(
        phone_number=phone,
        fact_key="preferred_area",
        fact_value="Joska & Malaa, Kangundo Road",
    ))
    assert save_res["status"] == "success"

    save_res2 = await save_customer_fact(SaveCustomerFactSchema(
        phone_number=phone,
        fact_key="preferred_name",
        fact_value="Wanjala Wafula",
    ))
    assert save_res2["status"] == "success"

    # Retrieve learned profile
    pref_res = await get_customer_preferences(GetCustomerPreferencesSchema(phone_number=phone))
    assert pref_res["status"] == "success"
    profile = pref_res["profile"]
    assert profile["preferred_name"] == "Wanjala Wafula"
    assert "Joska" in profile["preferred_area"]


@pytest.mark.asyncio
async def test_customer_requests_human_support():
    """Customer asks to talk to Simon or customer service executive."""
    from src.tools.support import ContactSupportSchema, get_support_contact
    contact_res = await get_support_contact(ContactSupportSchema(inquiry_topic="Speak with executive"))
    assert contact_res["status"] == "success"
    assert contact_res["customer_service_executive"]["name"] == "Simon"
    assert contact_res["customer_service_executive"]["phone"] == "0701454854"
    assert "realtorsroundtables.co.ke" in contact_res["website"]


@pytest.mark.asyncio
async def test_handle_interactive_button_reply():
    """Customer clicks a WhatsApp button to speak with Simon or view listings."""
    from unittest.mock import patch, AsyncMock
    from src.messages.interactions.interactive_handler import handle_interactive

    with patch("src.messages.interactions.interactive_handler.handle_text", new_callable=AsyncMock) as mock_handle_text:
        interactive_msg = {
            "id": "wamid.HBg12345",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {
                    "id": "btn_chat_simon",
                    "title": "Chat with Simon",
                },
            },
        }
        await handle_interactive("254701454854", interactive_msg)
        mock_handle_text.assert_awaited_once()
        args = mock_handle_text.await_args[0]
        assert args[0] == "254701454854"
        assert args[1]["text"]["body"] == "Chat with Simon"


