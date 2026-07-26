# src/messages/chats/text_handler.reply

from src.messages.chats.conversation import get_history, append_message
from src.messages.sender import send_whatsapp_message
from src.services.llm import ask_gpt


async def handle_text(sender: str, msg: dict) -> None:
    """Handles one incoming text message using THIS customer's own history."""
    user_text = msg["text"]["body"]

    append_message(sender, "user", user_text)
    reply = await ask_gpt(get_history(sender))  # full per-customer history, not just the raw string
    reply_text = reply.output_text
    append_message(sender, "assistant", reply_text)

    await send_whatsapp_message(sender, reply_text)
    