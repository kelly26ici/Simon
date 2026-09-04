"""Tests for compare_properties tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import compare_properties
from src.tools.properties.schemas import ComparePropertiesSchema


@pytest.mark.asyncio
async def test_compare_properties_success():
    payload = ComparePropertiesSchema(property_ids=["p1", "p2"])
    p1 = {
        "id": "p1", "title": "House 1", "price": 10000000, "bedrooms": 3,
        "bathrooms": 2, "square_meters": 150,
        "amenities": ["garden", "gated", "gym"],
        "property_type": "house", "listing_type": "sale", "status": "available",
    }
    p2 = {
        "id": "p2", "title": "House 2", "price": 20000000, "bedrooms": 4,
        "bathrooms": 3, "square_meters": 200,
        "amenities": ["pool", "garden", "pet_allowed"],
        "property_type": "villa", "listing_type": "sale", "status": "available",
    }

    async def fake_get(pid):
        return p1 if pid == "p1" else p2

    with patch("src.tools.properties.tools.db.get_property_by_id", side_effect=fake_get):
        res = await compare_properties(payload)
        assert res["compared"] == 2
        assert len(res["properties"]) == 2
        # Comparison rows must stay within the new model vocabulary.
        allowed_row = {
            "id", "title", "property_type", "property_subtype", "listing_type",
            "price_period", "price", "price_per_sqm", "bedrooms", "bathrooms",
            "square_meters", "lot_size_sqm", "location", "city", "town", "country",
            "amenities", "furnished", "year_built", "description",
        }
        for row in res["properties"]:
            assert set(row.keys()).issubset(allowed_row), set(row.keys()) - allowed_row
        # p1: 10M/150sqm = 66.7k/sqm (cheapest per sqm) -> best value
        assert res["analysis"]["best_value"]["title"] == "House 1"
        # p2: 200 sqm -> most spacious
        assert res["analysis"]["most_spacious"]["title"] == "House 2"
        # common amenity (garden) present in both
        assert "garden" in res["analysis"]["common_amenities"]


@pytest.mark.asyncio
async def test_compare_properties_missing():
    payload = ComparePropertiesSchema(property_ids=["p1", "pX"])
    p1 = {"id": "p1", "title": "House 1", "price": 10000000, "bedrooms": 3,
          "bathrooms": 2, "square_meters": 150, "amenities": ["garden"],
          "property_type": "house", "listing_type": "sale", "status": "available"}

    async def fake_get(pid):
        return p1 if pid == "p1" else None

    with patch("src.tools.properties.tools.db.get_property_by_id", side_effect=fake_get):
        res = await compare_properties(payload)
        assert "error" in res
