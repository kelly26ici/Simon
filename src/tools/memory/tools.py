from src.tools.registry import registry
from src.tools.memory.schemas import SaveCustomerFactSchema, FlagForSummarySchema, CheckPaymentHistorySchema
from src.services.db import db
from src.core.redis import RedisStore

summary_queue = RedisStore(prefix="summary_queue")

@registry.register("save_customer_fact", SaveCustomerFactSchema)
async def save_customer_fact(payload: SaveCustomerFactSchema) -> dict:
    """Save a structured fact about the customer."""
    await db.upsert_customer_profile(payload.phone_number, {payload.field: payload.value})
    return {"status": "success", "message": f"Saved {payload.field} for {payload.phone_number}"}

@registry.register("flag_for_summary", FlagForSummarySchema)
async def flag_for_summary(payload: FlagForSummarySchema) -> dict:
    """Flag a conversation to be summarized in the background."""
    await summary_queue.set(payload.phone_number, True)
    return {"status": "success", "message": "Flagged for background summarization."}

@registry.register("check_payment_history", CheckPaymentHistorySchema)
async def check_payment_history(payload: CheckPaymentHistorySchema) -> dict:
    """Check if this number has paid before."""
    # TODO: As per architectural design, this should ideally be bound to envelope.sender 
    # at the call site so the model cannot hallucinate or pass arbitrary numbers.
    has_paid = await db.check_payment_history(payload.phone_number)
    return {"has_paid": has_paid}
