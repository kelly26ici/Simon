"""
Property embedding pipeline — embeds property descriptions and indexes them
in Qdrant for semantic search.

Flow:
1. Fetch properties from Supabase
2. Build a rich text representation for each property
3. Embed via Cloudflare Workers AI
4. Upsert into Qdrant with payload (id, price, bedrooms, location, etc.)
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointStruct, Range

from src.tools.embeddings import get_embeddings
from src.tools.qdrant import client as qdrant_client, make_collection
from src.services.db import db

PROPERTIES_COLLECTION = "properties"
VECTOR_SIZE = 1024  # Cloudflare qwen3-embedding-0.6b outputs 1024-dim vectors
BATCH_SIZE = 20  # Cloudflare free tier limit per request


def _build_property_text(prop: Dict[str, Any]) -> str:
    """Build a rich, searchable text representation of a property."""
    parts = [
        f"{prop.get('title', '')}",
        f"Type: {prop.get('property_type', '')}",
        f"Listing: {prop.get('listing_type', '')}",
        f"Location: {prop.get('location', '')}, {prop.get('city', '')}",
        f"Price: {prop.get('price', '')} {prop.get('currency', 'KES')}",
    ]

    if prop.get("bedrooms"):
        parts.append(f"Bedrooms: {prop['bedrooms']}")
    if prop.get("bathrooms"):
        parts.append(f"Bathrooms: {prop['bathrooms']}")
    if prop.get("square_meters"):
        parts.append(f"Size: {prop['square_meters']} sqm")
    if prop.get("lot_size_sqm"):
        parts.append(f"Lot: {prop['lot_size_sqm']} sqm")
    if prop.get("year_built"):
        parts.append(f"Year built: {prop['year_built']}")
    if prop.get("furnished"):
        parts.append("Furnished")
    if prop.get("parking_spots"):
        parts.append(f"Parking: {prop['parking_spots']} spots")
    if prop.get("amenities"):
        parts.append(f"Amenities: {', '.join(prop['amenities'])}")
    if prop.get("has_garden"):
        parts.append("Has garden")
    if prop.get("has_swimming_pool"):
        parts.append("Has swimming pool")
    if prop.get("pet_friendly"):
        parts.append("Pet friendly")
    if prop.get("gated_community"):
        parts.append("Gated community")

    parts.append(f"Description: {prop.get('description', '')}")

    return " | ".join(parts)


async def index_all_properties() -> int:
    """Fetch all available properties from Supabase, embed them, and upsert into Qdrant."""
    await make_collection(PROPERTIES_COLLECTION)

    properties = await db.search_properties(status="available")
    if not properties:
        logger.warning("No properties found in Supabase to index.")
        return 0

    logger.info("Indexing {} properties into Qdrant...", len(properties))

    for i in range(0, len(properties), BATCH_SIZE):
        batch = properties[i : i + BATCH_SIZE]
        texts = [_build_property_text(p) for p in batch]

        try:
            embeddings = await get_embeddings(texts)
        except Exception:
            logger.exception("Embedding batch {} failed, skipping.", i // BATCH_SIZE)
            continue

        points = []
        for prop, vector in zip(batch, embeddings):
            prop_id = str(prop["id"])
            payload = {
                "title": prop.get("title", ""),
                "property_type": prop.get("property_type", ""),
                "listing_type": prop.get("listing_type", ""),
                "price": float(prop.get("price", 0)),
                "bedrooms": prop.get("bedrooms", 0) or 0,
                "bathrooms": prop.get("bathrooms", 0) or 0,
                "square_meters": float(prop.get("square_meters", 0) or 0),
                "location": prop.get("location", ""),
                "city": prop.get("city", ""),
                "amenities": prop.get("amenities", []),
                "furnished": prop.get("furnished", False),
                "status": prop.get("status", "available"),
            }
            points.append(PointStruct(id=prop_id, vector=vector, payload=payload))

        if points:
            await qdrant_client.upsert(
                collection_name=PROPERTIES_COLLECTION,
                points=points,
                wait=True,
            )

        logger.success("Indexed {} properties.", len(points))
    return len(properties)


async def delete_property_index(property_id: str) -> bool:
    """Remove a single property from the Qdrant index."""
    try:
        await qdrant_client.delete(
            collection_name=PROPERTIES_COLLECTION,
            points_selector=[property_id],
            wait=True,
        )
    except Exception:
        logger.exception("Failed to delete property {} from Qdrant", property_id)
        return False

    logger.success("Removed property {} from Qdrant index.", property_id)
    return True


async def semantic_search(
    query: str,
    limit: int = 5,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    city: Optional[str] = None,
    property_type: Optional[str] = None,
    listing_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search properties semantically using Qdrant."""
    await ensure_collection(PROPERTIES_COLLECTION)

    try:
        embeddings = await get_embeddings([query])
    except Exception:
        logger.exception("Failed to embed search query")
        return []

    query_vector = embeddings[0]

    must_filters = []
    if price_min is not None or price_max is not None:
        price_range = Range(gte=price_min, lte=price_max)
        must_filters.append(FieldCondition(key="price", range=price_range))
    if city:
        must_filters.append(FieldCondition(key="city", match=MatchValue(value=city)))
    if property_type:
        must_filters.append(FieldCondition(key="property_type", match=MatchValue(value=property_type)))
    if listing_type:
        must_filters.append(FieldCondition(key="listing_type", match=MatchValue(value=listing_type)))

    qdrant_filter = Filter(must=must_filters) if must_filters else None

    results = await qdrant_client.query_points(
        collection_name=PROPERTIES_COLLECTION,
        query=query_vector,
        limit=limit,
        query_filter=qdrant_filter,
        with_payload=True,
        with_vectors=False,
    )

    return [
        {
            "id": hit.id,
            "score": round(hit.score, 4),
            **hit.payload,
        }
        for hit in results.points
    ]


# Re-export for convenience
from src.tools.qdrant import make_collection as ensure_collection
