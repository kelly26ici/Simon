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

import time
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger

from src.configs.settings import MPESA_WEBHOOK_SECRET
from src.services.db import db
from src.tools.mpesa.store import transaction_store
from src.tools.mpesa.schemas import TransactionState

router = APIRouter(prefix="/mpesa", tags=["mpesa-webhooks"])

# Short-lived dedupe window for Daraja callback retries/replays.
_DEDUPE_WINDOW_SECONDS = 600


def _check_secret(secret: str) -> None:
    if secret != MPESA_WEBHOOK_SECRET:
        # 404 rather than 401/403 so the endpoint doesn't even confirm
        # it exists to someone probing for it.
        raise HTTPException(status_code=404)


async def _parse_json_body(request: Request) -> dict[str, Any]:
    """Safely parse JSON from the request body, returning an empty dict on failure."""
    try:
        data = await request.json()
    except Exception as e:
        logger.warning("Failed to parse JSON body: {}", e)
        return {}
    if not isinstance(data, dict):
        logger.warning("Expected JSON object in request body, got {}", type(data).__name__)
        return {}
    return data


async def _mark_seen(checkout_request_id: str, trans_id: str | None = None) -> bool:
    keys = [f"seen:{checkout_request_id}"]
    if trans_id:
        keys.append(f"seen:{trans_id}")
    for key in keys:
        already = await transaction_store.get(key)
        if already:
            return False
        await transaction_store.set(key, {"seen_at": int(time.time())}, ex=_DEDUPE_WINDOW_SECONDS)
    return True


@router.post("/callback/{secret}")
async def handle_stk_callback(secret: str, request: Request):
    """
    Daraja calls this asynchronously with the outcome of an STK push.
    Always acknowledge with 200 + ResultCode 0 regardless of the payment
    outcome - Daraja retries the webhook if it doesn't get a clean ack,
    which I don't want for a failed/cancelled payment.
    """
    _check_secret(secret)

    callback_data = await _parse_json_body(request)
    logger.info("STK callback: {}", callback_data)

    ack = JSONResponse(content={"ResultCode": 0, "ResultDesc": "Received"})

    stk_callback = callback_data.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    result_code = stk_callback.get("ResultCode")

    if not checkout_request_id:
        logger.error("Callback missing CheckoutRequestID: {}", callback_data)
        return ack

    if result_code is None:
        logger.error("Callback missing ResultCode: {}", callback_data)
        await transaction_store.update(
            checkout_request_id,
            state=TransactionState.FAILED.value,
            result_desc="Missing ResultCode in callback",
        )
        return ack

    if result_code != 0:
        result_desc = stk_callback.get("ResultDesc", "Unknown error")
        state = TransactionState.CANCELLED if result_code == 1032 else TransactionState.FAILED
        logger.info("STK {}: {} - {}", state.value, checkout_request_id, result_desc)
        if not await _mark_seen(checkout_request_id):
            logger.info("Duplicate STK callback ignored: {}", checkout_request_id)
            return ack
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

    if not await _mark_seen(checkout_request_id):
        logger.info("Duplicate STK success callback ignored: {}", checkout_request_id)
        return ack

    mpesa_receipt = metadata.get("MpesaReceiptNumber")
    amount = metadata.get("Amount")
    phone_number = metadata.get("PhoneNumber")

    await transaction_store.update(
        checkout_request_id,
        state=TransactionState.SUCCESS.value,
        mpesa_receipt=mpesa_receipt,
        amount=amount,
        phone_number=phone_number,
        result_desc="Payment received",
    )

    # Best-effort durable write to Supabase so check_payment_history has
    # data to query. Never block the Daraja ack — a DB failure here must not
    # cause the callback to retry.
    try:
        await db.save_mpesa_transaction(
            checkout_request_id,
            {
                "merchant_request_id": stk_callback.get("MerchantRequestID"),
                "phone_number": phone_number,
                "amount": amount,
                "account_reference": metadata.get("AccountReference"),
                "mpesa_receipt": mpesa_receipt,
                "state": "success",
                "result_desc": "Payment received",
            },
        )
    except Exception as e:
        logger.warning(
            "STK success {} persisted to Redis but failed Supabase write: {}",
            checkout_request_id, e,
        )

    logger.info("STK success: {} - {}", checkout_request_id, metadata)
    return ack


@router.post("/c2b/validation/{secret}")
async def handle_c2b_validation(secret: str, request: Request):
    _check_secret(secret)
    validation_data = await _parse_json_body(request)
    logger.info("C2B validation payload: {}", validation_data)
    return JSONResponse(content={"ResultCode": 0, "ResultDesc": "Accepted"})


@router.post("/c2b/confirmation/{secret}")
async def handle_c2b_confirmation(secret: str, request: Request):
    _check_secret(secret)
    confirmation_data = await _parse_json_body(request)
    logger.info("C2B confirmation payload: {}", confirmation_data)

    trans_id = confirmation_data.get("TransID")
    if not trans_id:
        logger.warning("C2B confirmation missing TransID: {}", confirmation_data)
        return JSONResponse(content={"ResultCode": 0, "ResultDesc": "Completed"})

    if not await _mark_seen("", trans_id=trans_id):
        logger.info("Duplicate C2B confirmation ignored: {}", trans_id)
        return JSONResponse(content={"ResultCode": 0, "ResultDesc": "Completed"})

    await transaction_store.set(
        f"c2b:{trans_id}",
        {
            "transaction_type": confirmation_data.get("TransactionType"),
            "transaction_id": trans_id,
            "transaction_time": confirmation_data.get("TransTime"),
            "amount": confirmation_data.get("TransAmount"),
            "business_shortcode": confirmation_data.get("BusinessShortCode"),
            "account_reference": confirmation_data.get("BillRefNumber"),
            "invoice_number": confirmation_data.get("InvoiceNumber"),
            "phone_number": confirmation_data.get("MSISDN"),
            "first_name": confirmation_data.get("FirstName"),
            "state": "completed",
        },
    )
    logger.info("Persisted C2B transaction: {}", trans_id)

    return JSONResponse(content={"ResultCode": 0, "ResultDesc": "Completed"})
