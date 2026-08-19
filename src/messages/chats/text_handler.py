# src/messages/chats/text_handler.py

from datetime import datetime, timezone
import json
from loguru import logger

from src.messages.chats.conversation import get_history, append_message
from src.messages.sender import send_whatsapp_message, send_typing_indicator
from src.services.llm import ask_gpt
from src.services.db import db

logger.add("logs/text_handler.log", rotation="100 MB")


async def _build_customer_context_string(sender: str) -> str:
    """Builds a contextual profile string for the current user."""
    context_lines = [
        f"Customer WhatsApp ID / Phone: {sender}",
        f"Current Timestamp (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]

    try:
        profile = await db.get_customer_profile(sender)
        if profile:
            if profile.get("preferred_name"):
                context_lines.append(f"Customer Name: {profile['preferred_name']}")
            if profile.get("budget_range"):
                context_lines.append(f"Known Budget: {profile['budget_range']}")
            if profile.get("preferred_area"):
                context_lines.append(f"Preferred Neighborhood: {profile['preferred_area']}")
            metadata = profile.get("metadata") or {}
            if metadata:
                context_lines.append(f"Learned Customer Facts & Preferences: {json.dumps(metadata)}")

        viewings = await db.get_customer_viewings(sender, status="confirmed")
        if viewings:
            viewing_summaries = []
            for v in viewings[:3]:
                viewing_summaries.append(f"Booking #{v.get('id', '')[:8]}: {v.get('viewing_date')} ({v.get('status')})")
            context_lines.append(f"Upcoming Viewings: {'; '.join(viewing_summaries)}")
    except Exception as exc:
        logger.debug("Failed to build customer context for {}: {}", sender, exc)

    return "\n".join(context_lines)


async def handle_text(sender: str, msg: dict) -> None:
    """Handles one incoming text message using THIS customer's own history and profile."""
    user_text = msg["text"]["body"]
    message_id = msg["id"]  # WAMID of the inbound message — needed for typing indicator

    await append_message(sender, "user", user_text)
    history = await get_history(sender)
    customer_context = await _build_customer_context_string(sender)

    try:
        await send_typing_indicator(message_id)
    except Exception as exc:
        logger.warning(
            "Typing indicator failed for {}: {}",
            message_id,
            exc,
            exc_info=True,
        )

    try:
        reply = await ask_gpt(history, customer_context=customer_context)
    except Exception as exc:
        logger.exception("LLM failed for sender {}: {}", sender, exc)
        fallback = "I’m having trouble answering that right now. Please try again in a moment."
        await append_message(sender, "assistant", fallback)
        await send_whatsapp_message(sender, fallback)
        return

    reply_text = getattr(reply, "output_text", None) or ""
    if not reply_text:
        logger.warning(
            "LLM returned empty / None output_text for sender={} — sending fallback",
            sender,
        )
        fallback = "I'm having trouble answering that right now. Please try again in a moment."
        await append_message(sender, "assistant", fallback)
        await send_whatsapp_message(sender, fallback)
        return

    await append_message(sender, "assistant", reply_text)

    try:
        await send_whatsapp_message(sender, reply_text)
    except Exception as exc:
        logger.exception("WhatsApp send failed for sender {}: {}", sender, exc)

