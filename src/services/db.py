from typing import Any, Dict, Optional, List

from loguru import logger

from src.clients.supabase_client import supabase


class DatabaseClient:
    def __init__(self):
        self.client = supabase

    # --- Customer Profiles ---
    async def get_customer_profile(self, whatsapp_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        response = await self.client.table("customer_profiles").select("*").eq("whatsapp_id", whatsapp_id).execute()
        return response.data[0] if response.data else None

    async def upsert_customer_profile(self, whatsapp_id: str, data: Dict[str, Any]) -> None:
        if not self.client:
            return
        payload = {"whatsapp_id": whatsapp_id, **data}
        await self.client.table("customer_profiles").upsert(payload).execute()

    # --- Mpesa Transactions ---
    async def save_mpesa_transaction(self, checkout_request_id: str, data: Dict[str, Any]) -> None:
        if not self.client:
            return
        payload = {"checkout_request_id": checkout_request_id, **data}
        await self.client.table("mpesa_transactions").upsert(payload).execute()

    async def get_mpesa_transaction(self, checkout_request_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        response = await self.client.table("mpesa_transactions").select("*").eq("checkout_request_id", checkout_request_id).execute()
        return response.data[0] if response.data else None

    async def check_payment_history(self, phone_number: str) -> bool:
        """Returns True if this phone number has any successful past transactions."""
        if not self.client:
            return False
        response = (
            await self.client.table("mpesa_transactions")
            .select("checkout_request_id")
            .eq("phone_number", phone_number)
            .eq("state", "success")
            .limit(1)
            .execute()
        )
        return len(response.data) > 0

    # --- Properties ---
    async def upsert_property(self, property_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Insert or update a property. If 'id' is not provided, Supabase generates one."""
        if not self.client:
            return None
        response = await self.client.table("properties").upsert(property_data).execute()
        return response.data[0] if response.data else None

    async def search_properties(self, **filters) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        query = self.client.table("properties").select("*")
        for k, v in filters.items():
            if v is not None:
                query = query.eq(k, v)
        response = await query.execute()
        return response.data

    async def get_property_by_id(self, property_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single property by its UUID."""
        if not self.client:
            return None
        response = (
            await self.client.table("properties")
            .select("*")
            .eq("id", property_id)
            .single()
            .execute()
        )
        return response.data if response.data else None

    async def search_properties_advanced(
        self,
        property_type: Optional[str] = None,
        listing_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        bedrooms: Optional[int] = None,
        min_bedrooms: Optional[int] = None,
        bathrooms: Optional[int] = None,
        min_sqm: Optional[float] = None,
        max_sqm: Optional[float] = None,
        location: Optional[str] = None,
        city: Optional[str] = None,
        amenities: Optional[List[str]] = None,
        furnished: Optional[bool] = None,
        pet_friendly: Optional[bool] = None,
        gated_community: Optional[bool] = None,
        sort_by: str = "price",
        sort_order: str = "asc",
        limit: int = 5,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Advanced property search with range filters, sorting, and pagination.

        Uses Supabase's filter DSL for range queries (gte/lte) and
        array containment (contains) for amenities.
        """
        if not self.client:
            return []

        query = self.client.table("properties").select("*")

        # Exact-match filters
        if property_type:
            query = query.eq("property_type", property_type)
        if listing_type:
            query = query.eq("listing_type", listing_type)
        if location:
            query = query.ilike("location", f"%{location}%")
        if city:
            query = query.ilike("city", f"%{city}%")
        if bedrooms is not None:
            query = query.eq("bedrooms", bedrooms)
        if bathrooms is not None:
            query = query.eq("bathrooms", bathrooms)
        if furnished is not None:
            query = query.eq("furnished", furnished)
        if pet_friendly is not None:
            query = query.eq("pet_friendly", pet_friendly)
        if gated_community is not None:
            query = query.eq("gated_community", gated_community)

        # Range filters
        if min_price is not None:
            query = query.gte("price", min_price)
        if max_price is not None:
            query = query.lte("price", max_price)
        if min_bedrooms is not None:
            query = query.gte("bedrooms", min_bedrooms)
        if min_sqm is not None:
            query = query.gte("square_meters", min_sqm)
        if max_sqm is not None:
            query = query.lte("square_meters", max_sqm)

        # Array containment — property must have ALL specified amenities
        if amenities:
            query = query.contains("amenities", amenities)

        # Only show available properties by default
        query = query.eq("status", "available")

        # Sorting
        order = "desc" if sort_order == "desc" else "asc"
        query = query.order(sort_by, desc=(sort_order == "desc"))

        # Pagination
        query = query.range(offset, offset + limit - 1)

        response = await query.execute()
        return response.data


db = DatabaseClient()
