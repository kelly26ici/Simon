# src/messages/router.py

from loguru import logger

from src.messages.parser import IncomingMessage
from src.messages.chats.text_handler import handle_text
from src.messages.audios.audio_handler import handle_audio

# Explicit registry — add an entry here as each new handler
# (image, audio, interactive, ...) gets built out.
MESSAGE_HANDLERS = {
    "text": handle_text,
    "audio": handle_audio,
}


async def dispatch(message: IncomingMessage) -> None:
    handler = MESSAGE_HANDLERS.get(message.msg_type)
    if handler is None:
        logger.warning(
            "No handler yet for message type '{}' from {}",
            message.msg_type,
            message.sender,
        )
        return
    await handler(message.sender, message.raw)
    