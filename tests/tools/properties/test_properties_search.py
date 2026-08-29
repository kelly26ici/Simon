"""Tests for search_properties tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import search_properties
from src.tools.properties.schemas import SearchPropertiesSchema, PropertyType


@pytest.mark.asyncio
async def test_search_properties_returns_matches():
    payload = SearchPropertiesSchema(property_type=PropertyType.apartment)
    fake_props = [
        {"id": "prop_1", "title": "2BR Apartment", "price": 8500000, "property_type": "apartment"}
    ]
    with patch("src.tools.properties.tools.db.search_properties_advanced", new=AsyncMock(return_value=fake_props)):
        res = await search_properties(payload)
        assert res["total"] == 1
        assert len(res["results"]) == 1
        assert res["results"][0]["title"] == "2BR Apartment"
