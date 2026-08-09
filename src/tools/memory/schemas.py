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
    field: str = Field(
        ...,
        description=(
            "The profile field to update (snake_case). Suggested fields: "
            "preferred_name, budget_range, preferred_area — but any descriptive "
            "snake_case field is accepted (e.g. preferred_city, preferred_bedrooms, "
            "preferred_property_type, max_budget_kes)."
        ),
    )
    value: str = Field(..., description="The value to save for this field")

class FlagForSummarySchema(BaseModel):
    """Input for flag_for_summary tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number to flag for summarization")

class CheckPaymentHistorySchema(BaseModel):
    """Input for check_payment_history tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number")
