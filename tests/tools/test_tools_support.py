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
        "id": "prop_456",
        "title": "Luxury Apartment",
        "agent_id": "agent-1",
    }
    fake_agent = {
        "id": "agent-1",
        "first_name": "James",
        "last_name": "Maina",
        "phone": "0711223344",
        "email": "james@example.com",
        "agency_name": "Realtors Round Tables",
    }
    with patch("src.tools.support.db.get_property_by_id", new=AsyncMock(return_value=fake_property)), \
         patch("src.tools.support.db.get_agent", new=AsyncMock(return_value=fake_agent)):
        result = await get_support_contact(payload)
        assert "listing_agent" in result
        assert result["listing_agent"]["name"] == "James Maina"
        assert result["listing_agent"]["phone"] == "0711223344"
        assert result["listing_agent"]["email"] == "james@example.com"
