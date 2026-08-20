"""
tests/test_qdrant_semantic.py

Integration tests for Qdrant vector database and Cloudflare AI semantic search.
Tests natural language retrieval of Kenyan real estate listings.
"""

import pytest
from src.tools.properties import semantic_search
from src.tools.qdrant import client as qdrant_client, make_collection, PROPERTIES_COLLECTION


@pytest.mark.asyncio
async def test_qdrant_collection_health():
    """Verify Qdrant collection is created and reachable."""
    collection_info = await qdrant_client.get_collection("properties")
    assert collection_info is not None
    assert collection_info.status.value in ("green", "yellow", "ok")


@pytest.mark.asyncio
async def test_semantic_search_kangundo_plots():
    """Verify natural language search finds Kangundo Road plots/land."""
    results = await semantic_search(
        query="50x100 plot in Joska or Malaa with ready title deed",
        limit=5,
    )
    assert len(results) > 0, "Semantic search should return matches for Kangundo plot queries"
    top = results[0]
    assert "id" in top
    assert "score" in top
    assert top["score"] > 0
    assert any("kangundo" in str(r.get("location", "")).lower() or "joska" in str(r.get("location", "")).lower() or "malaa" in str(r.get("location", "")).lower() or r.get("property_type") == "land" for r in results)


@pytest.mark.asyncio
async def test_semantic_search_nairobi_luxury():
    """Verify natural language search finds luxury apartments with amenities."""
    results = await semantic_search(
        query="modern executive 2-bedroom apartment with swimming pool and gym in Kilimani or Westlands",
        limit=5,
    )
    assert len(results) > 0, "Semantic search should return luxury apartment matches"
    for r in results:
        assert r["property_type"] in ("apartment", "penthouse", "studio")
        assert "price" in r


@pytest.mark.asyncio
async def test_semantic_search_family_bungalows():
    """Verify natural language search finds gated family bungalows."""
    results = await semantic_search(
        query="spacious 3 bedroom family bungalow in a secure gated court with garden",
        limit=5,
    )
    assert len(results) > 0
    assert any(r.get("property_type") in ("house", "townhouse", "villa") for r in results)


@pytest.mark.asyncio
async def test_semantic_search_with_metadata_filters():
    """Verify semantic search respects price caps and property type filters."""
    results = await semantic_search(
        query="residential property with good road access",
        property_type="land",
        price_max=2_500_000,
        limit=5,
    )
    assert len(results) > 0
    for r in results:
        assert r["property_type"] == "land"
        assert float(r["price"]) <= 2_500_000
