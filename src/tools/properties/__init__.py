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
    subtype = prop.get("property_subtype", "")
    l_type = prop.get("listing_type", "")
    p_period = prop.get("price_period", "")
    loc = prop.get("location", "")
    address = prop.get("address", "")
    town = prop.get("town", "")
    city = prop.get("city", "Nairobi")
    county = prop.get("county", "")
    country = prop.get("country", "Kenya")
    price = prop.get("price", "")
    currency = prop.get("currency", "KES")

    parts = [
        f"Title: {title}",
    ]
    if subtype:
        parts.append(f"{subtype.capitalize()} {p_type}")
    else:
        parts.append(f"Property Type: {p_type}")
    parts.append(f"Listing: {l_type}")
    if p_period:
        parts.append(f"Price Period: {p_period}")

    # Location breadcrumb
    loc_bits = [b for b in [loc, address, town, city, county, country] if b]
    parts.append(f"Location: {', '.join(loc_bits)}")

    parts.append(f"Price: {price} {currency}")
    if prop.get("lot_size_sqm"):
        parts.append(f"Lot/Land: {prop['lot_size_sqm']} sqm")
    if prop.get("plot_dimensions"):
        parts.append(f"Plot dimensions: {prop['plot_dimensions']}")
    if prop.get("land_size_raw"):
        parts.append(f"Land size: {prop['land_size_raw']}")

    if prop.get("bedrooms") is not None:
        parts.append(f"{prop['bedrooms']} Bedrooms")
    if prop.get("bathrooms") is not None:
        parts.append(f"{prop['bathrooms']} Bathrooms")
    if prop.get("square_meters"):
        parts.append(f"Size: {prop['square_meters']} sqm")
    if prop.get("furnished"):
        parts.append("Furnished")
    if prop.get("year_built"):
        parts.append(f"Year built: {prop['year_built']}")

    # Amenities feature tags (includes garden/pool/parking/pet-friendly/etc.)
    if prop.get("amenities"):
        amenities_str = ", ".join(prop["amenities"]) if isinstance(prop["amenities"], list) else str(prop["amenities"])
        parts.append(f"Amenities: {amenities_str}")

    # Listing agent (if attached by the indexer)
    agent = prop.get("agent")
    if isinstance(agent, dict):
        name = " ".join(filter(None, [agent.get("first_name"), agent.get("last_name")])).strip()
        if name:
            parts.append(f"Listed by: {name}")
        if agent.get("phone"):
            parts.append(f"Agent phone: {agent['phone']}")
        if agent.get("agency_name"):
            parts.append(f"Agency: {agent['agency_name']}")

    desc = prop.get("description", "")
    if desc:
        parts.append(f"Overview: {desc}")

    return " | ".join(parts)


def _build_point_payload(prop: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts indexed and metadata payload for a Qdrant point.

    Mirrors the new Property254 model: features live in `amenities`, the
    listing agent is referenced by `agent_id`, and the gallery lives in
    `images` (stored as a compact list of URL strings here).
    """
    images = prop.get("images", [])
    if isinstance(images, list):
        image_urls = [im.get("url") if isinstance(im, dict) else im for im in images]
    else:
        image_urls = []

    agent = prop.get("agent")
    agent_id = prop.get("agent_id")
    if not agent_id and isinstance(agent, dict):
        agent_id = agent.get("id")

    return {
        "title": prop.get("title", ""),
        "description": prop.get("description", ""),
        "property_type": str(prop.get("property_type", "")),
        "property_subtype": str(prop.get("property_subtype", "")),
        "listing_type": str(prop.get("listing_type", "")),
        "price_period": str(prop.get("price_period", "")),
        "price": float(prop.get("price", 0)),
        "currency": prop.get("currency", "KES"),
        "bedrooms": int(prop.get("bedrooms", 0) or 0),
        "bathrooms": int(prop.get("bathrooms", 0) or 0),
        "square_meters": float(prop.get("square_meters", 0) or 0),
        "lot_size_sqm": prop.get("lot_size_sqm"),
        "location": prop.get("location", ""),
        "address": prop.get("address", ""),
        "town": prop.get("town", ""),
        "city": prop.get("city", "Nairobi"),
        "country": prop.get("country", "Kenya"),
        "amenities": prop.get("amenities", []) if isinstance(prop.get("amenities"), list) else [],
        "furnished": bool(prop.get("furnished", False)),
        "images": image_urls,
        "agent_id": str(agent_id) if agent_id else "",
        "status": prop.get("status", "available"),
    }


async def index_property(property_data: Union[str, Dict[str, Any]]) -> bool:
    """Index or update a single property in Qdrant."""
    await make_collection(PROPERTIES_COLLECTION)

    if isinstance(property_data, str):
        prop = await db.get_property_full(property_data)
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

    # Attach ordered image galleries + agent profiles in batched lookups so the
    # indexer does not issue N+1 queries per property.
    pids = [str(p.get("id")) for p in properties if p.get("id")]
    agent_ids = [str(p.get("agent_id")) for p in properties if p.get("agent_id")]
    images_map = await db.get_property_images_batch(pids)
    agents_map = await db.get_agents_by_ids(agent_ids)
    for p in properties:
        pid = str(p.get("id"))
        p["images"] = images_map.get(pid, [])
        aid = p.get("agent_id")
        p["agent"] = agents_map.get(str(aid)) if aid else None

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
    price_period: Optional[str] = None,
    property_subtype: Optional[str] = None,
    town: Optional[str] = None,
    country: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search properties semantically using Qdrant vector similarity with metadata filters."""
    await ensure_collection(PROPERTIES_COLLECTION)

    try:
        embeddings = await get_embeddings([query])
        if not embeddings:
            raise RuntimeError(
                f"Embeddings service returned an empty result for query: '{query}'. "
                "The embeddings API may be unavailable or the query was rejected."
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("Failed to embed search query: '{}'", query)
        raise RuntimeError(
            f"Failed to generate embeddings for the search query: {exc}"
        ) from exc

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
    if price_period:
        must_filters.append(FieldCondition(key="price_period", match=MatchValue(value=price_period)))
    if property_subtype:
        must_filters.append(FieldCondition(key="property_subtype", match=MatchValue(value=property_subtype)))
    if town:
        must_filters.append(FieldCondition(key="town", match=MatchValue(value=town)))
    if country:
        must_filters.append(FieldCondition(key="country", match=MatchValue(value=country)))

    # Only available properties
    must_filters.append(FieldCondition(key="status", match=MatchValue(value="available")))

    qdrant_filter = Filter(must=must_filters) if must_filters else None

    try:
        results = await qdrant_client.query_points(
            collection_name=PROPERTIES_COLLECTION,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        logger.exception("Qdrant query_points failed for query: '{}'", query)
        raise RuntimeError(
            f"Vector store (Qdrant) search failed: {exc}"
        ) from exc

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

