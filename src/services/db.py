from typing import Any, Dict, Optional, List
from src.clients.supabase_client import supabase

class DatabaseClient:
    def __init__(self):
        self.client = supabase

    # --- Customer Profiles ---
    async def get_customer_profile(self, whatsapp_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        response = self.client.table("customer_profiles").select("*").eq("whatsapp_id", whatsapp_id).execute()
        return response.data[0] if response.data else None

    async def upsert_customer_profile(self, whatsapp_id: str, data: Dict[str, Any]) -> None:
        if not self.client:
            return
        payload = {"whatsapp_id": whatsapp_id, **data}
        self.client.table("customer_profiles").upsert(payload).execute()

    # --- Mpesa Transactions ---
    async def save_mpesa_transaction(self, checkout_request_id: str, data: Dict[str, Any]) -> None:
        if not self.client:
            return
        payload = {"checkout_request_id": checkout_request_id, **data}
        self.client.table("mpesa_transactions").upsert(payload).execute()

    async def get_mpesa_transaction(self, checkout_request_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        response = self.client.table("mpesa_transactions").select("*").eq("checkout_request_id", checkout_request_id).execute()
        return response.data[0] if response.data else None

    async def check_payment_history(self, phone_number: str) -> bool:
        """Returns True if this phone number has any successful past transactions."""
        if not self.client:
            return False
        response = (
            self.client.table("mpesa_transactions")
            .select("checkout_request_id")
            .eq("phone_number", phone_number)
            .eq("state", "success")
            .limit(1)
            .execute()
        )
        return len(response.data) > 0

    # --- Properties ---
    async def search_properties(self, **filters) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        query = self.client.table("properties").select("*")
        for k, v in filters.items():
            if v is not None:
                query = query.eq(k, v)
        response = query.execute()
        return response.data

db = DatabaseClient()
