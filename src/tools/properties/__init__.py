"""
Property embedding pipeline — embeds property descriptions and indexes them
in Qdrant for semantic search.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Union

from loguru import logger
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointStruct, Range

from src.tools.embeddings import get_embeddings
from src.tools.qdrant import client as qdrant_client, make_collection
from src.services.db import db

PROPERTIES_COLLECTION = "properties"
VECTOR_SIZE = 1024  # Cloudflare qwen3-embedding-0.6b / bge-large outputs 1024-dim vectors
BATCH_SIZE = 20  # Cloudflare per-request batch limit


def _build_property_text(prop: Dict[str, Any]) -> str:
    """Build a rich, searchable text representation of a property with full semantic context."""
    title = prop.get("title", "")
    p_type = prop.get("property_type", "")
    l_type = prop.get("listing_type", "")
    loc = prop.get("location", "")
    city = prop.get("city", "Nairobi")
    price = prop.get("price", "")
    currency = prop.get("currency", "KES")

    parts = [
        f"Title: {title}",
        f"Property Type: {p_type}",
        f"Listing: {l_type}",
        f"Location: {loc}, {city}",
        f"Price: {price} {currency}",
    ]

    if prop.get("bedrooms") is not None:
        parts.append(f"{prop['bedrooms']} Bedrooms")
    if prop.get("bathrooms") is not None:
        parts.append(f"{prop['bathrooms']} Bathrooms")
    if prop.get("square_meters"):
        parts.append(f"Size: {prop['square_meters']} square meters")
    if prop.get("lot_size_sqm"):
        parts.append(f"Land/Lot: {prop['lot_size_sqm']} square meters")
    if prop.get("furnished"):
        parts.append("Fully furnished")
    if prop.get("parking_spots"):
        parts.append(f"Parking: {prop['parking_spots']} dedicated spaces")
    if prop.get("amenities"):
        amenities_str = ", ".join(prop["amenities"]) if isinstance(prop["amenities"], list) else str(prop["amenities"])
        parts.append(f"Key Amenities: {amenities_str}")
    if prop.get("has_garden"):
        parts.append("Features a lush private garden")
    if prop.get("has_swimming_pool"):
        parts.append("Has a swimming pool")
    if prop.get("pet_friendly"):
        parts.append("Pet friendly property")
    if prop.get("gated_community"):
        parts.append("Located inside a secure gated community")

    desc = prop.get("description", "")
    if desc:
        parts.append(f"Overview: {desc}")

    return " | ".join(parts)


def _build_point_payload(prop: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts indexed and metadata payload for a Qdrant point."""
    return {
        "title": prop.get("title", ""),
        "description": prop.get("description", ""),
        "property_type": str(prop.get("property_type", "")),
        "listing_type": str(prop.get("listing_type", "")),
        "price": float(prop.get("price", 0)),
        "currency": prop.get("currency", "KES"),
        "bedrooms": int(prop.get("bedrooms", 0) or 0),
        "bathrooms": int(prop.get("bathrooms", 0) or 0),
        "square_meters": float(prop.get("square_meters", 0) or 0),
        "location": prop.get("location", ""),
        "city": prop.get("city", "Nairobi"),
        "amenities": prop.get("amenities", []) if isinstance(prop.get("amenities"), list) else [],
        "furnished": bool(prop.get("furnished", False)),
        "has_garden": bool(prop.get("has_garden", False)),
        "has_swimming_pool": bool(prop.get("has_swimming_pool", False)),
        "images": prop.get("images", []) if isinstance(prop.get("images"), list) else [],
        "agent_name": prop.get("agent_name", ""),
        "agent_phone": prop.get("agent_phone", ""),
        "status": prop.get("status", "available"),
    }


async def index_property(property_data: Union[str, Dict[str, Any]]) -> bool:
    """Index or update a single property in Qdrant."""
    await make_collection(PROPERTIES_COLLECTION)

    if isinstance(property_data, str):
        prop = await db.get_property_by_id(property_data)
        if not prop:
            logger.warning("Cannot index property {}: not found in DB", property_data)
            return False
    else:
        prop = property_data

    prop_id = str(prop.get("id"))
    text = _build_property_text(prop)

    try:
        embeddings = await get_embeddings([text])
        if not embeddings:
            logger.error("Failed to generate embedding for property {}", prop_id)
            return False

        point = PointStruct(
            id=prop_id,
            vector=embeddings[0],
            payload=_build_point_payload(prop),
        )
        await qdrant_client.upsert(
            collection_name=PROPERTIES_COLLECTION,
            points=[point],
            wait=True,
        )
        logger.info("Indexed property '{}' ({}) in Qdrant", prop.get("title"), prop_id)
        return True
    except Exception as exc:
        logger.exception("Failed to index property {} in Qdrant: {}", prop_id, exc)
        return False


async def index_all_properties(concurrency: int = 6) -> int:
    """Fetch all available properties from Supabase, embed them concurrently in batches, and upsert into Qdrant."""
    await make_collection(PROPERTIES_COLLECTION)

    properties = await db.get_all_properties(status="available")
    if not properties:
        logger.warning("No properties found in Supabase to index.")
        return 0

    logger.info("Indexing {} properties into Qdrant with concurrency={}...", len(properties), concurrency)
    sem = asyncio.Semaphore(concurrency)
    indexed_count = 0
    lock = asyncio.Lock()

    async def _process_batch(batch_idx: int, batch: List[Dict[str, Any]]):
        nonlocal indexed_count
        async with sem:
            texts = [_build_property_text(p) for p in batch]
            try:
                embeddings = await get_embeddings(texts)
                if not embeddings or len(embeddings) != len(batch):
                    logger.error("Embedding batch mismatch for batch index {}", batch_idx)
                    return
            except Exception:
                logger.exception("Embedding batch {} failed, skipping.", batch_idx)
                return

            points = []
            for prop, vector in zip(batch, embeddings):
                prop_id = str(prop["id"])
                points.append(
                    PointStruct(
                        id=prop_id,
                        vector=vector,
                        payload=_build_point_payload(prop),
                    )
                )

            if points:
                try:
                    await qdrant_client.upsert(
                        collection_name=PROPERTIES_COLLECTION,
                        points=points,
                        wait=False,
                    )
                    async with lock:
                        indexed_count += len(points)
                    logger.info("Indexed batch {}/{} ({} properties).", batch_idx + 1, (len(properties) + BATCH_SIZE - 1) // BATCH_SIZE, len(points))
                except Exception as e:
                    logger.error("Failed to upsert points for batch {}: {}", batch_idx, e)

    batches = [
        (i // BATCH_SIZE, properties[i : i + BATCH_SIZE])
        for i in range(0, len(properties), BATCH_SIZE)
    ]
    tasks = [_process_batch(idx, b) for idx, b in batches]
    await asyncio.gather(*tasks)

    logger.success("Completed Qdrant indexing: total {} properties.", indexed_count)
    return indexed_count


async def delete_property_index(property_id: str) -> bool:
    """Remove a single property from the Qdrant index."""
    try:
        await qdrant_client.delete(
            collection_name=PROPERTIES_COLLECTION,
            points_selector=[property_id],
            wait=True,
        )
        logger.success("Removed property {} from Qdrant index.", property_id)
        return True
    except Exception:
        logger.exception("Failed to delete property {} from Qdrant", property_id)
        return False


async def semantic_search(
    query: str,
    limit: int = 5,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    city: Optional[str] = None,
    location: Optional[str] = None,
    property_type: Optional[str] = None,
    listing_type: Optional[str] = None,
    bedrooms: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Search properties semantically using Qdrant vector similarity with metadata filters."""
    await ensure_collection(PROPERTIES_COLLECTION)

    try:
        embeddings = await get_embeddings([query])
        if not embeddings:
            logger.warning("Could not compute embeddings for query: '{}'", query)
            return []
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
    if location:
        must_filters.append(FieldCondition(key="location", match=MatchValue(value=location)))
    if property_type:
        must_filters.append(FieldCondition(key="property_type", match=MatchValue(value=property_type)))
    if listing_type:
        must_filters.append(FieldCondition(key="listing_type", match=MatchValue(value=listing_type)))
    if bedrooms is not None:
        must_filters.append(FieldCondition(key="bedrooms", match=MatchValue(value=bedrooms)))

    # Only available properties
    must_filters.append(FieldCondition(key="status", match=MatchValue(value="available")))

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
            "id": str(hit.id),
            "score": round(hit.score, 4),
            **hit.payload,
        }
        for hit in results.points
    ]


# Re-export for convenience
from src.tools.qdrant import make_collection as ensure_collection

