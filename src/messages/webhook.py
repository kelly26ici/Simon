# src/messages/webhook.py

import json

from fastapi import Response
from loguru import logger

from src.messages.validator import verify_signature
from src.messages.parser import parse_incoming
from src.messages.router import dispatch
from src.core.redis import RedisStore

SeenMessages = RedisStore(prefix="seen_msg")


async def process_webhook_event(body: bytes, signature_header: str) -> Response:
    """Full pipeline for one POST /webhook call: verify -> parse -> dispatch.

    Always returns 200 once the signature check passes, even if a handler
    throws — returning non-200 makes Meta retry-deliver the same message,
    which just re-triggers the same failure (or double-sends once it's fixed).
    """
    if not verify_signature(body, signature_header):
        logger.warning("Signature verification failed")
        return Response(status_code=403)

    data = json.loads(body)

    message = parse_incoming(data)
    if message is None:
        return Response(status_code=200)  # status update, not a message

    msg_id = message.raw.get("id")
    if msg_id:
        if await SeenMessages.get(msg_id):
            logger.debug("Duplicate message ignored: {}", msg_id)
            return Response(status_code=200)
        await SeenMessages.set(msg_id, "1", ex=3600)

    try:
        await dispatch(message)
    except Exception as exc:
        logger.exception(
            "Error handling message from {}: {}",
            message.sender,
            exc,
        )

    return Response(status_code=200)
