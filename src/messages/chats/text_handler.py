# src/messages/chats/text_handler.py

from loguru import logger

from src.messages.chats.conversation import get_history, append_message
from src.messages.sender import send_whatsapp_message, send_typing_indicator
from src.services.llm import ask_gpt

logger.add("logs/text_handler.log", rotation="100 MB")


async def handle_text(sender: str, msg: dict) -> None:
    """Handles one incoming text message using THIS customer's own history."""
    user_text = msg["text"]["body"]
    message_id = msg["id"]  # WAMID of the inbound message — needed for typing indicator

    await append_message(sender, "user", user_text)
    history = await get_history(sender)

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
        reply = await ask_gpt(history)
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
