# src/messages/parser.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class IncomingMessage:
    sender: str    # customer's phone number — used as the conversation key
    msg_type: str  # "text", "image", "audio", "interactive", etc.
    raw: dict      # the original message object, for handlers to pull from
    phone_number_id: Optional[str] = None  # recipient phone number ID from webhook metadata


def parse_incoming(data: dict) -> Optional[IncomingMessage]:
    """Pulls the first message out of a webhook payload.

    Returns None for anything that isn't an actual inbound message (delivery
    receipts, read receipts, status updates) so the caller can just skip it —
    mirrors the original try/except KeyError/IndexError behaviour.
    """
    try:
        value = data["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None

        phone_number_id = value.get("metadata", {}).get("phone_number_id")
        msg = messages[0]
        return IncomingMessage(
            sender=msg["from"],
            msg_type=msg["type"],
            raw=msg,
            phone_number_id=phone_number_id,
        )
    except (KeyError, IndexError):
        return None