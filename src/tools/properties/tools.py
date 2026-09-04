"""
Agent-facing property search tools registered with the shared ToolRegistry.

Exposes five tools:
    - search_properties          → structured filter-based search (Supabase)
    - semantic_search_properties → natural language search (Qdrant + embeddings)
    - get_property_details       → full property profile (images + agent) by UUID
    - compare_properties        → side-by-side comparison of 2-4 properties
    - create_property            → create or update a property listing (Supabase + Qdrant)

Data-model notes (Property254-compatible, see SQl/schema.sql):
    * Listing agent lives in the normalized `agents` table, referenced by
      `agent_id` — it is JOINed in at read time, not denormalized on the row.
    * Images live in the `property_images` table (ordered gallery + featured),
      also JOINed at read time.
    * Feature booleans (garden, pool, pet-friendly, gated community, parking)
      are folded into the `amenities` tag array.
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


# ── Shared Simon defaults ────────────────────────────────────────────────────

COMPANY_NAME = "Realtors Round Tables"
WEBSITE_URL = "https://realtorsroundtables.co.ke"
DEFAULT_AGENT_NAME = "Simon | Realtors Round Tables"
DEFAULT_AGENT_PHONE = "0701454854"
DEFAULT_AGENT_EMAIL = "info@realtorsroundtables.co.ke"
DEFAULT_AGENT_WA = "https://wa.me/254701454854"


def _agent_display_name(agent: Dict[str, Any]) -> str:
	"""Human-readable agent name from a normalized agent row (or Simon default)."""
	if agent:
		parts = [agent.get("first_name"), agent.get("last_name")]
		name = " ".join(p for p in parts if p)
		if name:
			return name
	return DEFAULT_AGENT_NAME


def _wa_link(phone: str) -> str:
	"""Build a clickable WhatsApp link from a phone number string."""
	if not phone:
		return DEFAULT_AGENT_WA
	digits = "".join(ch for ch in phone if ch.isdigit())
	if digits.startswith("254") and len(digits) == 12:
		pass
	elif digits.startswith("0") and len(digits) == 10:
		digits = "254" + digits[1:]
	elif len(digits) == 9 and digits.startswith("7"):
		digits = "254" + digits
	return f"https://wa.me/{digits}"


def _image_urls(prop: Dict[str, Any]) -> List[str]:
	"""Return ordered image URLs for a property row (which may carry dicts or strings)."""
	images = prop.get("images", [])
	if not isinstance(images, list):
		return []
	urls = []
	for im in images:
		if isinstance(im, dict) and im.get("url"):
			urls.append(im["url"])
		elif isinstance(im, str):
			urls.append(im)
	return urls


def _summarize_property(p: Dict[str, Any]) -> Dict[str, Any]:
	"""Extract a concise, token-efficient summary of a property for search result listings."""
	amenities = p.get("amenities", [])
	if isinstance(amenities, list):
		amenities = amenities[:6]
	image_urls = _image_urls(p)

	summary = {
		"id": str(p.get("id", "")),
		"title": p.get("title", ""),
		"price": p.get("price", 0),
		"currency": p.get("currency", "KES"),
		"price_period": p.get("price_period"),
		"bedrooms": p.get("bedrooms"),
		"bathrooms": p.get("bathrooms"),
		"property_type": p.get("property_type"),
		"property_subtype": p.get("property_subtype"),
		"listing_type": p.get("listing_type"),
		"location": p.get("location", ""),
		"city": p.get("city", "Nairobi"),
		"country": p.get("country", "Kenya"),
		"amenities": amenities,
		"image": image_urls[0] if image_urls else None,
		"agent_id": p.get("agent_id"),
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
	if payload.price_period:
		filters["price_period"] = payload.price_period.value
	if payload.property_subtype:
		filters["property_subtype"] = payload.property_subtype
	if payload.location:
		filters["location"] = payload.location
	if payload.city:
		filters["city"] = payload.city
	if payload.town:
		filters["town"] = payload.town
	if payload.country:
		filters["country"] = payload.country
	if payload.bedrooms is not None:
		filters["bedrooms"] = payload.bedrooms
	if payload.bathrooms is not None:
		filters["bathrooms"] = payload.bathrooms
	if payload.furnished is not None:
		filters["furnished"] = payload.furnished
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
	if payload.min_lot_size_sqm is not None:
		filters["min_lot_size_sqm"] = payload.min_lot_size_sqm
	if payload.max_lot_size_sqm is not None:
		filters["max_lot_size_sqm"] = payload.max_lot_size_sqm
	if payload.amenities:
		filters["amenities"] = payload.amenities

	filters["sort_by"] = payload.sort_by.value
	filters["sort_order"] = payload.sort_order.value
	filters["limit"] = payload.limit
	filters["offset"] = payload.offset

	logger.info("Structured search with filters: {}", filters)

	try:
		# Attach image galleries so summaries can surface a featured thumbnail.
		results = await db.search_properties_advanced(**filters, include_images=True)
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
			price_period=payload.price_period.value if payload.price_period else None,
			property_subtype=payload.property_subtype,
			town=payload.town,
			country=payload.country,
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
	- Full title, detailed description, and listing purpose (sale / rent).
	- Price, currency, price period, and price-per-sqm.
	- Physical attributes: bedrooms, bathrooms, square meters, lot size,
	  plot dimensions, year built, and floor details.
	- Neighborhood / address / town / city / county / country location.
	- Complete amenities feature tags and furnished status.
	- Full ordered image gallery (URLs, featured flag).
	- Listing agent profile (name, phone, email, agency) joined from the
	  normalized ``agents`` table, with clickable WhatsApp contact links.

	Use this when a customer asks for more info or photos about a specific property
	discovered in search results.
	"""
	logger.info("Fetching details for property ID: {}", payload.property_id)
	prop = await db.get_property_full(payload.property_id)
	if not prop:
		logger.warning("Property with ID '{}' not found in database", payload.property_id)
		return {
			"error": f"Property with ID '{payload.property_id}' was not found. It may have been sold or removed.",
		}

	images = _image_urls(prop)
	agent = prop.get("agent")
	name = _agent_display_name(agent)
	phone = (agent or {}).get("phone") or DEFAULT_AGENT_PHONE
	email = (agent or {}).get("email") or DEFAULT_AGENT_EMAIL

	logger.success("Retrieved property details successfully | property_id={} title='{}'", payload.property_id, prop.get("title"))
	return {
		"status": "success",
		"property": {
			"id": str(prop.get("id", "")),
			"title": prop.get("title"),
			"description": prop.get("description"),
			"property_type": prop.get("property_type"),
			"property_subtype": prop.get("property_subtype"),
			"listing_type": prop.get("listing_type"),
			"price_period": prop.get("price_period"),
			"price": float(prop.get("price", 0)),
			"currency": prop.get("currency", "KES"),
			"price_per_sqm": prop.get("price_per_sqm"),
			"bedrooms": prop.get("bedrooms"),
			"bathrooms": prop.get("bathrooms"),
			"square_meters": prop.get("square_meters"),
			"lot_size_sqm": prop.get("lot_size_sqm"),
			"plot_dimensions": prop.get("plot_dimensions"),
			"land_size_raw": prop.get("land_size_raw"),
			"year_built": prop.get("year_built"),
			"floor_number": prop.get("floor_number"),
			"total_floors": prop.get("total_floors"),
			"location": prop.get("location"),
			"address": prop.get("address"),
			"town": prop.get("town"),
			"city": prop.get("city"),
			"county": prop.get("county"),
			"country": prop.get("country"),
			"latitude": prop.get("latitude"),
			"longitude": prop.get("longitude"),
			"amenities": prop.get("amenities", []),
			"furnished": prop.get("furnished", False),
			"images": images,
			"featured_image": images[0] if images else None,
			"video_url": prop.get("video_url"),
			"agent_id": prop.get("agent_id"),
			"listing_agent": {
				"name": name,
				"phone": phone,
				"email": email,
				"agency_name": (agent or {}).get("agency_name"),
				"whatsapp_link": _wa_link(phone),
			},
			"customer_service_executive": {
				"name": "Simon",
				"phone": DEFAULT_AGENT_PHONE,
				"whatsapp": DEFAULT_AGENT_WA,
				"website": WEBSITE_URL,
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
	- Best for families based on size and amenity feature tags (garden, security, gated, pet-friendly)

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
		amenities = p.get("amenities", []) or []

		comparison_rows.append({
			"id": str(p["id"]),
			"title": p.get("title", "Untitled"),
			"property_type": p.get("property_type", ""),
			"property_subtype": p.get("property_subtype"),
			"listing_type": p.get("listing_type", ""),
			"price_period": p.get("price_period"),
			"price": price,
			"price_per_sqm": price_per_sqm,
			"bedrooms": p.get("bedrooms", 0) or 0,
			"bathrooms": p.get("bathrooms", 0) or 0,
			"square_meters": sqm,
			"lot_size_sqm": p.get("lot_size_sqm"),
			"location": p.get("location", ""),
			"city": p.get("city", ""),
			"town": p.get("town"),
			"country": p.get("country"),
			"amenities": amenities,
			"furnished": p.get("furnished", False),
			"year_built": p.get("year_built"),
			"description": p.get("description", ""),
		})

	# ── Compute insights ─────────────────────────────────────────────────
	# Best value (lowest price per sqm)
	with_price_per_sqm = [r for r in comparison_rows if r["price_per_sqm"] is not None]
	best_value = min(with_price_per_sqm, key=lambda r: r["price_per_sqm"]) if with_price_per_sqm else None

	# Most spacious
	most_spacious = max(comparison_rows, key=lambda r: r["square_meters"])

	# Best for families (more bedrooms/bathrooms + family-friendly amenities).
	# Feature tags are now folded into the `amenities` array.
	FAMILY_AMENITY_WEIGHTS = {
		"garden": 3,
		"gated": 2,
		"pet_allowed": 1,
		"security": 2,
		"parking": 1,
	}

	def family_score(r: Dict[str, Any]) -> int:
		score = r["bedrooms"] * 2 + (r["bathrooms"] or 0)
		r_amenities = {a.lower() for a in (r.get("amenities") or [])}
		for tag, weight in FAMILY_AMENITY_WEIGHTS.items():
			if tag in r_amenities:
				score += weight
		return score

	best_family = max(comparison_rows, key=family_score)

	# Amenity overlap
	all_amenities = set()
	for r in comparison_rows:
		all_amenities.update(a.lower() for a in (r["amenities"] or []))
	common_amenities = all_amenities.copy()
	for r in comparison_rows:
		common_amenities &= {a.lower() for a in (r["amenities"] or [])}

	# Unique amenities per property
	unique_amenities = {}
	for r in comparison_rows:
		unique_amenities[r["title"]] = list({a.lower() for a in (r["amenities"] or [])} - common_amenities)

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
				"family_friendly_amenities": [a for a in FAMILY_AMENITY_WEIGHTS if a in {a2.lower() for a2 in (best_family["amenities"] or [])}],
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

	The listing agent (if provided via the ``agent`` object or ``agent_id``)
	is find-or-created in the normalized ``agents`` table and linked by
	``agent_id``; the image gallery is stored in the ordered ``property_images``
	table.

	Use this tool when a customer or agent provides property details that should
	be added to the live listings — e.g. a new home for sale, a rental
	available for rent, or updating an existing listing's price/amenities.

	Returns the new property's UUID and a success confirmation.
	"""
	# mode="json" serializes enum values (PropertyType/ListingType/PricePeriod)
	# to their string values so the Supabase client inserts valid enum text.
	prop_data = payload.model_dump(exclude_none=True, mode="json")

	# ── Agent (normalized into `agents`, linked by agent_id) ─────────────
	agent_obj = prop_data.pop("agent", None)
	agent_id = prop_data.pop("agent_id", None)
	if agent_obj and not agent_id:
		agent_row = await db.upsert_agent(agent_obj)
		if agent_row:
			agent_id = str(agent_row.get("id"))
	if agent_id:
		prop_data["agent_id"] = str(agent_id)

	# ── Images (stored in `property_images`, not on the property row) ────
	images = prop_data.pop("images", None)

	logger.info("Creating property | title='{}' type={} listing={}", prop_data.get("title"), prop_data.get("property_type"), prop_data.get("listing_type"))

	result = await db.upsert_property(
		prop_data,
		on_conflict="title,location,price,listing_type,property_type,price_period",
	)
	if not result:
		logger.error("Failed to create property '{}' in Supabase", prop_data.get("title"))
		return {
			"error": "Failed to create property. The database may be unavailable.",
			"hint": "Ask the customer to try again later or contact support.",
		}

	prop_id = str(result.get("id"))

	# Attach the image gallery (first image becomes featured if none flagged).
	if images:
		await db.add_property_images(prop_id, images)

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
		"agent_id": agent_id,
		"images_attached": bool(images),
		"message": f"Property '{prop_data.get('title')}' has been created and is now searchable.",
	}
