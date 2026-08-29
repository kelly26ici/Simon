"""Tests for M-Pesa agent tools in src/tools/mpesa/tools.py."""

import pytest
from unittest.mock import AsyncMock, patch
from src.tools.mpesa.tools import send_stk_push, check_transaction_status
from src.tools.mpesa.schemas import MpesaPaymentSchema, CheckStatusSchema, TransactionState, TransactionStatus


@pytest.mark.asyncio
async def test_send_stk_push_tool():
    payload = MpesaPaymentSchema(
        Amount=5000,
        PartyA="254700000000",
        AccountReference="PROP123",
        TransactionDesc="Deposit",
    )
    fake_daraja_resp = {
        "CheckoutRequestID": "ws_CO_001",
        "MerchantRequestID": "mr_001",
        "CustomerMessage": "Prompt sent to phone",
        "ResponseCode": "0",
    }
    with patch("src.tools.mpesa.tools.mpesa_client.stk_push", new=AsyncMock(return_value=fake_daraja_resp)), \
         patch("src.tools.mpesa.tools.transaction_store.set", new=AsyncMock()):
        res = await send_stk_push(payload)
        assert res.checkout_request_id == "ws_CO_001"


@pytest.mark.asyncio
async def test_check_transaction_status_tool():
    payload = CheckStatusSchema(checkout_request_id="ws_CO_001")
    fake_status = TransactionStatus(
        checkout_request_id="ws_CO_001",
        state=TransactionState.SUCCESS,
        amount=5000.0,
        mpesa_receipt="REC12345",
    )
    with patch("src.tools.mpesa.tools.transaction_store.get", new=AsyncMock(return_value={"state": "success"})), \
         patch("src.tools.mpesa.tools.mpesa_client.query_stk_status", new=AsyncMock(return_value=fake_status)):
        res = await check_transaction_status(payload)
        assert res.state == TransactionState.SUCCESS
