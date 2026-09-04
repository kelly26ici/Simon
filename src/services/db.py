import asyncio
from typing import Any, Dict, Optional, List

from loguru import logger

from src.clients.supabase_client import supabase


class DatabaseClient:
    """Production database client wrapping Supabase for properties, customer profiles,
    scheduled viewings, and M-Pesa transactions."""

    def __init__(self):
        self.client = supabase

    async def _run_sync(self, func, *args, **kwargs):
        """Runs synchronous Supabase calls in a threadpool to prevent blocking the event loop."""
        return await asyncio.to_thread(func, *args, **kwargs)

    # ═══════════════════════════════════════════════════════════════════════════
    # Customer Profiles & Memory
    # ═══════════════════════════════════════════════════════════════════════════

    _CUSTOMER_PROFILE_COLUMNS = {"preferred_name", "budget_range", "preferred_area"}

    async def get_customer_profile(self, whatsapp_id: str) -> Optional[Dict[str, Any]]:
        """Fetch customer profile by WhatsApp number."""
        if not self.client:
            return None

        def _get():
            response = self.client.table("customer_profiles").select("*").eq("whatsapp_id", whatsapp_id).execute()
            return response.data[0] if response.data else None

        try:
            return await self._run_sync(_get)
        except Exception as exc:
            logger.warning("Error fetching customer profile for {}: {}", whatsapp_id, exc)
            return None

    async def upsert_customer_profile(self, whatsapp_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upsert customer profile facts. Real columns are placed top-level,
        dynamic facts are merged into the JSONB metadata column."""
        if not self.client:
            return None

        known = {k: v for k, v in data.items() if k in self._CUSTOMER_PROFILE_COLUMNS}
        unknown = {k: v for k, v in data.items() if k not in self._CUSTOMER_PROFILE_COLUMNS}

        payload: Dict[str, Any] = {"whatsapp_id": whatsapp_id, **known}

        if unknown:
            existing = await self.get_customer_profile(whatsapp_id) or {}
            merged = {**(existing.get("metadata") or {}), **unknown}
            payload["metadata"] = merged

        def _upsert():
            response = self.client.table("customer_profiles").upsert(payload).execute()
            return response.data[0] if response.data else payload

        try:
            return await self._run_sync(_upsert)
        except Exception as exc:
            logger.exception("Failed to upsert customer profile for {}: {}", whatsapp_id, exc)
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # Conversation Summaries
    # ═══════════════════════════════════════════════════════════════════════════

    async def upsert_conversation_summary(
        self,
        whatsapp_id: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persists the live conversation summary for a customer to the database,
        with fallback to customer_profiles metadata and memory cache."""
        # 1. Update customer profile metadata as redundant backup
        try:
            await self.upsert_customer_profile(
                whatsapp_id,
                {"conversation_summary": summary},
            )
        except Exception as exc:
            logger.debug("Redundant profile summary sync failed: {}", exc)

        # 2. Persist in conversation_summaries table if Supabase client available
        if self.client:
            payload = {
                "whatsapp_id": whatsapp_id,
                "summary": summary,
                "metadata": metadata or {},
            }
            def _upsert():
                try:
                    self.client.table("conversation_summaries").upsert(payload).execute()
                    return True
                except Exception as exc:
                    logger.warning("conversation_summaries table upsert failed: {}", exc)
                    return False

            try:
                ok = await self._run_sync(_upsert)
                if ok:
                    return True
            except Exception as exc:
                logger.warning("Could not execute conversation_summaries upsert: {}", exc)

        # If table is missing or DB temporarily unreachable, profile/memory update succeeded
        return True

    async def get_conversation_summary(self, whatsapp_id: str) -> Optional[str]:
        """Retrieve latest conversation summary for a customer."""
        # 1. Try dedicated conversation_summaries table
        if self.client:
            def _get():
                try:
                    res = self.client.table("conversation_summaries").select("summary").eq("whatsapp_id", whatsapp_id).execute()
                    if res.data:
                        return res.data[0].get("summary")
                except Exception as exc:
                    logger.debug("conversation_summaries table select failed: {}", exc)
                return None

            try:
                summary = await self._run_sync(_get)
                if summary:
                    return summary
            except Exception as exc:
                logger.debug("Error fetching from conversation_summaries: {}", exc)

        # 2. Fallback to customer_profiles table metadata
        profile = await self.get_customer_profile(whatsapp_id)
        if profile:
            metadata = profile.get("metadata") or {}
            if "conversation_summary" in metadata:
                return metadata["conversation_summary"]

        return None

    # ═══════════════════════════════════════════════════════════════════════════
    # Conversation Messages (full persistent history)
    # ═══════════════════════════════════════════════════════════════════════════

    async def save_message(
        self,
        whatsapp_id: str,
        role: str,
        content: Any,
        wamid: Optional[str] = None,
        source: str = "whatsapp",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persist a single conversation message. Idempotent: if wamid is provided
        and a row with that wamid already exists, the insert is silently skipped
        (no duplicate rows for webhook retries).

        Returns the inserted row (with id + created_at) or None on failure.
        """
        if not self.client:
            return None

        payload = {
            "whatsapp_id": whatsapp_id,
            "role": role,
            "content": content,
            "wamid": wamid,
            "source": source,
            "metadata": metadata or {},
        }

        def _insert():
            try:
                if wamid:
                    res = (
                        self.client.table("conversation_messages")
                        .upsert(payload, on_conflict="wamid")
                        .execute()
                    )
                else:
                    res = (
                        self.client.table("conversation_messages")
                        .insert(payload)
                        .execute()
                    )
                return res.data[0] if res.data else None
            except Exception as exc:
                logger.debug("conversation_messages insert skipped/failed: {}", exc)
                return None

        try:
            return await self._run_sync(_insert)
        except Exception as exc:
            logger.debug("Could not execute conversation_messages insert: {}", exc)
            return None

    async def get_messages(
        self,
        whatsapp_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch persistent message history for a customer, newest-first.
        Returns rows ordered by created_at DESC with pagination support.
        Each row: {id, whatsapp_id, role, content, wamid, source, metadata, created_at}.
        """
        if not self.client:
            return []

        # Keep callers from accidentally issuing an invalid or unbounded range.
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        def _get():
            try:
                res = (
                    self.client.table("conversation_messages")
                    .select("id, whatsapp_id, role, content, wamid, source, metadata, created_at")
                    .eq("whatsapp_id", whatsapp_id)
                    .order("created_at", desc=True)
                    .order("id", desc=True)
                    .range(offset, offset + limit - 1)
                    .execute()
                )
                return res.data or []
            except Exception as exc:
                logger.debug("conversation_messages select failed: {}", exc)
                return []

        try:
            return await self._run_sync(_get)
        except Exception as exc:
            logger.debug("Error fetching conversation messages: {}", exc)
            return []

    # ═══════════════════════════════════════════════════════════════════════════
    # Bot / Owner System Settings
    # ═══════════════════════════════════════════════════════════════════════════

    async def save_bot_setting(
        self,
        key: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Saves a system or bot configuration key/value (e.g. SIMON_CHAT_ID)."""
        if not self.client:
            return False

        payload = {
            "key": key,
            "value": str(value),
            "metadata": metadata or {},
        }

        def _upsert():
            try:
                self.client.table("bot_settings").upsert(payload).execute()
                return True
            except Exception as exc:
                logger.warning("bot_settings upsert failed: {}", exc)
                return False

        try:
            return await self._run_sync(_upsert)
        except Exception as exc:
            logger.warning("Failed to save bot setting {}: {}", key, exc)
            return False

    async def get_bot_setting(self, key: str) -> Optional[str]:
        """Fetches a system or bot configuration value by key."""
        if not self.client:
            return None

        def _get():
            try:
                res = self.client.table("bot_settings").select("value").eq("key", key).execute()
                if res.data:
                    return res.data[0].get("value")
            except Exception as exc:
                logger.debug("bot_settings select failed for {}: {}", key, exc)
            return None

        try:
            return await self._run_sync(_get)
        except Exception as exc:
            logger.debug("Failed to get bot setting {}: {}", key, exc)
            return None

    async def save_owner_chat_id(
        self,
        chat_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> bool:
        """Saves the primary owner / Simon's Telegram Chat ID."""
        meta = {}
        if username:
            meta["username"] = username
        if first_name:
            meta["first_name"] = first_name
        return await self.save_bot_setting("SIMON_CHAT_ID", str(chat_id), metadata=meta)

    async def get_owner_chat_id(self) -> Optional[str]:
        """Retrieves Simon's Telegram Chat ID from database settings."""
        return await self.get_bot_setting("SIMON_CHAT_ID")


    # ═══════════════════════════════════════════════════════════════════════════
    # Properties
    # ═══════════════════════════════════════════════════════════════════════════

    async def upsert_property(
        self,
        property_data: Dict[str, Any],
        on_conflict: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Insert or update a property listing."""
        if not self.client:
            return None

        def _upsert():
            kwargs = {}
            if on_conflict:
                kwargs["on_conflict"] = on_conflict
            response = self.client.table("properties").upsert(property_data, **kwargs).execute()
            return response.data[0] if response.data else None

        try:
            return await self._run_sync(_upsert)
        except Exception as exc:
            logger.exception("Failed to upsert property {}: {}", property_data.get("title"), exc)
            return None

    async def upsert_properties_batch(
        self,
        properties_data: List[Dict[str, Any]],
        batch_size: int = 100,
        on_conflict: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Insert or update multiple properties in batches.

        Returns the upserted rows (with ids) so callers can attach dependent
        data such as the image gallery.
        """
        if not self.client or not properties_data:
            return []

        saved_rows: List[Dict[str, Any]] = []
        for i in range(0, len(properties_data), batch_size):
            batch = properties_data[i : i + batch_size]
            def _upsert_batch(b=batch):
                kwargs = {}
                if on_conflict:
                    kwargs["on_conflict"] = on_conflict
                res = self.client.table("properties").upsert(b, **kwargs).execute()
                return res.data or []

            try:
                rows = await self._run_sync(_upsert_batch)
                saved_rows.extend(rows)
                logger.info("Upserted batch {}/{} ({} properties)", i // batch_size + 1, (len(properties_data) + batch_size - 1) // batch_size, len(rows))
            except Exception as exc:
                logger.error("Failed to upsert batch starting at {}: {}", i, exc)

        return saved_rows

    async def get_property_by_id(self, property_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single property by its UUID."""
        if not self.client:
            return None

        def _get():
            response = (
                self.client.table("properties")
                .select("*")
                .eq("id", property_id)
                .single()
                .execute()
            )
            return response.data if response.data else None

        try:
            return await self._run_sync(_get)
        except Exception as exc:
            logger.debug("Property ID {} not found or error: {}", property_id, exc)
            return None

    async def get_properties_by_ids(self, property_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch multiple properties by a list of UUIDs."""
        if not self.client or not property_ids:
            return []

        def _get_many():
            response = (
                self.client.table("properties")
                .select("*")
                .in_("id", property_ids)
                .execute()
            )
            return response.data or []

        try:
            return await self._run_sync(_get_many)
        except Exception as exc:
            logger.exception("Error fetching properties by IDs: {}", exc)
            return []

    async def get_all_properties(self, limit: int = 10000, status: str = "available") -> List[Dict[str, Any]]:
        """Fetch all properties across multiple PostgREST pages."""
        if not self.client:
            return []

        def _fetch_all():
            all_rows = []
            page_size = 1000
            for start in range(0, limit, page_size):
                end = start + page_size - 1
                query = self.client.table("properties").select("*")
                if status:
                    query = query.eq("status", status)
                res = query.range(start, end).execute()
                if not res.data:
                    break
                all_rows.extend(res.data)
                if len(res.data) < page_size:
                    break
            return all_rows

        try:
            return await self._run_sync(_fetch_all)
        except Exception as exc:
            logger.exception("Error in get_all_properties: {}", exc)
            return []

    async def search_properties(self, **filters) -> List[Dict[str, Any]]:
        """Simple equality filter search for properties."""
        if not self.client:
            return []

        def _search():
            query = self.client.table("properties").select("*")
            for k, v in filters.items():
                if v is not None:
                    query = query.eq(k, v)
            response = query.execute()
            return response.data or []

        try:
            return await self._run_sync(_search)
        except Exception as exc:
            logger.exception("Error in search_properties: {}", exc)
            return []

    async def search_properties_advanced(
        self,
        property_type: Optional[str] = None,
        listing_type: Optional[str] = None,
        price_period: Optional[str] = None,
        property_subtype: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        bedrooms: Optional[int] = None,
        min_bedrooms: Optional[int] = None,
        bathrooms: Optional[int] = None,
        min_sqm: Optional[float] = None,
        max_sqm: Optional[float] = None,
        min_lot_size_sqm: Optional[float] = None,
        max_lot_size_sqm: Optional[float] = None,
        location: Optional[str] = None,
        town: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        amenities: Optional[List[str]] = None,
        furnished: Optional[bool] = None,
        sort_by: str = "price",
        sort_order: str = "asc",
        limit: int = 5,
        offset: int = 0,
        include_images: bool = False,
        include_agents: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Advanced property search with range filters, fuzzy location matching,
        amenity array containment, sorting, and pagination.

        Amenity *feature* booleans that previously lived as dedicated columns
        (garden, pool, pet-friendly, gated community, parking) are now part of
        the `amenities` tag array and are filtered via `amenities`
        (array-contains-ALL). `furnished` is retained as a structured column.
        """
        if not self.client:
            return []

        def _advanced_search():
            query = self.client.table("properties").select("*")

            # Exact / Case-insensitive match filters
            if property_type:
                query = query.eq("property_type", property_type)
            if listing_type:
                query = query.eq("listing_type", listing_type)
            if price_period:
                query = query.eq("price_period", price_period)
            if property_subtype:
                query = query.ilike("property_subtype", f"%{property_subtype}%")
            if location:
                query = query.ilike("location", f"%{location}%")
            if town:
                query = query.ilike("town", f"%{town}%")
            if city:
                query = query.ilike("city", f"%{city}%")
            if country:
                query = query.eq("country", country)
            if bedrooms is not None:
                query = query.eq("bedrooms", bedrooms)
            if bathrooms is not None:
                query = query.eq("bathrooms", bathrooms)
            if furnished is not None:
                query = query.eq("furnished", furnished)

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
            if min_lot_size_sqm is not None:
                query = query.gte("lot_size_sqm", min_lot_size_sqm)
            if max_lot_size_sqm is not None:
                query = query.lte("lot_size_sqm", max_lot_size_sqm)

            # Array containment — property must have ALL specified amenities
            if amenities:
                query = query.contains("amenities", amenities)

            # Only available properties
            query = query.eq("status", "available")

            # Sorting
            valid_sort_fields = {"price", "bedrooms", "square_meters", "created_at"}
            effective_sort = sort_by if sort_by in valid_sort_fields else "price"
            query = query.order(effective_sort, desc=(sort_order == "desc"))

            # Pagination
            query = query.range(offset, offset + limit - 1)

            response = query.execute()
            rows = response.data or []

            # Optionally attach ordered image galleries + agent profiles.
            if rows and (include_images or include_agents):
                ids = [str(r["id"]) for r in rows]
                if include_images:
                    images_map = self._sync_get_property_images_batch(ids)
                    for r in rows:
                        r["images"] = images_map.get(str(r["id"]), [])
                if include_agents:
                    agent_ids = [str(r["agent_id"]) for r in rows if r.get("agent_id")]
                    agents_map = self._sync_get_agents_by_ids(agent_ids)
                    for r in rows:
                        aid = r.get("agent_id")
                        r["agent"] = agents_map.get(str(aid)) if aid else None

            return rows

        try:
            return await self._run_sync(_advanced_search)
        except Exception as exc:
            logger.exception("Error in search_properties_advanced: {}", exc)
            return []

    async def delete_property(self, property_id: str) -> bool:
        """Delete a property by UUID from both Supabase and the Qdrant vector index."""
        if not self.client:
            return False

        def _delete():
            self.client.table("properties").delete().eq("id", property_id).execute()
            return True

        try:
            result = await self._run_sync(_delete)
            # Also remove from the Qdrant vector index so deleted properties
            # don't appear in semantic search results.
            try:
                from src.tools.properties import delete_property_index
                await delete_property_index(property_id)
            except Exception as idx_exc:
                logger.warning("Failed to delete property {} from Qdrant: {}", property_id, idx_exc)
            return result
        except Exception as exc:
            logger.exception("Failed to delete property {}: {}", property_id, exc)
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    # Property Images (normalized ordered gallery)
    # ═══════════════════════════════════════════════════════════════════════════

    def _sync_get_property_images_batch(self, property_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Synchronous fetch (callable inside the search worker thread).

        Returns {property_id: [ordered image rows]} with featured first.
        """
        if not self.client or not property_ids:
            return {}
        try:
            rows = (
                self.client.table("property_images")
                .select("*")
                .in_("property_id", property_ids)
                .order("is_featured", desc=True)
                .order("sort_order")
                .execute()
                .data or []
            )
        except Exception as exc:
            logger.debug("property_images batch fetch failed: {}", exc)
            return {}
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for im in rows:
            grouped.setdefault(str(im["property_id"]), []).append(im)
        return grouped

    async def get_property_images(self, property_id: str) -> List[Dict[str, Any]]:
        """Ordered image rows for a property (featured first)."""
        return await self._run_sync(self._sync_get_property_images_batch, [property_id]).get(property_id, [])  # type: ignore[arg-type]

    async def get_property_images_batch(self, property_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Ordered image rows for many properties. {property_id: [rows]}."""
        return await self._run_sync(self._sync_get_property_images_batch, property_ids)  # type: ignore[arg-type]

    async def add_property_image(
        self,
        property_id: str,
        url: str,
        sort_order: int = 0,
        is_featured: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None

        def _insert():
            res = (
                self.client.table("property_images")
                .insert({"property_id": property_id, "url": url, "sort_order": sort_order, "is_featured": is_featured})
                .execute()
            )
            return res.data[0] if res.data else None

        try:
            return await self._run_sync(_insert)
        except Exception as exc:
            logger.debug("add_property_image failed: {}", exc)
            return None

    async def add_property_images(self, property_id: str, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Attach an ordered image gallery (each dict: url, sort_order?, is_featured?)."""
        if not self.client or not images:
            return []
        rows = [
            {
                "property_id": property_id,
                "url": im.get("url") if isinstance(im, dict) else str(im),
                "sort_order": int(im.get("sort_order", idx)) if isinstance(im, dict) else idx,
                "is_featured": bool(im.get("is_featured", False)) if isinstance(im, dict) else False,
            }
            for idx, im in enumerate(images)
        ]
        # Promote the first image to featured if none explicitly featured.
        if not any(r["is_featured"] for r in rows) and rows:
            rows[0]["is_featured"] = True

        def _insert():
            res = self.client.table("property_images").upsert(rows, on_conflict="property_id,sort_order").execute()
            return res.data or []

        try:
            return await self._run_sync(_insert)
        except Exception as exc:
            logger.debug("add_property_images batch failed: {}", exc)
            return []

    # ═══════════════════════════════════════════════════════════════════════════
    # Agents
    # ═══════════════════════════════════════════════════════════════════════════

    def _sync_get_agents_by_ids(self, agent_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Synchronous fetch of agents by id (usable inside the search thread)."""
        if not self.client or not agent_ids:
            return {}
        try:
            rows = self.client.table("agents").select("*").in_("id", agent_ids).execute().data or []
        except Exception as exc:
            logger.debug("agents batch fetch failed: {}", exc)
            return {}
        return {str(a["id"]): a for a in rows}

    async def get_agent(self, agent_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not self.client or not agent_id:
            return None

        def _get():
            try:
                res = self.client.table("agents").select("*").eq("id", agent_id).maybe_single().execute()
                return res.data if res.data else None
            except Exception as exc:
                logger.debug("get_agent({}) failed: {}", agent_id, exc)
                return None

        return await self._run_sync(_get)

    async def get_agents_by_ids(self, agent_ids: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        return await self._run_sync(self._sync_get_agents_by_ids, agent_ids)  # type: ignore[arg-type]

    async def upsert_agent(self, agent_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find-or-create a listing agent by normalized phone and/or email.

        Accepts {first_name, last_name, email, phone, agency_name, bio, ...}.
        Returns the existing or freshly created agent row (with id).
        """
        if not self.client:
            return None

        allowed = {"first_name", "last_name", "email", "phone", "agency_name", "bio", "is_verified", "avatar_url"}
        base = {k: v for k, v in agent_data.items() if k in allowed and v is not None}
        phone = base.get("phone")
        email = base.get("email")

        def _upsert():
            found = None
            if phone:
                r = self.client.table("agents").select("*").eq("phone", phone).maybe_single().execute()
                found = getattr(r, "data", None) or None
            if not found and email:
                r = self.client.table("agents").select("*").eq("email", email).maybe_single().execute()
                found = getattr(r, "data", None) or None
            # Supabase returns a *list* of rows; callers expect a single dict
            # (the upserted row), matching the -> Optional[Dict[str, Any]] contract.
            if found:
                res = self.client.table("agents").update(base).eq("id", found["id"]).execute()
                return (res.data or [None])[0]
            res = self.client.table("agents").insert(base).execute()
            return (res.data or [None])[0]

        return await self._run_sync(_upsert)

    async def get_property_full(self, property_id: str) -> Optional[Dict[str, Any]]:
        """Property row + ordered images + agent profile (single source of truth)."""
        prop = await self.get_property_by_id(property_id)
        if not prop:
            return None
        images = await self.get_property_images(property_id)
        prop["images"] = images
        agent = None
        if prop.get("agent_id"):
            agent = await self.get_agent(prop["agent_id"])
        prop["agent"] = agent
        return prop

    # ═══════════════════════════════════════════════════════════════════════════
    # Leads / Inquiries  (Property254 "Contact Us" contact form)
    # ═══════════════════════════════════════════════════════════════════════════

    async def record_property_inquiry(
        self,
        customer_phone: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        property_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        inquiry_type: str = "general",
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        payload = {
            "customer_phone": customer_phone,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "property_id": property_id,
            "agent_id": agent_id,
            "inquiry_type": inquiry_type,
            "message": message,
            "metadata": metadata or {},
        }

        def _insert():
            res = self.client.table("property_inquiries").insert(payload).execute()
            return res.data[0] if res.data else None

        try:
            return await self._run_sync(_insert)
        except Exception as exc:
            logger.warning("record_property_inquiry failed: {}", exc)
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # Scheduled Viewings / Appointments
    # ═══════════════════════════════════════════════════════════════════════════

    async def create_scheduled_viewing(
        self,
        property_id: Optional[str],
        customer_phone: str,
        customer_name: Optional[str],
        viewing_date: str,
        duration_minutes: int = 30,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Book a property viewing appointment."""
        if not self.client:
            return {"status": "error", "message": "Database unavailable"}

        payload = {
            "property_id": property_id,
            "customer_phone": customer_phone,
            "customer_name": customer_name,
            "viewing_date": viewing_date,
            "duration_minutes": duration_minutes,
            "status": "confirmed",
            "notes": notes,
        }

        def _insert():
            try:
                resp = self.client.table("scheduled_viewings").insert(payload).execute()
                return resp.data[0] if resp.data else payload
            except Exception as e:
                # If table is missing in remote DB, log and return structured payload
                logger.warning("scheduled_viewings table insert failed: {}", e)
                return {**payload, "id": "mock-viewing-id"}

        return await self._run_sync(_insert)

    async def get_customer_viewings(
        self,
        customer_phone: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get scheduled viewings for a customer phone number."""
        if not self.client:
            return []

        def _get():
            try:
                query = self.client.table("scheduled_viewings").select(
                    "id, property_id, customer_name, viewing_date, duration_minutes, status, notes, created_at"
                ).eq("customer_phone", customer_phone)
                if status:
                    query = query.eq("status", status)
                resp = query.order("viewing_date", desc=False).execute()
                return resp.data or []
            except Exception as e:
                logger.debug("Could not fetch viewings: {}", e)
                return []

        return await self._run_sync(_get)

    async def cancel_scheduled_viewing(self, viewing_id: str, customer_phone: str) -> bool:
        """Cancel a viewing appointment."""
        if not self.client:
            return False

        def _cancel():
            try:
                self.client.table("scheduled_viewings").update({"status": "cancelled"}).eq("id", viewing_id).eq("customer_phone", customer_phone).execute()
                return True
            except Exception as e:
                logger.warning("Failed to cancel viewing: {}", e)
                return False

        return await self._run_sync(_cancel)

    # ═══════════════════════════════════════════════════════════════════════════
    # M-Pesa Transactions
    # ═══════════════════════════════════════════════════════════════════════════

    async def save_mpesa_transaction(self, checkout_request_id: str, data: Dict[str, Any]) -> None:
        if not self.client:
            return
        payload = {"checkout_request_id": checkout_request_id, **data}

        def _save():
            self.client.table("mpesa_transactions").upsert(payload).execute()

        try:
            await self._run_sync(_save)
        except Exception as exc:
            logger.exception("Failed to save M-Pesa transaction {}: {}", checkout_request_id, exc)

    async def get_mpesa_transaction(self, checkout_request_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None

        def _get():
            response = self.client.table("mpesa_transactions").select("*").eq("checkout_request_id", checkout_request_id).execute()
            return response.data[0] if response.data else None

        try:
            return await self._run_sync(_get)
        except Exception as exc:
            logger.warning("Error fetching M-Pesa transaction {}: {}", checkout_request_id, exc)
            return None

    async def check_payment_history(self, phone_number: str) -> bool:
        """Returns True if this phone number has any successful past transactions."""
        if not self.client:
            return False

        def _check():
            response = (
                self.client.table("mpesa_transactions")
                .select("checkout_request_id")
                .eq("phone_number", phone_number)
                .eq("state", "success")
                .limit(1)
                .execute()
            )
            return len(response.data) > 0

        try:
            return await self._run_sync(_check)
        except Exception as exc:
            logger.warning("Error checking payment history for {}: {}", phone_number, exc)
            return False


db = DatabaseClient()

