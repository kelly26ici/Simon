"""Tests for property schemas in src/tools/properties/schemas.py."""

from src.tools.properties.schemas import (
    PropertyType,
    ListingType,
    SearchPropertiesSchema,
    SemanticSearchSchema,
    GetPropertyDetailsSchema,
    ComparePropertiesSchema,
    CreatePropertySchema,
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


def test_create_property_schema_defaults():
    s = CreatePropertySchema(
        title="Test Villa",
        description="A beautiful villa for testing purposes.",
        property_type=PropertyType.villa,
        listing_type=ListingType.sale,
        price=20000000,
        location="Karen",
    )
    assert s.title == "Test Villa"
    assert s.property_type == PropertyType.villa
    assert s.listing_type == ListingType.sale
    assert s.price == 20000000
    assert s.city == "Nairobi"
    assert s.furnished is False
    assert s.bedrooms is None


def test_create_property_schema_rejects_negative_price():
    import pytest
    with pytest.raises(Exception):
        CreatePropertySchema(
            title="Bad Villa",
            description="A villa with a bad price.",
            property_type=PropertyType.villa,
            listing_type=ListingType.sale,
            price=-100,
            location="Karen",
        )
