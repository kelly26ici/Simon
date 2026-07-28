"""
Webhook endpoints Daraja calls - the agent never touches these directly.
This is an APIRouter, not its own FastAPI() app - mount it with
app.include_router(mpesa_router) from wherever the real app lives.

Safaricom doesn't sign these payloads, so anyone who finds the URL can
POST a fake "payment successful" callback. A secret path segment is the
minimum bar here - for anything handling real money I also want this
locked down at the network level to Safaricom's published IP ranges,
not just this app-level check.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger

from src.configs.settings import MPESA_WEBHOOK_SECRET
from src.tools.mpesa.store import transaction_store
from src.tools.mpesa.schemas import TransactionState

router = APIRouter(prefix="/mpesa", tags=["mpesa-webhooks"])


def _check_secret(secret: str) -> None:
    if secret != MPESA_WEBHOOK_SECRET:
        # 404 rather than 401/403 so the endpoint doesn't even confirm
        # it exists to someone probing for it.
        raise HTTPException(status_code=404)


@router.post("/callback/{secret}")
async def handle_stk_callback(secret: str, request: Request):
    """
    Daraja calls this asynchronously with the outcome of an STK push.
    Always acknowledge with 200 + ResultCode 0 regardless of the payment
    outcome - Daraja retries the webhook if it doesn't get a clean ack,
    which I don't want for a failed/cancelled payment.
    """
    _check_secret(secret)

    callback_data = await request.json()
    logger.info("STK callback: {}", callback_data)

    ack = JSONResponse(content={"ResultCode": 0, "ResultDesc": "Received"})

    stk_callback = callback_data.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    result_code = stk_callback.get("ResultCode")

    if not checkout_request_id:
        logger.error("Callback missing CheckoutRequestID: {}", callback_data)
        return ack

    if result_code != 0:
        result_desc = stk_callback.get("ResultDesc", "Unknown error")
        state = TransactionState.CANCELLED if result_code == 1032 else TransactionState.FAILED
        logger.info("STK {}: {} - {}", state.value, checkout_request_id, result_desc)
        await transaction_store.update(checkout_request_id, state=state.value, result_desc=result_desc)
        return ack

    try:
        items = stk_callback["CallbackMetadata"]["Item"]
        metadata = {item["Name"]: item.get("Value") for item in items}
    except (KeyError, TypeError) as e:
        logger.error("Malformed callback metadata: {} - payload: {}", e, callback_data)
        await transaction_store.update(
            checkout_request_id, state=TransactionState.FAILED.value, result_desc="Malformed callback"
        )
        return ack

    await transaction_store.update(
        checkout_request_id,
        state=TransactionState.SUCCESS.value,
        mpesa_receipt=metadata.get("MpesaReceiptNumber"),
        amount=metadata.get("Amount"),
        phone_number=metadata.get("PhoneNumber"),
        result_desc="Payment received",
    )

    logger.info("STK success: {} - {}", checkout_request_id, metadata)
    return ack


@router.post("/c2b/validation/{secret}")
async def handle_c2b_validation(secret: str, request: Request):
    _check_secret(secret)
    validation_data = await request.json()
    logger.info("C2B validation payload: {}", validation_data)
    return JSONResponse(content={"ResultCode": 0, "ResultDesc": "Accepted"})


@router.post("/c2b/confirmation/{secret}")
async def handle_c2b_confirmation(secret: str, request: Request):
    _check_secret(secret)
    confirmation_data = await request.json()
    logger.info("C2B confirmation payload: {}", confirmation_data)

    parsed_metadata = {
        "transaction_type": confirmation_data.get("TransactionType"),
        "transaction_id": confirmation_data.get("TransID"),
        "transaction_time": confirmation_data.get("TransTime"),
        "amount": confirmation_data.get("TransAmount"),
        "business_shortcode": confirmation_data.get("BusinessShortCode"),
        "account_reference": confirmation_data.get("BillRefNumber"),
        "invoice_number": confirmation_data.get("InvoiceNumber"),
        "phone_number": confirmation_data.get("MSISDN"),
        "first_name": confirmation_data.get("FirstName"),
    }
    logger.info("Parsed C2B record: {}", parsed_metadata)

    # TODO: persist this the same way STK results are - currently logged only
    return JSONResponse(content={"ResultCode": 0, "ResultDesc": "Completed"})