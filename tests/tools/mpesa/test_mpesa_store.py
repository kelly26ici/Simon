"""Tests for M-Pesa transaction store in src/tools/mpesa/store.py."""

import pytest
from src.tools.mpesa.store import transaction_store


@pytest.mark.asyncio
async def test_mpesa_transaction_store_save_and_get():
    tx_data = {
        "checkout_request_id": "ws_CO_999",
        "phone_number": "254712345678",
        "amount": 5000,
        "status": "pending",
    }
    await transaction_store.set("ws_CO_999", tx_data)
    fetched = await transaction_store.get("ws_CO_999")
    assert fetched is not None
    assert fetched["amount"] == 5000
    assert fetched["phone_number"] == "254712345678"
