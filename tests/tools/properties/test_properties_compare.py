"""Tests for compare_properties tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import compare_properties
from src.tools.properties.schemas import ComparePropertiesSchema


@pytest.mark.asyncio
async def test_compare_properties_success():
    payload = ComparePropertiesSchema(property_ids=["p1", "p2"])
    p1 = {"id": "p1", "title": "House 1", "price": 10000000, "bedrooms": 3, "square_meters": 150, "amenities": ["gym"], "has_garden": True, "gated_community": True, "pet_friendly": False}
    p2 = {"id": "p2", "title": "House 2", "price": 12000000, "bedrooms": 4, "square_meters": 200, "amenities": ["pool"], "has_garden": True, "gated_community": False, "pet_friendly": True}

    async def fake_get(pid):
        return p1 if pid == "p1" else p2

    with patch("src.tools.properties.tools.db.get_property_by_id", side_effect=fake_get):
        res = await compare_properties(payload)
        assert res["compared"] == 2
        assert len(res["properties"]) == 2
