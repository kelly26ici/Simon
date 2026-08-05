"""
Pydantic schemas for the property search tools.
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


class SortBy(str, Enum):
    price = "price"
    bedrooms = "bedrooms"
    square_meters = "square_meters"
    created_at = "created_at"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


# ── Tool 1: Structured Search ────────────────────────────────────────────────

class SearchPropertiesSchema(BaseModel):
    """Input for the search_properties tool — structured filter-based search."""

    property_type: Optional[PropertyType] = Field(
        default=None,
        description="Filter by property type (house, apartment, land, etc.)",
    )
    listing_type: Optional[ListingType] = Field(
        default=None,
        description="Filter by listing type: sale or rent",
    )
    min_price: Optional[float] = Field(
        default=None,
        ge=0,
        description="Minimum price in KES",
    )
    max_price: Optional[float] = Field(
        default=None,
        ge=0,
        description="Maximum price in KES",
    )
    bedrooms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Exact number of bedrooms required",
    )
    min_bedrooms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Minimum number of bedrooms",
    )
    bathrooms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Exact number of bathrooms required",
    )
    min_sqm: Optional[float] = Field(
        default=None,
        ge=0,
        description="Minimum square meters",
    )
    max_sqm: Optional[float] = Field(
        default=None,
        ge=0,
        description="Maximum square meters",
    )
    location: Optional[str] = Field(
        default=None,
        description="Neighborhood or area (e.g. 'Kilimani', 'Westlands')",
    )
    city: Optional[str] = Field(
        default=None,
        description="City name (e.g. 'Nairobi', 'Mombasa')",
    )
    amenities: Optional[List[str]] = Field(
        default=None,
        description="Required amenities (e.g. ['pool', 'gym', 'parking'])",
    )
    furnished: Optional[bool] = Field(
        default=None,
        description="Filter by furnished status",
    )
    pet_friendly: Optional[bool] = Field(
        default=None,
        description="Filter by pet-friendly status",
    )
    gated_community: Optional[bool] = Field(
        default=None,
        description="Filter by gated community status",
    )
    sort_by: SortBy = Field(
        default=SortBy.price,
        description="Field to sort results by",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.asc,
        description="Sort direction",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip (for pagination)",
    )


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
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return",
    )
    min_price: Optional[float] = Field(
        default=None,
        ge=0,
        description="Optional minimum price filter in KES",
    )
    max_price: Optional[float] = Field(
        default=None,
        ge=0,
        description="Optional maximum price filter in KES",
    )
    city: Optional[str] = Field(
        default=None,
        description="Optional city filter",
    )
    property_type: Optional[PropertyType] = Field(
        default=None,
        description="Optional property type filter",
    )
    listing_type: Optional[ListingType] = Field(
        default=None,
        description="Optional listing type filter (sale/rent)",
    )


# ── Tool 3: Property Comparison ──────────────────────────────────────────────

class ComparePropertiesSchema(BaseModel):
    """Input for the compare_properties tool — side-by-side comparison."""

    property_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="List of 2-4 property UUIDs to compare. Get these IDs from "
                    "search_properties or semantic_search_properties results.",
    )