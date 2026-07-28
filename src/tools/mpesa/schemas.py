"""
Pydantic schemas for the M-Pesa tools, plus the shapes Daraja expects back.
Split out from mpesa_agent.py so client.py and tools.py can both import
these without needing each other.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from src.configs.settings import SHORTCODE


class MpesaPaymentSchema(BaseModel):
    """Input for the send_stk_push tool."""

    Amount: int = Field(..., gt=0, description="Whole-number amount to charge, in KES")
    PartyA: str = Field(..., description="Payer's phone number, format 254XXXXXXXXX")
    AccountReference: str = Field(..., max_length=12, description="Short reference for the transaction, max 12 chars")
    TransactionDesc: str = Field(..., max_length=13, description="Short description of what's being paid for, max 13 chars")
    TransactionType: Literal["CustomerPayBillOnline", "CustomerBuyGoodsOnline"] = Field(
        default="CustomerPayBillOnline",
        description="CustomerBuyGoodsOnline for till numbers, CustomerPayBillOnline for paybills",
    )

    @field_validator("PartyA")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.fullmatch(r"254\d{9}", v):
            raise ValueError("Phone number must be in format 254XXXXXXXXX")
        return v


class CheckStatusSchema(BaseModel):
    """Input for the check_transaction_status tool."""

    checkout_request_id: str = Field(..., description="The ID returned by send_stk_push")


class TransactionState(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class STKPushResult(BaseModel):
    """What send_stk_push returns to the agent."""

    checkout_request_id: str
    merchant_request_id: str
    customer_message: str
    state: TransactionState = TransactionState.PENDING


class TransactionStatus(BaseModel):
    """What check_transaction_status returns to the agent."""

    checkout_request_id: str
    state: TransactionState
    amount: Optional[float] = None
    mpesa_receipt: Optional[str] = None
    phone_number: Optional[str] = None
    result_desc: Optional[str] = None


class C2BRegisterSchema(BaseModel):
    """
    ConfirmationURL / ValidationURL aren't defaulted here on purpose - they
    need the webhook secret baked in (see webhooks.py), and I'd rather
    build them once in client.py than duplicate the secret-handling logic
    in two places.
    """

    ShortCode: str = SHORTCODE
    ResponseType: Literal["Cancelled", "Completed"] = "Completed"
    ConfirmationURL: str
    ValidationURL: str    