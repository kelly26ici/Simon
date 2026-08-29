"""Tests for get_customer_preferences tool in src/tools/memory/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.memory.tools import get_customer_preferences
from src.tools.memory.schemas import GetCustomerPreferencesSchema


@pytest.mark.asyncio
async def test_get_customer_preferences_found():
    payload = GetCustomerPreferencesSchema(phone_number="254700000000")
    fake_profile = {"preferred_name": "Brian", "budget_range": "20M KES"}

    with patch("src.tools.memory.tools.db.get_customer_profile", new=AsyncMock(return_value=fake_profile)):
        res = await get_customer_preferences(payload)
        assert res["status"] == "success"
        assert res["profile"]["preferred_name"] == "Brian"


@pytest.mark.asyncio
async def test_get_customer_preferences_not_found():
    payload = GetCustomerPreferencesSchema(phone_number="254700000000")

    with patch("src.tools.memory.tools.db.get_customer_profile", new=AsyncMock(return_value=None)):
        res = await get_customer_preferences(payload)
        assert res["status"] == "not_found"
