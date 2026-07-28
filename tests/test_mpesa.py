import pytest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.tools.mpesa.schemas import MpesaPaymentSchema, CheckStatusSchema, TransactionState
from src.tools.mpesa.store import transaction_store
from src.tools.mpesa.webhooks import router as mpesa_router
from src.tools.mpesa import webhooks
from src.tools.mpesa.tools import send_stk_push, check_transaction_status

# Patch the webhook secret in the webhooks module for testing
webhooks.MPESA_WEBHOOK_SECRET = "test_secret"

app = FastAPI()
app.include_router(mpesa_router)
client = TestClient(app)

def test_schema_valid_phone():
    schema = MpesaPaymentSchema(
        Amount=100,
        PartyA="254700000000",
        AccountReference="Test",
        TransactionDesc="Desc"
    )
    assert schema.PartyA == "254700000000"

def test_schema_invalid_phone():
    with pytest.raises(ValidationError):
        MpesaPaymentSchema(
            Amount=100,
            PartyA="0700000000",
            AccountReference="Test",
            TransactionDesc="Desc"
        )

@pytest.mark.asyncio
async def test_stk_callback_success():
    checkout_request_id = "ws_CO_12345"
    
    await transaction_store.set(
        checkout_request_id,
        {
            "state": TransactionState.PENDING.value,
            "merchant_request_id": "req_1",
            "amount": 100,
            "phone_number": "254700000000",
            "account_reference": "Ref",
        },
    )

    payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "req_1",
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 100.00},
                        {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                        {"Name": "Balance"},
                        {"Name": "TransactionDate", "Value": 20191121152811},
                        {"Name": "PhoneNumber", "Value": 254700000000}
                    ]
                }
            }
        }
    }

    response = client.post("/mpesa/callback/test_secret", json=payload)
    assert response.status_code == 200
    assert response.json()["ResultCode"] == 0

    record = await transaction_store.get(checkout_request_id)
    assert record["state"] == TransactionState.SUCCESS.value
    assert record["mpesa_receipt"] == "NLJ7RT61SV"
    assert record["amount"] == 100.00
    assert record["phone_number"] == 254700000000

@pytest.mark.asyncio
async def test_stk_callback_cancelled():
    checkout_request_id = "ws_CO_cancelled_1"
    
    await transaction_store.set(
        checkout_request_id,
        {
            "state": TransactionState.PENDING.value,
            "merchant_request_id": "req_2",
            "amount": 500,
            "phone_number": "254711111111",
            "account_reference": "CancelTest",
        },
    )

    payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "req_2",
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user."
            }
        }
    }

    response = client.post("/mpesa/callback/test_secret", json=payload)
    assert response.status_code == 200

    record = await transaction_store.get(checkout_request_id)
    assert record["state"] == TransactionState.CANCELLED.value

def test_webhook_invalid_secret():
    response = client.post("/mpesa/callback/wrong_secret", json={})
    assert response.status_code == 404

def test_c2b_validation_and_confirmation():
    res_val = client.post("/mpesa/c2b/validation/test_secret", json={"TransID": "123"})
    assert res_val.status_code == 200
    assert res_val.json()["ResultCode"] == 0

    res_conf = client.post("/mpesa/c2b/confirmation/test_secret", json={"TransID": "123", "MSISDN": "254700000000"})
    assert res_conf.status_code == 200
    assert res_conf.json()["ResultCode"] == 0

@pytest.mark.asyncio
async def test_send_stk_push_tool():
    payload = MpesaPaymentSchema(
        Amount=200,
        PartyA="254722222222",
        AccountReference="ToolRef",
        TransactionDesc="ToolDesc"
    )

    mock_client_response = {
        "CheckoutRequestID": "ws_CO_tool_999",
        "MerchantRequestID": "merchant_999",
        "CustomerMessage": "Success"
    }

    with patch("src.tools.mpesa.tools.mpesa_client.stk_push", AsyncMock(return_value=mock_client_response)):
        res = await send_stk_push(payload)
        assert res.checkout_request_id == "ws_CO_tool_999"
        assert res.state == TransactionState.PENDING

        record = await transaction_store.get("ws_CO_tool_999")
        assert record["amount"] == 200
