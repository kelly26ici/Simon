# src/messages/chats/text_handler.py

import loguru
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
    except Exception:
        logger.warning("typing indicator failed for %s", message_id, exc_info=True)

    reply = await ask_gpt(history)  # full per-customer history, not just the raw string
    reply_text = reply.output_text
    await append_message(sender, "assistant", reply_text)

    await send_whatsapp_message(sender, reply_text)
