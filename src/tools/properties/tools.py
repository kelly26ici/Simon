"""
Agent-facing property search tools registered with the shared ToolRegistry.

Exposes three tools:
    - search_properties          → structured filter-based search (Supabase)
    - semantic_search_properties → natural language search (Qdrant + embeddings)
    - compare_properties        → side-by-side comparison of 2-4 properties
"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from src.tools.registry import registry
from src.tools.properties.schemas import (
    SearchPropertiesSchema,
    SemanticSearchSchema,
    ComparePropertiesSchema,
)
from src.tools.properties import semantic_search
from src.services.db import db


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 1: Structured Filter Search
# ═══════════════════════════════════════════════════════════════════════════════

@registry.register("search_properties", SearchPropertiesSchema)
async def search_properties(payload: SearchPropertiesSchema) -> Dict[str, Any]:
    """
    Search for properties using structured filters like price range, bedrooms,
    location, property type, and amenities.

    Use this tool when the customer gives specific, measurable requirements:
    - "3-bedroom apartment in Kilimani under 15 million"
    - "Houses for sale in Westlands with at least 4 bedrooms"
    - "Studio apartments for rent under 30,000 per month"

    Do NOT use this for vague or lifestyle-based queries like "a cozy family
    home" — use semantic_search_properties for those instead.

    Returns a paginated list of matching properties with all details.
    """
    filters: Dict[str, Any] = {}

    if payload.property_type:
        filters["property_type"] = payload.property_type.value
    if payload.listing_type:
        filters["listing_type"] = payload.listing_type.value
    if payload.location:
        filters["location"] = payload.location
    if payload.city:
        filters["city"] = payload.city
    if payload.bedrooms is not None:
        filters["bedrooms"] = payload.bedrooms
    if payload.bathrooms is not None:
        filters["bathrooms"] = payload.bathrooms
    if payload.furnished is not None:
        filters["furnished"] = payload.furnished
    if payload.pet_friendly is not None:
        filters["pet_friendly"] = payload.pet_friendly
    if payload.gated_community is not None:
        filters["gated_community"] = payload.gated_community

    # Range filters are handled specially by the db layer
    if payload.min_price is not None:
        filters["min_price"] = payload.min_price
    if payload.max_price is not None:
        filters["max_price"] = payload.max_price
    if payload.min_bedrooms is not None:
        filters["min_bedrooms"] = payload.min_bedrooms
    if payload.min_sqm is not None:
        filters["min_sqm"] = payload.min_sqm
    if payload.max_sqm is not None:
        filters["max_sqm"] = payload.max_sqm
    if payload.amenities:
        filters["amenities"] = payload.amenities

    filters["sort_by"] = payload.sort_by.value
    filters["sort_order"] = payload.sort_order.value
    filters["limit"] = payload.limit
    filters["offset"] = payload.offset

    logger.info("Structured search with filters: {}", filters)

    try:
        results = await db.search_properties_advanced(**filters)
    except Exception as exc:
        logger.exception("Structured property search failed")
        return {
            "error": "Property search failed.",
            "error_type": type(exc).__name__,
            "detail": str(exc).strip() or repr(exc),
            "hint": (
                "The database may be unreachable or the 'properties' table may be "
                "missing. Do not retry the same search; ask the customer to rephrase "
                "or inform them listings are temporarily unavailable."
            ),
        }

    return {
        "total": len(results),
        "limit": payload.limit,
        "offset": payload.offset,
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 2: Semantic (Natural Language) Search
# ═══════════════════════════════════════════════════════════════════════════════

@registry.register("semantic_search_properties", SemanticSearchSchema)
async def semantic_search_properties(payload: SemanticSearchSchema) -> Dict[str, Any]:
    """
    Search for properties using natural language. This understands the meaning
    and intent behind a query, not just exact keyword matches.

    Use this tool when the customer describes what they want in natural,
    conversational language:
    - "A modern family home with a big garden, quiet neighborhood, near good schools"
    - "Luxury penthouse with city views and modern finishes"
    - "Affordable starter apartment in a safe area with good transport links"

    This is also good for lifestyle-based queries where the customer doesn't
    know exact numbers but has a feel for what they want.

    For queries with specific numbers (exact bedrooms, price range), prefer
    search_properties instead, or use both tools and compare results.
    """
    logger.info("Semantic search: '{}'", payload.query)

    try:
        results = await semantic_search(
            query=payload.query,
            limit=payload.limit,
            price_min=payload.min_price,
            price_max=payload.max_price,
            city=payload.city,
            property_type=payload.property_type.value if payload.property_type else None,
            listing_type=payload.listing_type.value if payload.listing_type else None,
        )
    except Exception as exc:
        logger.exception("Semantic property search failed")
        return {
            "error": "Semantic search failed.",
            "error_type": type(exc).__name__,
            "detail": str(exc).strip() or repr(exc),
            "hint": (
                "This usually means the embeddings service (Cloudflare) or the "
                "vector store (Qdrant) is unreachable, or the property index is empty. "
                "Falling back to search_properties with specific filters may still work."
            ),
        }

    if not results:
        return {
            "total": 0,
            "query": payload.query,
            "message": "No properties matched your description. Try broadening your search or using search_properties with specific filters.",
            "results": [],
        }

    return {
        "total": len(results),
        "query": payload.query,
        "results": results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 3: Property Comparison
# ═══════════════════════════════════════════════════════════════════════════════

@registry.register("compare_properties", ComparePropertiesSchema)
async def compare_properties(payload: ComparePropertiesSchema) -> Dict[str, Any]:
    """
    Compare 2-4 properties side by side. Fetches full details for each property
    and computes a structured comparison including:

    - Price comparison (absolute and per sqm)
    - Size, bedrooms, bathrooms, location
    - Amenities overlap and differences
    - Best value (lowest price per sqm)
    - Best for families / couples / singles based on size and features

    Use this when a customer asks:
    - "Which of these two is better?"
    - "Compare these three apartments for me"
    - "What's the difference between property A and property B?"

    The property IDs come from search_properties or semantic_search_properties
    results — always search first, then compare the top results.
    """
    properties: List[Dict[str, Any]] = []
    missing: List[str] = []

    for pid in payload.property_ids:
        prop = await db.get_property_by_id(pid)
        if prop:
            properties.append(prop)
        else:
            missing.append(pid)

    if not properties:
        return {"error": "None of the requested properties were found. They may have been removed or sold."}

    if len(properties) < 2:
        return {
            "error": "At least 2 valid properties are needed for comparison. "
                     f"Only {len(properties)} found. Missing: {missing}",
        }

    # ── Build comparison ─────────────────────────────────────────────────
    comparison_rows = []
    for p in properties:
        price = float(p.get("price", 0))
        sqm = float(p.get("square_meters", 0) or 0)
        price_per_sqm = round(price / sqm, 2) if sqm > 0 else None

        comparison_rows.append({
            "id": str(p["id"]),
            "title": p.get("title", "Untitled"),
            "property_type": p.get("property_type", ""),
            "listing_type": p.get("listing_type", ""),
            "price": price,
            "price_per_sqm": price_per_sqm,
            "bedrooms": p.get("bedrooms", 0) or 0,
            "bathrooms": p.get("bathrooms", 0) or 0,
            "square_meters": sqm,
            "location": p.get("location", ""),
            "city": p.get("city", ""),
            "amenities": p.get("amenities", []),
            "furnished": p.get("furnished", False),
            "parking_spots": p.get("parking_spots", 0) or 0,
            "year_built": p.get("year_built"),
            "has_garden": p.get("has_garden", False),
            "has_swimming_pool": p.get("has_swimming_pool", False),
            "pet_friendly": p.get("pet_friendly", False),
            "gated_community": p.get("gated_community", False),
            "description": p.get("description", ""),
        })

    # ── Compute insights ─────────────────────────────────────────────────
    # Best value (lowest price per sqm)
    with_price_per_sqm = [r for r in comparison_rows if r["price_per_sqm"] is not None]
    best_value = min(with_price_per_sqm, key=lambda r: r["price_per_sqm"]) if with_price_per_sqm else None

    # Most spacious
    most_spacious = max(comparison_rows, key=lambda r: r["square_meters"])

    # Best for families (most bedrooms + garden + gated)
    def family_score(r: Dict) -> int:
        score = r["bedrooms"] * 2 + r["bathrooms"]
        if r["has_garden"]:
            score += 3
        if r["gated_community"]:
            score += 2
        if r["pet_friendly"]:
            score += 1
        return score

    best_family = max(comparison_rows, key=family_score)

    # Amenity overlap
    all_amenities = set()
    for r in comparison_rows:
        all_amenities.update(r["amenities"])
    common_amenities = all_amenities.copy()
    for r in comparison_rows:
        common_amenities &= set(r["amenities"])

    # Unique amenities per property
    unique_amenities = {}
    for r in comparison_rows:
        unique_amenities[r["title"]] = list(set(r["amenities"]) - common_amenities)

    return {
        "compared": len(comparison_rows),
        "missing_ids": missing if missing else None,
        "properties": comparison_rows,
        "analysis": {
            "best_value": {
                "title": best_value["title"],
                "price_per_sqm": best_value["price_per_sqm"],
            } if best_value else None,
            "most_spacious": {
                "title": most_spacious["title"],
                "square_meters": most_spacious["square_meters"],
            },
            "best_for_families": {
                "title": best_family["title"],
                "bedrooms": best_family["bedrooms"],
                "has_garden": best_family["has_garden"],
                "gated_community": best_family["gated_community"],
            },
            "common_amenities": list(common_amenities) if common_amenities else [],
            "unique_amenities": unique_amenities,
        },
    }