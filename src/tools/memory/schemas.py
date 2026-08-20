from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

# Suggested field names the model should prefer, kept here as the documented
# contract with the prompt. We accept any snake_case string so the model is never
# forced to drop a sensible fact (e.g. `preferred_city`, `preferred_bedrooms`)
# just because it wasn't on a hardcoded allowlist — the underlying customer_profiles
# table is a free-form JSON-ish row, so unknown fields are stored as-is.
SUGGESTED_CUSTOMER_FIELDS = {
    "preferred_name",
    "budget_range",
    "preferred_area",
}


class SaveCustomerFactSchema(BaseModel):
    """Input for save_customer_fact tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number")
    field: Optional[str] = Field(
        default=None,
        description=(
            "The profile field to update (snake_case). Suggested fields: "
            "preferred_name, budget_range, preferred_area — but any descriptive "
            "snake_case field is accepted."
        ),
    )
    value: Optional[str] = Field(default=None, description="The value to save for this field")
    fact_key: Optional[str] = Field(default=None, description="Alternative key name for field")
    fact_value: Optional[str] = Field(default=None, description="Alternative value name for value")

    def get_field_and_value(self) -> tuple[str, str]:
        f = self.field or self.fact_key or "general"
        v = self.value or self.fact_value or ""
        return f, v

class FlagForSummarySchema(BaseModel):
    """Input for flag_for_summary tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number to flag for summarization")

class CheckPaymentHistorySchema(BaseModel):
    """Input for check_payment_history tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number")


class GetCustomerPreferencesSchema(BaseModel):
    """Input for get_customer_preferences tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number")
