"""Tests for get_property_details tool in src/tools/properties/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.properties.tools import get_property_details
from src.tools.properties.schemas import GetPropertyDetailsSchema


@pytest.mark.asyncio
async def test_get_property_details_not_found():
    payload = GetPropertyDetailsSchema(property_id="prop_none")
    with patch("src.tools.properties.tools.db.get_property_full", new=AsyncMock(return_value=None)):
        res = await get_property_details(payload)
        assert "error" in res


@pytest.mark.asyncio
async def test_get_property_details_returns_full_profile():
    payload = GetPropertyDetailsSchema(property_id="prop_1")
    fake_full = {
        "id": "prop_1",
        "title": "Kitengela Royal Finesse House",
        "description": "Five bedroom house for sale",
        "property_type": "house",
        "property_subtype": "bungalow",
        "listing_type": "sale",
        "price_period": "one_time",
        "price": 17000000,
        "currency": "KES",
        "bedrooms": 5,
        "bathrooms": 4,
        "square_meters": 259,
        "lot_size_sqm": 400,
        "location": "Kitengela",
        "address": "12 Parliament Rd",
        "town": "Kitengela",
        "city": "Nairobi",
        "county": "Kajiado",
        "country": "Kenya",
        "amenities": ["garden", "security", "parking"],
        "furnished": False,
        "images": [
            {"id": "img1", "url": "https://example.com/1.jpg", "sort_order": 0, "is_featured": True},
            {"id": "img2", "url": "https://example.com/2.jpg", "sort_order": 1, "is_featured": False},
        ],
        "agent_id": "agent-1",
        "agent": {"id": "agent-1", "first_name": "Faith", "last_name": "Wanjiku",
                  "phone": "+254 712 345 678", "email": "faith@realestate.co.ke",
                  "agency_name": "Realtors Round Tables"},
    }
    allowed = {
        "id", "title", "description", "property_type", "property_subtype",
        "listing_type", "price_period", "price", "currency", "price_per_sqm",
        "bedrooms", "bathrooms", "square_meters", "lot_size_sqm", "plot_dimensions",
        "land_size_raw", "year_built", "floor_number", "total_floors",
        "location", "address", "town", "city", "county", "country",
        "latitude", "longitude", "amenities", "furnished", "images", "featured_image",
        "video_url", "agent_id", "listing_agent", "customer_service_executive",
    }
    with patch("src.tools.properties.tools.db.get_property_full", new=AsyncMock(return_value=fake_full)):
        res = await get_property_details(payload)
        assert res["status"] == "success"
        prop = res["property"]
        # The output must be confined to the new model's vocabulary.
        assert set(prop.keys()).issubset(allowed), set(prop.keys()) - allowed
        assert prop["property_subtype"] == "bungalow"
        assert prop["price_period"] == "one_time"
        assert prop["featured_image"] == "https://example.com/1.jpg"
        assert prop["listing_agent"]["name"] == "Faith Wanjiku"
        assert prop["listing_agent"]["phone"] == "+254 712 345 678"
        assert prop["listing_agent"]["email"] == "faith@realestate.co.ke"
        assert prop["customer_service_executive"]["name"] == "Simon"
