"""Tests for seed property data integrity in src/data/seed_properties.py."""

from src.data.seed_properties import PROPERTIES_SEED_DATA


def test_seed_properties_not_empty():
    assert len(PROPERTIES_SEED_DATA) > 0


def test_seed_properties_required_fields():
    required_keys = {"title", "description", "property_type", "listing_type", "price", "location", "city"}
    for idx, prop in enumerate(PROPERTIES_SEED_DATA):
        missing = required_keys - set(prop.keys())
        assert not missing, f"Property at index {idx} missing required fields: {missing}"


def test_seed_properties_price_positive():
    for prop in PROPERTIES_SEED_DATA:
        assert prop["price"] > 0, f"Property {prop.get('title')} has invalid price: {prop['price']}"


def test_seed_properties_valid_listing_types():
    valid_listing_types = {"sale", "rent"}
    for prop in PROPERTIES_SEED_DATA:
        assert prop["listing_type"] in valid_listing_types
