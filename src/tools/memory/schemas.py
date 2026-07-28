from pydantic import BaseModel, Field
from typing import Literal

class SaveCustomerFactSchema(BaseModel):
    """Input for save_customer_fact tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number")
    field: Literal["preferred_name", "budget_range", "preferred_area"] = Field(..., description="The field to update")
    value: str = Field(..., description="The value to save for this field")

class FlagForSummarySchema(BaseModel):
    """Input for flag_for_summary tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number to flag for summarization")

class CheckPaymentHistorySchema(BaseModel):
    """Input for check_payment_history tool."""
    phone_number: str = Field(..., description="The customer's WhatsApp ID/phone number")
