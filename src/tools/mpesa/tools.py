"""
Agent-facing M-Pesa tools, registered with the shared ToolRegistry using
the Responses API declaration shape (see src/tools/registry.py).

Exposes:
    - send_stk_push
    - check_transaction_status

Everything else (auth, C2B registration, callback handling, persistence)
is plumbing the agent never touches directly - that lives in client.py,
store.py and webhooks.py.
"""

from __future__ import annotations

from httpx import TransportError, TimeoutException
from loguru import logger

from src.tools.registry import registry
from src.tools.mpesa.client import mpesa_client
from src.tools.mpesa.store import transaction_store
from src.tools.mpesa.schemas import (
    MpesaPaymentSchema,
    CheckStatusSchema,
    STKPushResult,
    TransactionStatus,
    TransactionState,
)


@registry.register("send_stk_push", MpesaPaymentSchema)
async def send_stk_push(payload: MpesaPaymentSchema) -> STKPushResult:
    """
    Send an M-Pesa STK Push prompt to a customer's phone, asking them to
    authorize a payment.

    This only confirms Safaricom ACCEPTED the request - it does not mean
    the customer has paid yet. The actual result arrives asynchronously via
    callback, usually within 20-60 seconds. Use check_transaction_status
    with the returned checkout_request_id to poll for the outcome if the
    customer needs an immediate answer.
    """
    body = await mpesa_client.stk_push(payload)

    checkout_request_id = body["CheckoutRequestID"]
    merchant_request_id = body["MerchantRequestID"]

    await transaction_store.set(
        checkout_request_id,
        {
            "state": TransactionState.PENDING.value,
            "merchant_request_id": merchant_request_id,
            "amount": payload.Amount,
            "phone_number": payload.PartyA,
            "account_reference": payload.AccountReference,
        },
    )

    logger.success("STK push initiated successfully | checkout_request_id={} phone={} amount=KES {}", checkout_request_id, payload.PartyA, payload.Amount)

    return STKPushResult(
        checkout_request_id=checkout_request_id,
        merchant_request_id=merchant_request_id,
        customer_message=body.get("CustomerMessage", "Payment prompt sent to your phone."),
        state=TransactionState.PENDING,
    )


@registry.register("check_transaction_status", CheckStatusSchema)
async def check_transaction_status(payload: CheckStatusSchema) -> TransactionStatus:
    """
    Check the current status of a payment previously started with
    send_stk_push.

    Checks local state first (updated instantly by Daraja's callback when
    it arrives). Falls back to querying Daraja directly if no callback has
    landed yet - useful if the customer asks "did it go through?" before
    the callback has had time to arrive, or if a callback was missed.
    """
    checkout_request_id = payload.checkout_request_id
    record = await transaction_store.get(checkout_request_id)

    if record and record.get("state") != TransactionState.PENDING.value:
        return TransactionStatus(
            checkout_request_id=checkout_request_id,
            state=TransactionState(record["state"]),
            amount=record.get("amount"),
            mpesa_receipt=record.get("mpesa_receipt"),
            phone_number=record.get("phone_number"),
            result_desc=record.get("result_desc"),
        )

    # No definitive local state yet - ask Daraja directly. I only want to
    # catch "couldn't reach Daraja" here and report that back as still-
    # pending. Anything else is a real bug on my end and I want it to
    # surface instead of getting quietly relabelled as "pending".
    try:
        body = await mpesa_client.query_stk_status(checkout_request_id)
    except (TransportError, TimeoutException) as e:
        logger.warning("Status query unreachable for {}: {}", checkout_request_id, e)
        return TransactionStatus(checkout_request_id=checkout_request_id, state=TransactionState.PENDING)

    result_code = body.get("ResultCode")
    if result_code is None:
        return TransactionStatus(checkout_request_id=checkout_request_id, state=TransactionState.PENDING)

    if str(result_code) == "0":
        state = TransactionState.SUCCESS
    elif str(result_code) == "1032":
        state = TransactionState.CANCELLED
    else:
        state = TransactionState.FAILED

    await transaction_store.update(checkout_request_id, state=state.value, result_desc=body.get("ResultDesc"))
    logger.success("M-Pesa status query resolved | checkout_request_id={} state={}", checkout_request_id, state.value)

    return TransactionStatus(
        checkout_request_id=checkout_request_id,
        state=state,
        result_desc=body.get("ResultDesc"),
        amount=record.get("amount") if record else None,
        phone_number=record.get("phone_number") if record else None,
    )