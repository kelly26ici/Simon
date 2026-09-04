"""
Pydantic schemas for the property search tools.

Mirrors the Property254-compatible data model defined in SQl/schema.sql:
listing purpose (sale | rent), price period (one_time | per_month | per_night),
structured location (neighborhood / address / town / city / county / country),
residential attributes (bedrooms, bathrooms, square_meters, lot_size_sqm),
amenity feature tags, structured `furnished` flag, normalized agent + image
gallery, and a price/size/bedroom search contract.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class PropertyType(str, Enum):
	house = "house"
	apartment = "apartment"
	land = "land"
	commercial = "commercial"
	townhouse = "townhouse"
	villa = "villa"
	cottage = "cottage"
	penthouse = "penthouse"
	studio = "studio"


class ListingType(str, Enum):
	sale = "sale"
	rent = "rent"


class PricePeriod(str, Enum):
	"""How a listing's price is charged (Property254: KES price + period)."""
	one_time = "one_time"     # For Buy — fixed purchase price
	per_month = "per_month"   # For Rent / To Let — monthly rent
	per_night = "per_night"   # short-stay / Airbnb


class SortBy(str, Enum):
	price = "price"
	bedrooms = "bedrooms"
	square_meters = "square_meters"
	created_at = "created_at"


class SortOrder(str, Enum):
	asc = "asc"
	desc = "desc"


# ── Reusable sub-models ──────────────────────────────────────────────────────

class AgentSchema(BaseModel):
	"""A listing agent / agency profile (normalized agents table)."""
	first_name: str = Field(..., min_length=1, description="Agent first name")
	last_name: Optional[str] = Field(default=None, description="Agent last name")
	email: Optional[str] = Field(default=None, description="Agent email")
	phone: Optional[str] = Field(default=None, description="Agent phone (any format)")
	agency_name: Optional[str] = Field(default=None, description="Agency / business name")
	bio: Optional[str] = Field(default=None, description="Agent profile bio")
	is_verified: Optional[bool] = Field(default=False, description="Verified badge")
	avatar_url: Optional[str] = Field(default=None, description="Profile photo URL")


class ImageSpec(BaseModel):
	"""One image in a property gallery."""
	url: str = Field(..., description="Image URL")
	sort_order: Optional[int] = Field(default=None, description="Display order; defaults to list position")
	is_featured: Optional[bool] = Field(default=False, description="Primary / featured image")


# ── Tool 1: Structured Search ────────────────────────────────────────────────

class SearchPropertiesSchema(BaseModel):
	"""Input for the search_properties tool — structured filter-based search."""

	property_type: Optional[PropertyType] = Field(default=None, description="Filter by property type")
	listing_type: Optional[ListingType] = Field(default=None, description="Filter by listing type: sale or rent")
	price_period: Optional[PricePeriod] = Field(default=None, description="Filter by price period (sale=one_time, rent=per_month, short-stay=per_night)")
	property_subtype: Optional[str] = Field(default=None, description="Filter by subtype (e.g. 'duplex', 'bungalow', 'maisonette')")
	min_price: Optional[float] = Field(default=None, ge=0, description="Minimum price in KES")
	max_price: Optional[float] = Field(default=None, ge=0, description="Maximum price in KES")
	bedrooms: Optional[int] = Field(default=None, ge=0, description="Exact number of bedrooms required")
	min_bedrooms: Optional[int] = Field(default=None, ge=0, description="Minimum number of bedrooms")
	bathrooms: Optional[int] = Field(default=None, ge=0, description="Exact number of bathrooms required")
	min_sqm: Optional[float] = Field(default=None, ge=0, description="Minimum floor area in sqm")
	max_sqm: Optional[float] = Field(default=None, ge=0, description="Maximum floor area in sqm")
	min_lot_size_sqm: Optional[float] = Field(default=None, ge=0, description="Minimum land/plot size in sqm")
	max_lot_size_sqm: Optional[float] = Field(default=None, ge=0, description="Maximum land/plot size in sqm")
	location: Optional[str] = Field(default=None, description="Neighborhood or area (e.g. 'Kilimani', 'Westlands')")
	town: Optional[str] = Field(default=None, description="Town / municipality filter")
	city: Optional[str] = Field(default=None, description="City name (e.g. 'Nairobi', 'Mombasa')")
	country: Optional[str] = Field(default=None, description="Country filter (e.g. 'Kenya')")
	amenities: Optional[List[str]] = Field(default=None, description="Required amenity feature tags (e.g. ['pool','gym','parking']); property must have ALL")
	furnished: Optional[bool] = Field(default=None, description="Filter by furnished status")
	sort_by: SortBy = Field(default=SortBy.price, description="Field to sort results by")
	sort_order: SortOrder = Field(default=SortOrder.asc, description="Sort direction")
	limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results to return")
	offset: int = Field(default=0, ge=0, description="Number of results to skip (for pagination)")


# ── Tool 2: Semantic Search ──────────────────────────────────────────────────

class SemanticSearchSchema(BaseModel):
	"""Input for the semantic_search_properties tool — natural language search."""

	query: str = Field(
		...,
		min_length=3,
		description="Natural language description of what the customer is looking for. "
					"Be descriptive — include preferences about location, style, features, "
					"and lifestyle. E.g. 'modern 3-bedroom apartment in a quiet neighborhood "
					"with a garden, close to schools and shopping'",
	)
	limit: int = Field(default=5, ge=1, le=20, description="Maximum number of results to return")
	min_price: Optional[float] = Field(default=None, ge=0, description="Optional minimum price filter in KES")
	max_price: Optional[float] = Field(default=None, ge=0, description="Optional maximum price filter in KES")
	location: Optional[str] = Field(default=None, description="Optional neighborhood or area filter")
	city: Optional[str] = Field(default=None, description="Optional city filter")
	property_type: Optional[PropertyType] = Field(default=None, description="Optional property type filter")
	listing_type: Optional[ListingType] = Field(default=None, description="Optional listing type filter (sale/rent)")
	price_period: Optional[PricePeriod] = Field(default=None, description="Optional price-period filter")
	property_subtype: Optional[str] = Field(default=None, description="Optional property subtype filter")
	bedrooms: Optional[int] = Field(default=None, ge=0, description="Optional exact bedroom count filter")
	town: Optional[str] = Field(default=None, description="Optional town filter")
	country: Optional[str] = Field(default=None, description="Optional country filter (e.g. 'Kenya')")


# ── Tool 3: Property Details ─────────────────────────────────────────────────

class GetPropertyDetailsSchema(BaseModel):
	"""Input for the get_property_details tool."""

	property_id: str = Field(
		...,
		description="The unique UUID of the property to retrieve complete details, images, and contact for.",
	)


# ── Tool 5: Create / Update Property ─────────────────────────────────────────

class CreatePropertySchema(BaseModel):
	"""Input for the create_property tool — create or update a property listing."""

	title: str = Field(..., min_length=3, description="Property listing title")
	description: str = Field(..., min_length=10, description="Full property description")
	property_type: PropertyType = Field(..., description="Type of property")
	property_subtype: Optional[str] = Field(default=None, description="Subtype e.g. 'duplex', 'bungalow', 'maisonette'")
	listing_type: ListingType = Field(..., description="Sale or rent")
	price_period: PricePeriod = Field(default=PricePeriod.one_time, description="one_time (sale), per_month (rent), per_night (short-stay)")
	price: float = Field(..., gt=0, description="Listing price in KES (must be positive)")
	currency: str = Field(default="KES", description="Currency code")
	bedrooms: Optional[int] = Field(default=None, ge=0, description="Number of bedrooms")
	bathrooms: Optional[int] = Field(default=None, ge=0, description="Number of bathrooms")
	square_meters: Optional[float] = Field(default=None, gt=0, description="Floor area in sqm")
	lot_size_sqm: Optional[float] = Field(default=None, gt=0, description="Land/plot size in sqm")
	plot_dimensions: Optional[str] = Field(default=None, description="Raw plot dimensions, e.g. '50 x 100'")
	land_size_raw: Optional[str] = Field(default=None, description="Raw land size text, e.g. '1/4 acre'")
	year_built: Optional[int] = Field(default=None, ge=1900, le=2100, description="Year built")
	floor_number: Optional[int] = Field(default=None, description="Floor number (for apartments)")
	total_floors: Optional[int] = Field(default=None, description="Total floors in the building")
	# Location
	location: str = Field(..., min_length=2, description="Neighborhood or area (e.g. 'Kilimani')")
	address: Optional[str] = Field(default=None, description="Road / street address")
	town: Optional[str] = Field(default=None, description="Town / municipality")
	city: str = Field(default="Nairobi", description="City name")
	county: Optional[str] = Field(default=None, description="County name")
	country: str = Field(default="Kenya", description="Country name")
	latitude: Optional[float] = Field(default=None, description="Map latitude")
	longitude: Optional[float] = Field(default=None, description="Map longitude")
	# Features
	amenities: Optional[List[str]] = Field(default=None, description="Amenity feature tags (e.g. ['swimming_pool','garden','parking'])")
	furnished: Optional[bool] = Field(default=False, description="Whether the property is furnished")
	# Media
	images: Optional[List[ImageSpec]] = Field(default=None, description="Ordered image gallery; first/featured image rendered as primary")
	video_url: Optional[str] = Field(default=None, description="Property video tour URL")
	# Agent (normalized)
	agent: Optional[AgentSchema] = Field(default=None, description="Listing agent to link (find-or-create by phone/email)")
	agent_id: Optional[str] = Field(default=None, description="Existing agent UUID to link instead of the `agent` object")
	# Metadata
	source: Optional[str] = Field(default=None, description="Where the listing came from")
	status: Optional[str] = Field(default="available", description="Listing status")


class ComparePropertiesSchema(BaseModel):
	"""Input for the compare_properties tool — side-by-side comparison."""

	property_ids: List[str] = Field(
		...,
		min_length=2,
		max_length=4,
		description="List of 2-4 property UUIDs to compare. Get these IDs from "
					"search_properties or semantic_search_properties results.",
	)
