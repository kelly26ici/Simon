# src/routes/properties.py

"""REST API routes for property listing management.

Public read/search endpoints are open. Write endpoints (create, update, delete)
require HTTP Basic auth so that only agents / owners can submit or remove
listings without ever exposing the Supabase service key to the browser.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from loguru import logger

from src.services.db import db
from src.tools.properties.schemas import (
	PropertyType,
	ListingType,
	PricePeriod,
	SortBy,
	SortOrder,
	CreatePropertySchema,
)
from src.tools.properties import index_property

router = APIRouter(prefix="/api/properties", tags=["properties"])

security = HTTPBasic()


# ── Auth ────────────────────────────────────────────────────────────────────

def _verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
	"""Simple HTTP Basic auth check for property write endpoints.

	Uses PROPERTY_ADMIN_USER / PROPERTY_ADMIN_PASSWORD from environment.
	Falls back to 'admin' / 'changeme' if unset (change in production).
	"""
	expected_user = os.getenv("PROPERTY_ADMIN_USER", "admin")
	expected_pass = os.getenv("PROPERTY_ADMIN_PASSWORD", "changeme")

	correct = secrets.compare_digest(
		credentials.username + ":" + credentials.password,
		expected_user + ":" + expected_pass,
	)
	if not correct:
		raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
	return True


# ── Public: Search ──────────────────────────────────────────────────────────

@router.get("/", response_model=Dict[str, Any])
async def api_search_properties(
	location: Optional[str] = Query(default=None, description="Neighborhood or area filter"),
	town: Optional[str] = Query(default=None, description="Town / municipality filter"),
	city: Optional[str] = Query(default=None, description="City filter"),
	country: Optional[str] = Query(default=None, description="Country filter"),
	property_type: Optional[PropertyType] = Query(default=None, description="Property type filter"),
	listing_type: Optional[ListingType] = Query(default=None, description="Listing type filter"),
	price_period: Optional[PricePeriod] = Query(default=None, description="Price period filter"),
	property_subtype: Optional[str] = Query(default=None, description="Property subtype (e.g. 'duplex', 'bungalow')"),
	min_price: Optional[float] = Query(default=None, ge=0, description="Minimum price"),
	max_price: Optional[float] = Query(default=None, ge=0, description="Maximum price"),
	bedrooms: Optional[int] = Query(default=None, ge=0, description="Exact bedroom count"),
	min_bedrooms: Optional[int] = Query(default=None, ge=0, description="Minimum bedrooms"),
	min_sqm: Optional[float] = Query(default=None, ge=0, description="Minimum square meters"),
	max_sqm: Optional[float] = Query(default=None, ge=0, description="Maximum square meters"),
	min_lot_size_sqm: Optional[float] = Query(default=None, ge=0, description="Minimum land/plot size in sqm"),
	max_lot_size_sqm: Optional[float] = Query(default=None, ge=0, description="Maximum land/plot size in sqm"),
	amenities: Optional[List[str]] = Query(default=None, description="Required amenity feature tags (property must have ALL)"),
	furnished: Optional[bool] = Query(default=None, description="Furnished filter"),
	sort_by: SortBy = Query(default=SortBy.price),
	sort_order: SortOrder = Query(default=SortOrder.asc),
	limit: int = Query(default=50, ge=1, le=200, description="Results per page (max 200)"),
	offset: int = Query(default=0, ge=0, description="Results to skip"),
) -> Dict[str, Any]:
	"""Search available properties with structured filters and pagination.

	Returns a paginated list so large result sets (e.g. 500+ matches) can be
	browsed page-by-page without overwhelming the client. Property feature
	booleans are now folded into the `amenities` tag array — pass amenity tags
	(e.g. ``pool``, ``garden``, ``parking``) to filter by feature.
	"""
	filters: Dict[str, Any] = {
		"property_type": property_type.value if property_type else None,
		"listing_type": listing_type.value if listing_type else None,
		"price_period": price_period.value if price_period else None,
		"property_subtype": property_subtype,
		"min_price": min_price,
		"max_price": max_price,
		"bedrooms": bedrooms,
		"min_bedrooms": min_bedrooms,
		"min_sqm": min_sqm,
		"max_sqm": max_sqm,
		"min_lot_size_sqm": min_lot_size_sqm,
		"max_lot_size_sqm": max_lot_size_sqm,
		"location": location,
		"town": town,
		"city": city,
		"country": country,
		"amenities": amenities,
		"furnished": furnished,
		"sort_by": sort_by.value,
		"sort_order": sort_order.value,
		"limit": limit,
		"offset": offset,
	}
	# Drop None values so the db layer's defaults apply
	filters = {k: v for k, v in filters.items() if v is not None}

	try:
		# Attach ordered image galleries + agent profiles for each result.
		results = await db.search_properties_advanced(**filters, include_images=True)
	except Exception as exc:
		logger.exception("API property search failed: {}", exc)
		raise HTTPException(status_code=500, detail="Search failed")

	# Compute total available count for pagination navigation
	# Re-run without limit to get total (only if results filled the page)
	total = len(results)
	if total >= limit or offset > 0:
		try:
			count_filters = dict(filters)
			count_filters["limit"] = 10000
			count_filters["offset"] = 0
			# Best-effort count — omit the (now attached) image/agent data.
			count_filters.pop("include_images", None)
			total = len(await db.search_properties_advanced(**count_filters))
		except Exception:
			pass  # best-effort total; fall back to page length

	return {
		"total": total,
		"limit": limit,
		"offset": offset,
		"results": results,
	}


@router.get("/total", response_model=Dict[str, Any])
async def api_property_count(
	location: Optional[str] = Query(default=None),
	town: Optional[str] = Query(default=None),
	city: Optional[str] = Query(default=None),
	country: Optional[str] = Query(default=None),
	property_type: Optional[PropertyType] = Query(default=None),
	min_price: Optional[float] = Query(default=None, ge=0),
	max_price: Optional[float] = Query(default=None, ge=0),
	property_subtype: Optional[str] = Query(default=None),
	price_period: Optional[PricePeriod] = Query(default=None),
	bedrooms: Optional[int] = Query(default=None, ge=0),
) -> Dict[str, Any]:
	"""Return just the total count of matching available properties (for quick stats)."""
	filters: Dict[str, Any] = {
		"property_type": property_type.value if property_type else None,
		"listing_type": None,
		"price_period": price_period.value if price_period else None,
		"property_subtype": property_subtype,
		"location": location,
		"town": town,
		"city": city,
		"country": country,
		"min_price": min_price,
		"max_price": max_price,
		"bedrooms": bedrooms,
		"limit": 10000,
	}
	filters = {k: v for k, v in filters.items() if v is not None}
	try:
		count = len(await db.search_properties_advanced(**filters))
	except Exception:
		count = 0
	return {"count": count}


# ── Public: Get single property ─────────────────────────────────────────────

@router.get("/{property_id}", response_model=Dict[str, Any])
async def api_get_property(property_id: str) -> Dict[str, Any]:
	"""Retrieve full details for a single property by UUID.

	Includes the ordered image gallery (``images``) and the listing
	agent profile (``agent``) as joined relations.
	"""
	result = await db.get_property_full(property_id)
	if not result:
		raise HTTPException(status_code=404, detail="Property not found")
	return result


# ── Authenticated: Create / Update ──────────────────────────────────────────

@router.post("/", response_model=Dict[str, Any], status_code=201,
			 dependencies=[Depends(_verify_admin)])
async def api_create_property(payload: CreatePropertySchema) -> Dict[str, Any]:
	"""Create a new property listing. Requires admin authentication.

	The listing is upserted into Supabase and immediately indexed in Qdrant
	for semantic search. The listing agent (if provided) is find-or-created in
	the ``agents`` table and linked via ``agent_id``; the image gallery is
	stored in ``property_images``.
	"""
	data = payload.model_dump(exclude_none=True)

	# --- Agent (normalized into `agents`, linked by agent_id) ---
	agent_obj = data.pop("agent", None)
	agent_id = data.pop("agent_id", None)
	if agent_obj:
		agent_row = await db.upsert_agent(agent_obj)
		if agent_row:
			agent_id = str(agent_row.get("id"))
	if agent_id:
		data["agent_id"] = str(agent_id)

	# --- Images (stored in `property_images`, not on the property row) ---
	images = data.pop("images", None)

	prop_data = {k: v for k, v in data.items() if k not in {"agent", "agent_id"}}
	prop_data.update({"agent_id": agent_id} if agent_id else {})

	result = await db.upsert_property(
		prop_data,
		on_conflict="title,location,price,listing_type,property_type,price_period",
	)
	if not result:
		raise HTTPException(status_code=500, detail="Failed to create property")

	prop_id = str(result.get("id"))

	# Attach the image gallery (first image becomes featured if none flagged).
	if images:
		await db.add_property_images(prop_id, images)

	try:
		await index_property(prop_id)
	except Exception as exc:
		logger.warning("Qdrant indexing failed for new property {}: {}", prop_id, exc)

	logger.info("API: property created | id={} title='{}'", prop_id, prop_data.get("title"))
	return {"id": prop_id, "status": "created", "title": prop_data.get("title")}


# ── Authenticated: Delete ───────────────────────────────────────────────────

@router.delete("/{property_id}",
			   dependencies=[Depends(_verify_admin)])
async def api_delete_property(property_id: str) -> Dict[str, Any]:
	"""Delete a property listing. Requires admin authentication.

	Removes the property from both Supabase and the Qdrant vector index.
	Property images cascade-delete via the foreign key.
	"""
	success = await db.delete_property(property_id)  # now cleans Qdrant too
	if not success:
		raise HTTPException(status_code=404, detail="Property not found or already deleted")
	logger.info("API: property deleted | id={}", property_id)
	return {"id": property_id, "status": "deleted"}
