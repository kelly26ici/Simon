from loguru import logger
from src.tools.registry import registry
from src.tools.memory.schemas import (
    SaveCustomerFactSchema,
    FlagForSummarySchema,
    CheckPaymentHistorySchema,
    GetCustomerPreferencesSchema,
)
from src.services.db import db
from src.core.redis import RedisStore

summary_queue = RedisStore(prefix="summary_queue")

@registry.register("save_customer_fact", SaveCustomerFactSchema)
async def save_customer_fact(payload: SaveCustomerFactSchema) -> dict:
    """Save a structured fact about the customer (name, budget, target area, family size, etc.)."""
    field_name, field_val = payload.get_field_and_value()
    await db.upsert_customer_profile(payload.phone_number, {field_name: field_val})
    logger.success("Customer fact saved successfully | phone={} field='{}'", payload.phone_number, field_name)
    return {"status": "success", "message": f"Saved {field_name} for {payload.phone_number}"}

@registry.register("get_customer_preferences", GetCustomerPreferencesSchema)
async def get_customer_preferences(payload: GetCustomerPreferencesSchema) -> dict:
    """Retrieve all saved profile facts and preferences for a customer."""
    profile = await db.get_customer_profile(payload.phone_number)
    if not profile:
        logger.warning("No profile recorded yet for customer {}", payload.phone_number)
        return {"status": "not_found", "message": "No recorded profile yet for this customer."}
    logger.success("Customer preferences retrieved successfully | phone={}", payload.phone_number)
    return {"status": "success", "profile": profile}

@registry.register("flag_for_summary", FlagForSummarySchema)
async def flag_for_summary(payload: FlagForSummarySchema) -> dict:
    """Flag a conversation to be summarized in the background."""
    await summary_queue.set(payload.phone_number, True)
    logger.success("Conversation flagged for background summary | phone={}", payload.phone_number)
    return {"status": "success", "message": "Flagged for background summarization."}

@registry.register("check_payment_history", CheckPaymentHistorySchema)
async def check_payment_history(payload: CheckPaymentHistorySchema) -> dict:
    """Check if this number has paid before."""
    has_paid = await db.check_payment_history(payload.phone_number)
    logger.success("Payment history checked | phone={} has_paid={}", payload.phone_number, has_paid)
    return {"has_paid": has_paid}
