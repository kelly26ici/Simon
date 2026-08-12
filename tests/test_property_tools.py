"""Unit tests for property tools (search_properties, compare_properties).

These tests mock the DatabaseClient so they do not depend on a live Supabase
instance.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.tools.properties.tools import compare_properties, search_properties
from src.tools.properties.schemas import (
    ComparePropertiesSchema,
    SearchPropertiesSchema,
)


@pytest.fixture
def db_stub():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch, db_stub):
    import src.tools.properties.tools as tools

    monkeypatch.setattr(tools, "db", db_stub)


@pytest.mark.asyncio
async def test_search_properties_returns_paginated_results(db_stub):
    db_stub.search_properties_advanced.return_value = [
        {
            "id": "1",
            "title": "Apt A",
            "price": 10_000_000,
            "square_meters": 120,
            "location": "Kilimani",
        }
    ]

    payload = SearchPropertiesSchema(
        property_type=None,
        listing_type=None,
        location=None,
        city=None,
        bedrooms=None,
        bathrooms=None,
        furnished=None,
        pet_friendly=None,
        gated_community=None,
        min_price=None,
        max_price=None,
        min_bedrooms=None,
        min_sqm=None,
        max_sqm=None,
        amenities=None,
        sort_by="price",
        sort_order="asc",
        limit=5,
        offset=0,
    )

    result = await search_properties(payload)
    assert result["total"] == 1
    assert result["results"][0]["title"] == "Apt A"


@pytest.mark.asyncio
async def test_compare_properties_computes_analysis(db_stub):
    db_stub.get_property_by_id.side_effect = lambda pid: {
        "1": {
            "id": "1",
            "title": "Apt A",
            "price": 10_000_000,
            "square_meters": 100,
            "bedrooms": 2,
            "bathrooms": 1,
            "location": "Kilimani",
            "amenities": ["pool", "parking"],
            "has_garden": False,
            "gated_community": True,
            "pet_friendly": False,
        },
        "2": {
            "id": "2",
            "title": "Apt B",
            "price": 12_000_000,
            "square_meters": 120,
            "bedrooms": 3,
            "bathrooms": 2,
            "location": "Westlands",
            "amenities": ["pool", "gym"],
            "has_garden": True,
            "gated_community": True,
            "pet_friendly": True,
        },
    }[pid]

    payload = ComparePropertiesSchema(property_ids=["1", "2"])

    result = await compare_properties(payload)

    assert result["compared"] == 2
    assert result["analysis"]["best_value"]["title"] == "Apt A"
    assert result["analysis"]["most_spacious"]["title"] == "Apt B"
