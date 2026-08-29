"""
tests/test_database_live.py

Live integration tests for Supabase PostgreSQL database operations in Simon.
Tests property searches, advanced filtering, customer profile persistence,
and scheduled viewings against the live Supabase instance.
"""

import pytest
import uuid
from datetime import datetime, timezone

from src.services.db import db


@pytest.mark.asyncio
async def test_supabase_client_connected():
    """Verify live Supabase client connection and schema availability."""
    assert db.client is not None, "Supabase client must be initialized"
    props = await db.get_all_properties(limit=5)
    assert isinstance(props, list)
    assert len(props) > 0, "Supabase properties table should contain seeded listings"


@pytest.mark.asyncio
async def test_search_properties_kangundo_road():
    """Verify search returns Kangundo Road corridor listings (Joska, Malaa, Kamulu, etc.)."""
    results = await db.search_properties_advanced(location="Kangundo", limit=10)
    assert len(results) > 0, "Should find properties matching 'Kangundo'"
    for p in results:
        assert "kangundo" in p["location"].lower() or "joska" in p["location"].lower() or "malaa" in p["location"].lower() or "kamulu" in p["location"].lower()
        assert p["price"] > 0
        assert p["currency"] == "KES"


@pytest.mark.asyncio
async def test_search_properties_nairobi_prime():
    """Verify search returns Nairobi prime listings (Westlands, Kilimani, Karen)."""
    results = await db.search_properties_advanced(location="Kilimani", limit=10)
    assert len(results) > 0, "Should find properties matching 'Kilimani'"
    for p in results:
        assert "kilimani" in p["location"].lower()
        assert p["price"] > 0


@pytest.mark.asyncio
async def test_search_properties_by_type_and_price_range():
    """Verify filtering by property type and price ranges."""
    # Test land under 3 million
    land_results = await db.search_properties_advanced(
        property_type="land",
        max_price=3_000_000,
        limit=10,
        sort_by="price",
        sort_order="asc",
    )
    assert len(land_results) > 0, "Should find land parcels under 3M KES"
    for p in land_results:
        assert p["property_type"] == "land"
        assert float(p["price"]) <= 3_000_000

    # Test apartments with at least 2 bedrooms
    apt_results = await db.search_properties_advanced(
        property_type="apartment",
        min_bedrooms=2,
        limit=10,
    )
    assert len(apt_results) > 0, "Should find 2+ bedroom apartments"
    for p in apt_results:
        assert p["property_type"] == "apartment"
        assert p["bedrooms"] >= 2


@pytest.mark.asyncio
async def test_customer_profile_persistence():
    """Verify customer profile creation, metadata updates, and fact retrieval."""
    test_phone = f"254799{uuid.uuid4().hex[:6]}"
    
    # 1. Initial upsert
    res1 = await db.upsert_customer_profile(
        test_phone,
        {
            "preferred_name": "Amina Mohamed",
            "budget_range": "KES 10M - 20M",
            "preferred_area": "Malaa & Joska",
            "preferred_bedrooms": 3,
        }
    )
    assert res1 is not None

    # 2. Retrieve profile
    profile = await db.get_customer_profile(test_phone)
    assert profile is not None
    assert profile["preferred_name"] == "Amina Mohamed"
    assert profile["budget_range"] == "KES 10M - 20M"
    assert profile["preferred_area"] == "Malaa & Joska"

    # 3. Dynamic fact update (into JSONB metadata)
    await db.upsert_customer_profile(
        test_phone,
        {
            "mortgage_preapproved": True,
            "target_move_in": "December 2026",
        }
    )
    updated = await db.get_customer_profile(test_phone)
    assert updated["preferred_name"] == "Amina Mohamed"
    assert updated.get("metadata", {}).get("mortgage_preapproved") is True
    assert updated.get("metadata", {}).get("target_move_in") == "December 2026"


@pytest.mark.asyncio
async def test_scheduled_viewings_crud():
    """Verify booking, querying, and cancelling a property viewing."""
    test_phone = f"254788{uuid.uuid4().hex[:6]}"
    
    # Get any valid property ID
    props = await db.get_all_properties(limit=1)
    assert len(props) > 0
    prop_id = str(props[0]["id"])

    # 1. Create viewing
    viewing = await db.create_scheduled_viewing(
        property_id=prop_id,
        customer_phone=test_phone,
        customer_name="Peter Omondi",
        viewing_date="2026-09-01T10:00:00Z",
        duration_minutes=45,
        notes="First-time buyer interested in title deed verification",
    )
    assert viewing is not None
    viewing_id = str(viewing["id"])
    assert viewing["status"] == "confirmed"

    # 2. Fetch viewing list
    viewings = await db.get_customer_viewings(test_phone)
    assert len(viewings) >= 1
    assert any(str(v["id"]) == viewing_id for v in viewings)

    # 3. Cancel viewing
    cancelled = await db.cancel_scheduled_viewing(viewing_id, test_phone)
    assert cancelled is True

    # 4. Verify updated status
    updated_viewings = await db.get_customer_viewings(test_phone)
    target = next((v for v in updated_viewings if str(v["id"]) == viewing_id), None)
    assert target is not None
    assert target["status"] == "cancelled"
