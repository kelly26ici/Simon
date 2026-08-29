"""Tests for get_property_details tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import get_property_details
from src.tools.properties.schemas import GetPropertyDetailsSchema


@pytest.mark.asyncio
async def test_get_property_details_not_found():
    payload = GetPropertyDetailsSchema(property_id="prop_none")
    with patch("src.tools.properties.tools.db.get_property_by_id", new=AsyncMock(return_value=None)):
        res = await get_property_details(payload)
        assert "error" in res
