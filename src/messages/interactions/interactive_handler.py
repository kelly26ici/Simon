# src/messages/interactions/interactive_handler.py

from loguru import logger
from src.messages.chats.text_handler import handle_text


async def handle_interactive(sender: str, msg: dict) -> None:
    """
    Handles incoming interactive WhatsApp messages (button clicks, quick replies, list selections).
    Extracts the user's selected title and passes it to the conversational pipeline.
    """
    interactive = msg.get("interactive", {})
    itype = interactive.get("type", "")
    message_id = msg.get("id", "")

    user_text = ""
    if itype == "button_reply":
        button_reply = interactive.get("button_reply", {})
        user_text = button_reply.get("title") or button_reply.get("id", "")
        logger.info("Interactive button clicked by {}: '{}' (id: {})", sender, user_text, button_reply.get("id"))
    elif itype == "list_reply":
        list_reply = interactive.get("list_reply", {})
        user_text = list_reply.get("title") or list_reply.get("id", "")
        logger.info("Interactive list option selected by {}: '{}' (id: {})", sender, user_text, list_reply.get("id"))
    elif itype == "nfm_reply":
        # Flow / Form reply
        nfm_reply = interactive.get("nfm_reply", {})
        user_text = nfm_reply.get("response_json", "")
        logger.info("Flow reply from {}: {}", sender, user_text)
    else:
        logger.warning("Unrecognized interactive type '{}' from {}", itype, sender)

    if not user_text:
        user_text = "Hello"

    synthetic_msg = {
        "id": message_id,
        "type": "text",
        "text": {
            "body": user_text,
        },
    }

    await handle_text(sender, synthetic_msg)
