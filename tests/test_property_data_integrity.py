"""
tests/test_property_data_integrity.py

Data validation and schema integrity tests for Kenyan real estate data.
Ensures that all listings follow strict business rules, realistic Kenyan market pricing,
and correct enum types for production agent queries.
"""

import pytest
from src.services.db import db
from src.data.ingest_properties import generate_kangundo_road_properties, resolve_location


VALID_PROPERTY_TYPES = {
    "house", "apartment", "land", "commercial",
    "townhouse", "villa", "cottage", "penthouse", "studio"
}
VALID_LISTING_TYPES = {"sale", "rent"}


@pytest.mark.asyncio
async def test_database_properties_have_valid_enums():
    """Ensure all properties in database conform to strict enum constraints."""
    properties = await db.get_all_properties(limit=500)
    assert len(properties) > 0

    for p in properties:
        p_type = p.get("property_type")
        l_type = p.get("listing_type")
        status = p.get("status")
        price = p.get("price")

        assert p_type in VALID_PROPERTY_TYPES, f"Invalid property_type '{p_type}' in property {p.get('id')}"
        assert l_type in VALID_LISTING_TYPES, f"Invalid listing_type '{l_type}' in property {p.get('id')}"
        assert status in ("available", "pending", "sold", "rented", "off_market")
        assert price is not None and float(price) > 0, f"Invalid price {price} in property {p.get('id')}"
        assert p.get("currency") == "KES"
        assert len(p.get("title", "")) > 3


def test_kangundo_generator_data_integrity():
    """Verify Kangundo Road dedicated listings meet market price rules."""
    props = generate_kangundo_road_properties()
    assert len(props) >= 150, "Kangundo generator should produce comprehensive listing set"

    for p in props:
        assert p["property_type"] in VALID_PROPERTY_TYPES
        assert p["listing_type"] in VALID_LISTING_TYPES
        assert p["price"] > 0
        assert p["currency"] == "KES"
        assert "Kangundo" in p["location"] or "Joska" in p["location"] or "Malaa" in p["location"] or "Kamulu" in p["location"]
        assert -5.0 <= p["latitude"] <= 5.0, "Latitude must be in Kenya range"
        assert 33.0 <= p["longitude"] <= 42.0, "Longitude must be in Kenya range"
        assert isinstance(p["amenities"], list) and len(p["amenities"]) > 0
        assert isinstance(p["images"], list) and len(p["images"]) > 0


def test_resolve_location_mapping():
    """Verify location normalization and county resolution for Nairobi and Kangundo corridor."""
    cases = [
        ("Joska, Kangundo Road", "Joska", "Machakos"),
        ("Malaa Center near Quickmart", "Malaa", "Machakos"),
        ("Kamulu shopping center", "Kamulu", "Nairobi"),
        ("Kilimani, Argwings Kodhek", "Kilimani", "Nairobi"),
        ("Westlands, Rhapta Road", "Rhapta Road", "Nairobi"),
        ("Karen Mbagathi", "Karen", "Nairobi"),
        ("Tala market", "Tala", "Machakos"),
    ]
    for raw, expected_loc, expected_county in cases:
        loc_name, city, county, lat, lng in resolve_location(raw)
        assert expected_loc.lower() in loc_name.lower() or expected_loc.lower() in raw.lower()
        assert county == expected_county
