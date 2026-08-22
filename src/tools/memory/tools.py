from loguru import logger
from src.tools.registry import registry
from src.tools.memory.schemas import (
    SaveCustomerFactSchema,
    UpdateConversationSummarySchema,
    NotifyOwnerSchema,
    CheckPaymentHistorySchema,
    GetCustomerPreferencesSchema,
)
from src.services.db import db


@registry.register("save_customer_fact", SaveCustomerFactSchema)
async def save_customer_fact(payload: SaveCustomerFactSchema) -> dict:
    """Save a structured fact about the customer (name, budget, target area, family size, etc.).

    Call this tool whenever the customer reveals personal preferences, constraints, or details
    that will help you serve them better — e.g. name, budget range, preferred area or city,
    number of bedrooms needed, move-in date, lifestyle preferences.
    """
    field_name, field_val = payload.get_field_and_value()
    await db.upsert_customer_profile(payload.phone_number, {field_name: field_val})
    logger.success("Customer fact saved | phone={} field='{}'", payload.phone_number, field_name)
    return {"status": "success", "message": f"Saved {field_name} for {payload.phone_number}"}


@registry.register("get_customer_preferences", GetCustomerPreferencesSchema)
async def get_customer_preferences(payload: GetCustomerPreferencesSchema) -> dict:
    """Retrieve all saved profile facts and preferences for a customer."""
    profile = await db.get_customer_profile(payload.phone_number)
    if not profile:
        logger.warning("No profile recorded yet for customer {}", payload.phone_number)
        return {"status": "not_found", "message": "No recorded profile yet for this customer."}
    logger.success("Customer preferences retrieved | phone={}", payload.phone_number)
    return {"status": "success", "profile": profile}


@registry.register("update_conversation_summary", UpdateConversationSummarySchema)
async def update_conversation_summary(payload: UpdateConversationSummarySchema) -> dict:
    """Update the running summary of the real-estate conversation with this customer.

    Call this tool periodically — after every 3-4 meaningful exchanges — to keep a live,
    concise record of the conversation. The summary should capture:
      - Customer name and phone
      - Key requirements: budget, location, property type, bedrooms, lifestyle needs
      - Properties shown / shortlisted (IDs + titles + prices)
      - Viewing bookings (date, status)
      - Negotiation or decision stage (browsing → interested → viewing booked → offer stage)
      - Any concerns, objections, or special requests
      - Next steps agreed

    Write the FULL updated summary each time — do not append to the previous version,
    replace it with the complete, up-to-date picture.

    The summary is persisted in the database in real time and is used when
    notify_owner is called to brief the owner on the lead.
    """
    ok = await db.upsert_conversation_summary(payload.phone_number, payload.summary)
    if ok:
        logger.success(
            "Conversation summary updated | phone={} summary_len={}",
            payload.phone_number,
            len(payload.summary),
        )
        return {"status": "success", "message": "Conversation summary updated."}
    logger.error("Failed to persist conversation summary for {}", payload.phone_number)
    return {"status": "error", "message": "Could not save the summary. Database may be unavailable."}


@registry.register("notify_owner", NotifyOwnerSchema)
async def notify_owner(payload: NotifyOwnerSchema) -> dict:
    """Send a Telegram notification to the owner (Simon) about a customer interaction.

    Use this tool when:
    - A customer has booked a viewing — send the booking details immediately.
    - A customer is seriously interested and ready to proceed (hot lead).
    - A customer has asked to speak directly with an agent.
    - A negotiation has reached a meaningful stage (price discussed, offer made).
    - You have gathered enough information and want to alert Simon proactively.

    The message is delivered via Telegram to Simon's phone in real time.
    Include ALL relevant details: customer name, phone, what they want,
    properties of interest, viewing date/time, urgency, and next steps.
    """
    from src.services.telegram import send_telegram_message

    # Fetch the latest summary to enrich the notification
    summary = await db.get_conversation_summary(payload.phone_number) or ""

    lines = [
        "🏠 *New Lead / Customer Update*",
        f"*Customer Phone:* `{payload.phone_number}`",
        "",
        payload.message,
    ]
    if summary:
        lines += [
            "",
            "─────────────────────",
            "*Conversation Summary:*",
            summary,
        ]

    full_text = "\n".join(lines)

    ok = await send_telegram_message(full_text)
    if ok:
        logger.success(
            "Owner notified via Telegram | phone={} message_len={}",
            payload.phone_number,
            len(full_text),
        )
        return {
            "status": "success",
            "message": "Owner has been notified via Telegram.",
        }

    logger.warning(
        "Telegram notification failed for phone={} — check TELEGRAM_BOT_TOKEN and owner /start",
        payload.phone_number,
    )
    return {
        "status": "failed",
        "message": (
            "Could not send Telegram notification. "
            "Possible causes: TELEGRAM_BOT_TOKEN not set, or owner hasn't pressed /start yet."
        ),
    }


@registry.register("check_payment_history", CheckPaymentHistorySchema)
async def check_payment_history(payload: CheckPaymentHistorySchema) -> dict:
    """Check if this customer's phone number has any successful past M-Pesa transactions."""
    has_paid = await db.check_payment_history(payload.phone_number)
    logger.success("Payment history checked | phone={} has_paid={}", payload.phone_number, has_paid)
    return {"has_paid": has_paid}
