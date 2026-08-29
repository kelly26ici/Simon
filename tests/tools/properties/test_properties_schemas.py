"""Tests for property schemas in src/tools/properties/schemas.py."""

from src.tools.properties.schemas import (
    PropertyType,
    ListingType,
    SearchPropertiesSchema,
    SemanticSearchSchema,
    GetPropertyDetailsSchema,
    ComparePropertiesSchema,
)


def test_property_type_enum():
    assert PropertyType.house == "house"
    assert PropertyType.apartment == "apartment"
    assert PropertyType.villa == "villa"


def test_listing_type_enum():
    assert ListingType.sale == "sale"
    assert ListingType.rent == "rent"


def test_search_properties_schema_defaults():
    s = SearchPropertiesSchema()
    assert s.property_type is None
    assert s.listing_type is None
    assert s.limit == 5


def test_compare_properties_schema():
    s = ComparePropertiesSchema(property_ids=["id_1", "id_2"])
    assert len(s.property_ids) == 2
