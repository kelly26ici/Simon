"""Tests for M-Pesa schemas in src/tools/mpesa/schemas.py."""

import pytest
from src.tools.mpesa.schemas import (
    MpesaPaymentSchema,
    CheckStatusSchema,
    TransactionState,
    STKPushResult,
    TransactionStatus,
)


def test_mpesa_payment_schema_valid_phone():
    schema = MpesaPaymentSchema(
        Amount=1000,
        PartyA="254712345678",
        AccountReference="REF123",
        TransactionDesc="Deposit",
    )
    assert schema.PartyA == "254712345678"


def test_mpesa_payment_schema_invalid_phone():
    with pytest.raises(ValueError):
        MpesaPaymentSchema(
            Amount=1000,
            PartyA="0712345678",  # not 254...
            AccountReference="REF123",
            TransactionDesc="Deposit",
        )


def test_transaction_state_enum():
    assert TransactionState.PENDING == "pending"
    assert TransactionState.SUCCESS == "success"
    assert TransactionState.FAILED == "failed"
    assert TransactionState.CANCELLED == "cancelled"


def test_stk_push_result_creation():
    res = STKPushResult(
        checkout_request_id="ws_CO_123",
        merchant_request_id="mr_123",
        customer_message="Success",
    )
    assert res.state == TransactionState.PENDING
