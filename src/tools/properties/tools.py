"""
Agent-facing property search tools registered with the shared ToolRegistry.

Exposes four tools:
    - search_properties          → structured filter-based search (Supabase)
    - semantic_search_properties → natural language search (Qdrant + embeddings)
    - compare_properties        → side-by-side comparison of 2-4 properties
    - create_property            → create or update a property listing (Supabase + Qdrant)
"""

from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger

from src.tools.registry import registry
from src.tools.properties.schemas import (
    SearchPropertiesSchema,
    SemanticSearchSchema,
    GetPropertyDetailsSchema,
    ComparePropertiesSchema,
    CreatePropertySchema,
)
from src.tools.properties import semantic_search, index_property
from src.services.db import db


def _summarize_property(p: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a concise, token-efficient summary of a property for search result listings."""
    amenities = p.get("amenities", [])
    if isinstance(amenities, list):
        amenities = amenities[:6]
    images = p.get("images", [])
    first_image = images[0] if isinstance(images, list) and images else None

    summary = {
        "id": str(p.get("id", "")),
        "title": p.get("title", ""),
        "price": p.get("price", 0),
        "currency": p.get("currency", "KES"),
        "bedrooms": p.get("bedrooms"),
        "bathrooms": p.get("bathrooms"),
        "property_type": p.get("property_type"),
        "listing_type": p.get("listing_type"),
        "location": p.get("location", ""),
        "city": p.get("city", "Nairobi"),
        "amenities": amenities,
        "image": first_image,
    }
    if "score" in p:
        summary["score"] = p["score"]
    return summary


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

    Returns a paginated list of matching properties with concise summary details.
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

    summaries = [_summarize_property(p) for p in results]
    logger.success("Structured property search succeeded | found={} properties", len(summaries))

    return {
        "total": len(summaries),
        "limit": payload.limit,
        "offset": payload.offset,
        "results": summaries,
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
            location=payload.location,
            property_type=payload.property_type.value if payload.property_type else None,
            listing_type=payload.listing_type.value if payload.listing_type else None,
            bedrooms=payload.bedrooms,
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

    summaries = [_summarize_property(p) for p in results]
    logger.success("Semantic property search succeeded | query='{}' found={}", payload.query, len(summaries))

    return {
        "total": len(summaries),
        "query": payload.query,
        "results": summaries,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 3: Get Property Details
# ═══════════════════════════════════════════════════════════════════════════════

@registry.register("get_property_details", GetPropertyDetailsSchema)
async def get_property_details(payload: GetPropertyDetailsSchema) -> Dict[str, Any]:
    """
    Retrieve complete information about a specific property by its UUID.

    Returns:
    - Full title, detailed description, location, price, and currency.
    - Detailed bedroom, bathroom, square meters, year built, and floor details.
    - Complete amenities list, furnished status, parking spots, garden, pool.
    - Media links (high-resolution photo URLs, virtual tour links).
    - Assigned agent name, phone number, and email.

    Use this when a customer asks for more info or photos about a specific property
    discovered in search results.
    """
    logger.info("Fetching details for property ID: {}", payload.property_id)
    prop = await db.get_property_by_id(payload.property_id)
    if not prop:
        logger.warning("Property with ID '{}' not found in database", payload.property_id)
        return {
            "error": f"Property with ID '{payload.property_id}' was not found. It may have been sold or removed.",
        }

    logger.success("Retrieved property details successfully | property_id={} title='{}'", payload.property_id, prop.get("title"))
    return {
        "status": "success",
        "property": {
            "id": str(prop["id"]),
            "title": prop.get("title"),
            "description": prop.get("description"),
            "property_type": prop.get("property_type"),
            "listing_type": prop.get("listing_type"),
            "price": float(prop.get("price", 0)),
            "currency": prop.get("currency", "KES"),
            "price_per_sqm": prop.get("price_per_sqm"),
            "bedrooms": prop.get("bedrooms"),
            "bathrooms": prop.get("bathrooms"),
            "square_meters": prop.get("square_meters"),
            "location": prop.get("location"),
            "city": prop.get("city"),
            "county": prop.get("county"),
            "amenities": prop.get("amenities", []),
            "furnished": prop.get("furnished", False),
            "parking_spots": prop.get("parking_spots", 0),
            "has_garden": prop.get("has_garden", False),
            "has_swimming_pool": prop.get("has_swimming_pool", False),
            "pet_friendly": prop.get("pet_friendly", False),
            "gated_community": prop.get("gated_community", False),
            "images": prop.get("images", []),
            "video_url": prop.get("video_url"),
            "virtual_tour_url": prop.get("virtual_tour_url"),
            "agent_name": prop.get("agent_name", "Realtors Round Tables Agent"),
            "agent_phone": prop.get("agent_phone", "0701454854"),
            "agent_email": prop.get("agent_email", "info@realtorsroundtables.co.ke"),
            "agent_whatsapp": (
                f"https://wa.me/254{prop.get('agent_phone', '0701454854').lstrip('+').lstrip('254').lstrip('0')}"
                if prop.get("agent_phone")
                else "https://wa.me/254701454854"
            ),
            "customer_service_executive": {
                "name": "Simon",
                "phone": "0701454854",
                "whatsapp": "https://wa.me/254701454854",
                "website": "https://realtorsroundtables.co.ke",
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 4: Property Comparison
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
        logger.warning("Property comparison failed: none of requested IDs found {}", payload.property_ids)
        return {"error": "None of the requested properties were found. They may have been removed or sold."}

    if len(properties) < 2:
        logger.warning("Property comparison failed: insufficient properties ({})", len(properties))
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

    logger.success("Property comparison computed successfully | compared={}", len(comparison_rows))
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


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 5: Create / Update Property
# ═══════════════════════════════════════════════════════════════════════════════

@registry.register("create_property", CreatePropertySchema)
async def create_property(payload: CreatePropertySchema) -> Dict[str, Any]:
    """
    Create or update a property listing in the database. The listing is then
    immediately indexed in Qdrant so it appears in both structured and
    semantic searches.

    Use this tool when a customer or agent provides property details that should
    be added to the live listings — e.g. a new home for sale, a rental
    available for rent, or updating an existing listing's price/amenities.

    Returns the new property's UUID and a success confirmation.
    """
    prop_data = payload.model_dump(exclude_none=True)
    logger.info("Creating property | title='{}' type={} listing={}", prop_data.get("title"), prop_data.get("property_type"), prop_data.get("listing_type"))

    result = await db.upsert_property(prop_data)
    if not result:
        logger.error("Failed to create property '{}' in Supabase", prop_data.get("title"))
        return {
            "error": "Failed to create property. The database may be unavailable.",
            "hint": "Ask the customer to try again later or contact support.",
        }

    prop_id = str(result.get("id"))

    # Real-time Qdrant indexing so the property appears in semantic search
    try:
        indexed = await index_property(prop_id)
        if not indexed:
            logger.warning("Property {} created in DB but Qdrant indexing failed", prop_id)
    except Exception as exc:
        logger.warning("Qdrant indexing error for property {}: {}", prop_id, exc)

    logger.success("Property created and indexed | id={} title='{}'", prop_id, prop_data.get("title"))
    return {
        "status": "success",
        "property_id": prop_id,
        "title": prop_data.get("title"),
        "message": f"Property '{prop_data.get('title')}' has been created and is now searchable.",
    }