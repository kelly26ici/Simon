# src/messages/chats/text_handler.py

from datetime import datetime, timezone
import json
import re
from loguru import logger

from src.messages.chats.conversation import get_history, append_message
from src.messages.sender import send_whatsapp_message, send_typing_indicator
from src.services.llm import (
    ask_llm,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMAuthenticationError,
    LLMError,
)
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


def _extract_retry_after(exc: Exception) -> str | None:
    """Try to parse a 'retry after N seconds' hint from the exception message."""
    msg = str(exc)
    # Common formats: "retry after 47.123 seconds", "Please try again in 60s", "Retry-After: 30"
    match = re.search(
        r"(?:retry.{0,15}?|try again in\s*)(\d+(?:\.\d+)?)\s*s(?:econds?)?",
        msg,
        re.IGNORECASE,
    )
    if match:
        seconds = float(match.group(1))
        minutes = round(seconds / 60, 1)
        if minutes >= 1:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        return f"{int(seconds)} seconds"
    return None


def _customer_message_for_llm_error(exc: Exception) -> str:
    """Map a typed LLM exception to a clean, customer-friendly WhatsApp message."""
    if isinstance(exc, LLMRateLimitError):
        retry_hint = _extract_retry_after(exc)
        if retry_hint:
            return (
                f"We're receiving a lot of requests right now and our AI assistant is momentarily busy. "
                f"Please try again in about {retry_hint}. Sorry for the wait! 🙏"
            )
        return (
            "We're receiving a lot of requests right now and our AI assistant is momentarily busy. "
            "Please try again in a few minutes. Sorry for the wait! 🙏"
        )

    if isinstance(exc, LLMAuthenticationError):
        logger.critical("LLM authentication/permission error — check API key and quota: {}", exc)
        return (
            "Our AI assistant is currently undergoing maintenance. "
            "Please contact us directly at 0701 454 854 and we'll be happy to help! 😊"
        )

    if isinstance(exc, LLMServiceUnavailableError):
        return (
            "Our AI assistant is temporarily unavailable due to a service interruption. "
            "Please try again in a few minutes. If it persists, call us at 0701 454 854. 🙏"
        )

    # Generic LLMError or unexpected
    return (
        "Something unexpected happened on our end. Please try again in a moment. "
        "If the problem continues, reach us at 0701 454 854. 😊"
    )


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
        reply = await ask_llm(history, customer_context=customer_context)
    except (LLMRateLimitError, LLMAuthenticationError, LLMServiceUnavailableError, LLMError) as exc:
        # These are typed, known LLM failures — give the customer a specific message.
        logger.error("LLM error for sender {}: {}: {}", sender, type(exc).__name__, exc)
        fallback = _customer_message_for_llm_error(exc)
        await append_message(sender, "assistant", fallback)
        await send_whatsapp_message(sender, fallback)
        return
    except Exception as exc:
        # Truly unexpected (e.g. network misconfiguration, bug) — generic safe message.
        logger.exception("Unexpected error calling LLM for sender {}", sender)
        fallback = (
            "Something unexpected happened. Please try again in a moment "
            "or call us at 0701 454 854. 😊"
        )
        await append_message(sender, "assistant", fallback)
        await send_whatsapp_message(sender, fallback)
        return

    reply_text = getattr(reply, "output_text", None) or ""
    if not reply_text:
        logger.warning(
            "LLM returned empty / None output_text for sender={} — sending fallback",
            sender,
        )
        fallback = (
            "I didn't quite get a response there. Could you rephrase that, or try again in a moment? 😊"
        )
        await append_message(sender, "assistant", fallback)
        await send_whatsapp_message(sender, fallback)
        return

    await append_message(sender, "assistant", reply_text)

    try:
        await send_whatsapp_message(sender, reply_text)
    except Exception as exc:
        logger.exception("WhatsApp send failed for sender {}: {}", sender, exc)

