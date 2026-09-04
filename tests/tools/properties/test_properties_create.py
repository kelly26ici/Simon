"""Tests for create_property tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import create_property
from src.tools.properties.schemas import CreatePropertySchema, PropertyType, ListingType


@pytest.mark.asyncio
async def test_create_property_success():
    fake_prop = {
        "id": "new-prop-uuid",
        "title": "Test Property",
        "property_type": "apartment",
        "listing_type": "sale",
        "price": 15000000,
    }

    with patch("src.tools.properties.tools.db.upsert_property", new=AsyncMock(return_value=fake_prop)), \
         patch("src.tools.properties.tools.index_property", new=AsyncMock(return_value=True)):
        payload = CreatePropertySchema(
            title="Test Property",
            description="A beautiful apartment in the heart of the city.",
            property_type=PropertyType.apartment,
            listing_type=ListingType.sale,
            price=15000000,
            location="Westlands",
        )
        res = await create_property(payload)

        assert res["status"] == "success"
        assert res["property_id"] == "new-prop-uuid"
        assert "searchable" in res["message"].lower()


@pytest.mark.asyncio
async def test_create_property_db_failure():
    with patch("src.tools.properties.tools.db.upsert_property", new=AsyncMock(return_value=None)):
        payload = CreatePropertySchema(
            title="Failed Property",
            description="This property will not be created.",
            property_type=PropertyType.house,
            listing_type=ListingType.rent,
            price=50000,
            location="Karen",
        )
        res = await create_property(payload)

        assert "error" in res
        assert "Failed to create" in res["error"]


@pytest.mark.asyncio
async def test_create_property_validation():
    # Negative price should fail validation
    with pytest.raises(Exception):
        CreatePropertySchema(
            title="Bad Property",
            description="A property with bad data",
            property_type=PropertyType.apartment,
            listing_type=ListingType.sale,
            price=-100,  # must be > 0
            location="Kilimani",
        )
