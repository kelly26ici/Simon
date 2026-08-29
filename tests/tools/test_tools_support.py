"""Tests for get_support_contact tool in src/tools/support.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.support import get_support_contact, ContactSupportSchema


@pytest.mark.asyncio
async def test_get_support_contact_general():
    payload = ContactSupportSchema()
    result = await get_support_contact(payload)
    assert result["status"] == "success"
    assert result["customer_service_executive"]["name"] == "Simon"
    assert result["customer_service_executive"]["phone"] == "0701454854"
    assert "https://wa.me/254701454854" in result["customer_service_executive"]["whatsapp_link"]


@pytest.mark.asyncio
async def test_get_support_contact_with_property():
    payload = ContactSupportSchema(property_id="prop_456")
    fake_property = {
        "title": "Luxury Apartment",
        "agent_name": "James Maina",
        "agent_phone": "0711223344",
        "agent_email": "james@example.com",
    }
    with patch("src.tools.support.db.get_property_by_id", new=AsyncMock(return_value=fake_property)):
        result = await get_support_contact(payload)
        assert "listing_agent" in result
        assert result["listing_agent"]["agent_name"] == "James Maina"
